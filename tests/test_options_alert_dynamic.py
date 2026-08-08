#!/usr/bin/env python3
"""A newly discovered ticker remains pending until its option chain arrives."""
import datetime as dt
import os
from pathlib import Path
import subprocess
import time


REPO = Path(__file__).resolve().parents[1]
ENGINE = REPO / "bin" / "options_alert_engine"


def test_dynamic_ticker_retries_after_chain_subscription(tmp_path):
    signals = tmp_path / "data" / "trading-signals"
    signals.mkdir(parents=True)
    (tmp_path / "logs").mkdir()
    signal_file = signals / f"{dt.datetime.now():%Y-%m-%d}.txt"
    signal_file.write_text("")
    env = dict(os.environ, OPTIONS_ALERT_AUTO="1", OPTIONS_ALERT_MIN_PROB="55",
               OPTIONS_ALERT_TOP_N="2", OPTIONS_ALERT_RETRY_S="1")
    proc = subprocess.Popen([str(ENGINE), "--daemon"], cwd=tmp_path, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        time.sleep(0.7)  # daemon opens the file and tails only new fleet signals
        with signal_file.open("a") as fh:
            fh.write("09:31:00 | BRK.B: BUY | prob 60% | dynamic test\n")

        custom = tmp_path / "data" / "options_alert_tickers.txt"
        deadline = time.time() + 4
        while time.time() < deadline and not custom.exists():
            time.sleep(0.1)
        assert custom.exists(), f"daemon rc={proc.poll()}"
        assert custom.read_text().strip() == "BRK.B"

        expiry = dt.date.today() + dt.timedelta(days=5)
        chain = tmp_path / "data" / "opt_chain_brk.b.txt"
        chain.write_text(
            f"# opt_chain BRK.B | epoch {int(time.time())} | spot 500 | exps {expiry:%Y%m%d}\n"
            "# strike right exp bid ask vol oi iv delta gamma\n"
            f"500 C {expiry:%Y%m%d} 1.00 1.04 900 2200 .40 .54 .01\n"
        )
        pushed = tmp_path / "data" / "notify_push.txt"
        deadline = time.time() + 5
        while time.time() < deadline and not pushed.exists():
            time.sleep(0.1)
        assert pushed.read_text().rstrip().endswith("brk.b call 500 5-DTE")
    finally:
        proc.terminate()
        proc.wait(timeout=5)
