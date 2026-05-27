"""At-a-glance account dashboard for monitoring the agent.

    python scripts/status.py            # one-shot snapshot
    python scripts/status.py --loop     # live, self-refreshing (every 15s)
    python scripts/status.py --loop 30  # refresh every 30s

Shows equity/cash, holdings with up/down P&L, resting orders (protection +
pending entries), and recent fills (what was bought/sold). Read-only.
"""

import argparse
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

logger.remove()  # keep the dashboard clean

from rich import box  # noqa: E402
from rich.console import Console, Group  # noqa: E402
from rich.live import Live  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402

from config.config import get_settings  # noqa: E402
from src.core.types import OrderSide, OrderType  # noqa: E402
from src.execution.brokers.alpaca_broker import AlpacaBroker  # noqa: E402

console = Console()


def _pnl_markup(value: float) -> str:
    color = "green" if value >= 0 else "red"
    arrow = "▲" if value >= 0 else "▼"
    return f"[{color}]{arrow} {value:+,.2f}[/]"


def _order_role(o) -> str:
    if o.side == OrderSide.BUY:
        return "entry (limit)" if o.order_type == OrderType.LIMIT else "entry"
    if o.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
        return "stop-loss"
    return "take-profit"


def _summary(pf) -> Panel:
    total = sum(p.unrealized_pnl for p in pf.positions.values())
    invested = sum(p.market_value for p in pf.positions.values())
    text = (
        f"[bold]equity[/] ${pf.equity:,.0f}    "
        f"[bold]cash[/] ${pf.cash:,.0f}    "
        f"[bold]invested[/] ${invested:,.0f}    "
        f"[bold]open P&L[/] {_pnl_markup(total)}    "
        f"[bold]positions[/] {pf.position_count}"
    )
    return Panel(text, title=f"autostock paper — {datetime.now():%Y-%m-%d %H:%M:%S}", box=box.ROUNDED)


def _positions_table(pf) -> Table:
    t = Table(title="Holdings", box=box.SIMPLE_HEAVY, title_justify="left", expand=False)
    t.add_column("Sym", style="bold cyan")
    t.add_column("Qty", justify="right")
    t.add_column("Avg", justify="right")
    t.add_column("Now", justify="right")
    t.add_column("P&L $", justify="right")
    t.add_column("P&L %", justify="right")
    if not pf.positions:
        t.add_row("—", "", "", "", "", "")
        return t
    for sym, p in sorted(pf.positions.items()):
        pct = (p.current_price / p.avg_entry_price - 1) * 100 if p.avg_entry_price else 0.0
        color = "green" if p.unrealized_pnl >= 0 else "red"
        t.add_row(
            sym, f"{p.qty:.0f}", f"{p.avg_entry_price:.2f}", f"{p.current_price:.2f}",
            _pnl_markup(p.unrealized_pnl), f"[{color}]{pct:+.2f}%[/]",
        )
    return t


def _orders_table(opens) -> Table:
    t = Table(title="Resting orders", box=box.SIMPLE_HEAVY, title_justify="left", expand=False)
    t.add_column("Sym", style="bold cyan")
    t.add_column("Side")
    t.add_column("Role")
    t.add_column("Price", justify="right")
    if not opens:
        t.add_row("—", "", "none", "")
        return t
    for o in sorted(opens, key=lambda x: (x.symbol, _order_role(x))):
        price = o.limit_price if o.limit_price is not None else o.stop_price
        side_color = "green" if o.side == OrderSide.BUY else "red"
        t.add_row(o.symbol, f"[{side_color}]{o.side.value}[/]", _order_role(o), f"{price:.2f}")
    return t


def _fills_table(client) -> Table:
    t = Table(title="Recent fills (bought / sold)", box=box.SIMPLE_HEAVY, title_justify="left", expand=False)
    t.add_column("When")
    t.add_column("Side")
    t.add_column("Qty", justify="right")
    t.add_column("Sym", style="bold cyan")
    t.add_column("Fill", justify="right")
    try:
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        orders = client.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=50))
        fills = [o for o in orders if o.filled_at and float(o.filled_qty or 0) > 0]
        fills.sort(key=lambda o: o.filled_at, reverse=True)
    except Exception as e:
        t.add_row("err", str(e)[:30], "", "", "")
        return t
    if not fills:
        t.add_row("—", "", "", "none", "")
        return t
    for o in fills[:8]:
        side = str(o.side).split(".")[-1].upper()
        color = "green" if side == "BUY" else "red"
        t.add_row(
            o.filled_at.strftime("%m-%d %H:%M"), f"[{color}]{side}[/]",
            f"{float(o.filled_qty):.0f}", o.symbol, f"{float(o.filled_avg_price or 0):.2f}",
        )
    return t


def render(broker, client) -> Group:
    pf = broker.get_portfolio_state()
    return Group(
        _summary(pf),
        _positions_table(pf),
        _orders_table(broker.get_open_orders()),
        _fills_table(client),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="autostock account dashboard")
    parser.add_argument(
        "--loop", nargs="?", const=15, type=int, default=None,
        help="self-refresh every N seconds (default 15)",
    )
    args = parser.parse_args()

    s = get_settings()
    broker = AlpacaBroker(api_key=s.alpaca_api_key, secret_key=s.alpaca_secret_key, paper=s.broker.paper)
    client = broker._client

    if args.loop is None:
        console.print(render(broker, client))
        return

    with Live(render(broker, client), console=console, screen=True, refresh_per_second=4) as live:
        try:
            while True:
                time.sleep(args.loop)
                live.update(render(broker, client))
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
