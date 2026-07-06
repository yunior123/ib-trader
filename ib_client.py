import logging

import pandas as pd
from ib_insync import IB, Stock, util

log = logging.getLogger("ib-trader.client")


def connect(cfg) -> IB:
    if not cfg.DRY_RUN and cfg.IB_ACCOUNT != cfg.TFSA_ACCOUNT:
        raise RuntimeError(
            f"Live trading is restricted to TFSA account {cfg.TFSA_ACCOUNT}; "
            f"refusing account {cfg.IB_ACCOUNT}."
        )

    ib = IB()
    ib.connect(
        cfg.IB_HOST,
        cfg.IB_PORT,
        clientId=cfg.IB_CLIENT_ID,
        readonly=cfg.DRY_RUN,
        account=cfg.IB_ACCOUNT if not cfg.DRY_RUN else "",
    )
    log.info(
        "Connected to IBKR at %s:%s (clientId=%s, account=%s, readonly=%s)",
        cfg.IB_HOST,
        cfg.IB_PORT,
        cfg.IB_CLIENT_ID,
        cfg.IB_ACCOUNT if not cfg.DRY_RUN else "paper/default",
        cfg.DRY_RUN,
    )
    return ib


def get_history(ib: IB, symbol: str, cfg) -> pd.DataFrame:
    contract = Stock(symbol, cfg.EXCHANGE, cfg.CURRENCY)
    ib.qualifyContracts(contract)
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=cfg.HISTORY_DURATION,
        barSizeSetting=cfg.BAR_SIZE,
        whatToShow="TRADES",
        useRTH=cfg.USE_RTH,
    )
    df = util.df(bars)
    if df is None or df.empty:
        raise RuntimeError(f"No historical data returned for {symbol}")
    return df


def get_account_value(ib: IB) -> float:
    for v in ib.accountValues():
        if v.tag == "NetLiquidation":
            return float(v.value)
    raise RuntimeError("Could not find NetLiquidation in account values")


def get_position_qty(ib: IB, symbol: str) -> float:
    for pos in ib.positions():
        if pos.contract.symbol == symbol:
            return pos.position
    return 0.0
