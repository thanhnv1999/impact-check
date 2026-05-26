from datetime import datetime
from pathlib import Path

_log_path: Path = None


def init() -> None:
    global _log_path
    log_dir = Path(__file__).parent.parent  # d:\tool\
    _log_path = log_dir / "impact_check.log"
    _log_path.write_text(
        f"impact-check debug log\n"
        f"Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"{'=' * 70}\n",
        encoding="utf-8",
    )


def section(title: str, content: str) -> None:
    if _log_path is None:
        return
    with open(_log_path, "a", encoding="utf-8") as f:
        f.write(f"\n{'─' * 70}\n")
        f.write(f"  {title}\n")
        f.write(f"{'─' * 70}\n")
        f.write(content.rstrip())
        f.write("\n")
