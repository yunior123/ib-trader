import json
import os
from dataclasses import dataclass, asdict
from typing import Dict


@dataclass
class SymbolState:
    core_shares: float = 0.0       # never sold by the bot
    trading_shares: float = 0.0    # actively scaled in/out
    avg_cost: float = 0.0
    ladder_progress: int = 0       # how many profit-ladder rungs already hit on this swing


class PortfolioState:
    """JSON-backed state store so the core/trading split and ladder progress
    survive restarts of the bot (the loop is meant to run for days/weeks)."""

    def __init__(self, path: str = "state.json"):
        self.path = path
        self.symbols: Dict[str, SymbolState] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path) as f:
                raw = json.load(f)
            self.symbols = {k: SymbolState(**v) for k, v in raw.items()}

    def save(self):
        with open(self.path, "w") as f:
            json.dump({k: asdict(v) for k, v in self.symbols.items()}, f, indent=2)

    def get(self, symbol: str) -> SymbolState:
        if symbol not in self.symbols:
            self.symbols[symbol] = SymbolState()
        return self.symbols[symbol]
