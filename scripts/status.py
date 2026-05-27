"""Account snapshot for monitoring the agent.

    watch -n 20 python scripts/status.py

Prints equity/cash, positions with live P&L, and resting orders (incl. the
bracket/OCO protective legs). Read-only.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

logger.remove()  # keep the snapshot clean

from config.config import get_settings  # noqa: E402
from src.execution.brokers.alpaca_broker import AlpacaBroker  # noqa: E402


def main() -> None:
    s = get_settings()
    broker = AlpacaBroker(
        api_key=s.alpaca_api_key, secret_key=s.alpaca_secret_key, paper=s.broker.paper
    )
    pf = broker.get_portfolio_state()
    print(
        f"{datetime.now():%H:%M:%S}  equity ${pf.equity:,.0f}  cash ${pf.cash:,.0f}  "
        f"positions {pf.position_count}"
    )
    for sym, p in sorted(pf.positions.items()):
        print(
            f"  {sym:6} {p.qty:>5.0f} @ {p.avg_entry_price:>8.2f}  now {p.current_price:>8.2f}"
            f"  P&L {p.unrealized_pnl:>+8.2f}"
        )

    opens = broker.get_open_orders()
    if not opens:
        print("  resting orders: none")
        return
    print("  resting orders (protection / entries):")
    for o in sorted(opens, key=lambda x: x.symbol):
        price = o.limit_price if o.limit_price is not None else o.stop_price
        print(f"    {o.symbol:6} {o.side.value:4} {o.order_type.value:10} @ {price}")


if __name__ == "__main__":
    main()
