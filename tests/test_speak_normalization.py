import os
import subprocess


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def preview(message):
    env = dict(os.environ, SPEAK_PREVIEW="1")
    result = subprocess.run(
        ["/bin/bash", os.path.join(REPO, "scripts", "speak.sh"), "SIGNAL", message],
        cwd=REPO,
        env=env,
        text=True,
        capture_output=True,
        check=True,
        timeout=5,
    )
    return result.stdout.strip()


def test_spcx_has_unambiguous_spanish_pronunciation_without_side_effects():
    assert preview("SPCX sigue bajando fuerte.") == "Space equis sigue bajando fuerte."


def test_preview_preserves_other_text_and_existing_ticker_mapping():
    assert preview("AAPL y SPCX") == "Apple y Space equis"


def test_voice_queue_uses_canonical_database_and_records_synthesis_failures():
    src = open(os.path.join(REPO, "scripts", "voice_queue.sh")).read()
    assert 'DBV="$ROOT/data/trades.db"' in src
    assert "log_voice failed DANGER" in src
    assert "log_voice failed SIGNAL" in src
