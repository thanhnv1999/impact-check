import threading
import time
from contextlib import contextmanager

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()

_SEV_COLOR = {"HIGH": "bold red", "MED": "bold yellow", "LOW": "bold green"}
_SEV_ORDER = ["HIGH", "MED", "LOW"]


@contextmanager
def step(message: str):
    """Show a spinner with elapsed timer. Prints done + duration when finished."""
    start = time.time()
    stop_event = threading.Event()

    spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    spinner_state = {"i": 0}

    def _render_animated():
        elapsed = int(time.time() - start)
        mins, secs = divmod(elapsed, 60)
        char = spinner_chars[spinner_state["i"] % len(spinner_chars)]
        return Text.from_markup(
            f"[cyan]{char}[/cyan] {message} [dim]{mins:02d}:{secs:02d}[/dim]"
        )

    with Live(_render_animated(), console=console, refresh_per_second=4, transient=True) as live:
        def _updater():
            while not stop_event.is_set():
                spinner_state["i"] += 1
                live.update(_render_animated())
                time.sleep(0.25)

        t = threading.Thread(target=_updater, daemon=True)
        t.start()
        try:
            yield
        finally:
            stop_event.set()
            t.join(timeout=1)

    elapsed = time.time() - start
    mins, secs = divmod(int(elapsed), 60)
    console.print(f"[green]✓[/green] {message} [dim]({mins:02d}:{secs:02d})[/dim]")


def print_report(analysis: dict, git_changes) -> None:
    console.print()
    console.print(
        Panel.fit("[bold cyan]IMPACT ANALYSIS REPORT[/bold cyan]", border_style="cyan")
    )

    summary = analysis.get("summary", "")
    if summary:
        console.print(f"\n[bold]Tóm tắt:[/bold] {summary}")

    changed_names = ", ".join(f.path for f in git_changes.files)
    console.print(f"[dim]Files thay đổi: {changed_names}[/dim]\n")

    _print_affected_modules(analysis.get("affected_modules", []))
    _print_tests(analysis.get("tests_needed", []))
    _print_risks(analysis.get("risks", []))
    console.print()


def _print_affected_modules(modules: list) -> None:
    if not modules:
        return
    console.print("[bold yellow]  Module bị ảnh hưởng[/bold yellow]")
    table = _make_table("Mức độ", "Module", "Lý do")
    for m in _sort_by_severity(modules, "severity"):
        sev = m.get("severity", "LOW")
        table.add_row(Text(sev, style=_SEV_COLOR.get(sev, "")), m.get("name", ""), m.get("reason", ""))
    console.print(table)


def _print_tests(tests: list) -> None:
    if not tests:
        return
    console.print("[bold blue]  Cần test[/bold blue]")
    table = _make_table("Ưu tiên", "Loại", "Mô tả")
    for t in _sort_by_severity(tests, "priority"):
        pri = t.get("priority", "LOW")
        table.add_row(
            Text(pri, style=_SEV_COLOR.get(pri, "")),
            t.get("type", "").upper(),
            t.get("description", ""),
        )
    console.print(table)


def _print_risks(risks: list) -> None:
    if not risks:
        return
    console.print("[bold red]  Rủi ro[/bold red]")
    table = _make_table("Mức độ", "Vị trí", "Mô tả")
    for r in _sort_by_severity(risks, "level"):
        lvl = r.get("level", "LOW")
        table.add_row(
            Text(lvl, style=_SEV_COLOR.get(lvl, "")),
            r.get("location", ""),
            r.get("description", ""),
        )
    console.print(table)


def _make_table(*columns: str) -> Table:
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
    widths = [8, None, None]
    for col, width in zip(columns, widths):
        table.add_column(col, width=width)
    return table


def _sort_by_severity(items: list, key: str) -> list:
    return sorted(
        items,
        key=lambda x: _SEV_ORDER.index(x.get(key, "LOW")) if x.get(key, "LOW") in _SEV_ORDER else 9,
    )


def print_error(msg: str) -> None:
    console.print(f"[bold red]Error:[/bold red] {msg}")


def print_info(msg: str) -> None:
    console.print(f"[dim]{msg}[/dim]")
