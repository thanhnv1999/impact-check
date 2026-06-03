"""
Secret scanner cho pre-commit hook.
Quét staged files tìm API key, password, token bị hardcode.
Chạy hoàn toàn local — không cần network, không cần AI.
"""
import re
import subprocess
from pathlib import Path

from rich.console import Console

console = Console()

# (label, regex, severity)
PATTERNS = [
    # AI providers
    ("Anthropic API Key",  r"sk-ant-[a-zA-Z0-9\-]{20,}",                                    "HIGH"),
    ("OpenAI API Key",     r"sk-(?:proj|[a-zA-Z0-9])-[a-zA-Z0-9\-_]{40,}",                 "HIGH"),
    ("Gemini API Key",     r"AIza[0-9A-Za-z_\-]{35}",                                        "HIGH"),
    ("Grok API Key",       r"xai-[a-zA-Z0-9]{20,}",                                          "HIGH"),
    # Cloud & infra
    ("AWS Access Key",     r"AKIA[0-9A-Z]{16}",                                              "HIGH"),
    ("Private Key",        r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY",                       "HIGH"),
    # Dev tools
    ("GitHub Token",       r"ghp_[a-zA-Z0-9]{36,}",                                          "HIGH"),
    ("Stripe Live Key",    r"sk_live_[a-zA-Z0-9]{24,}",                                      "HIGH"),
    ("Slack Bot Token",    r"xoxb-[0-9]+-[0-9]+-[a-zA-Z0-9]+",                              "HIGH"),
    # Generic hardcode (có quotes)
    ("Hardcoded password", r"""(?i)(?<![a-zA-Z])pass(?:word|wd|phrase)?\s*[:=]\s*["'][^"'\s]{4,}["']""",  "MED"),
    ("Hardcoded secret",   r"""(?i)(?:secret|api_key|apikey)\s*[:=]\s*["'][^"'\s]{4,}["']""",              "MED"),
    ("Hardcoded token",    r"""(?i)(?:access_token|api_token|auth_token)\s*[:=]\s*["'][^"'\s]{8,}["']""",  "MED"),
    ("Private Key (var)",  r"""(?i)private[_\-]?key\s*[:=]\s*["'][^"'\s]{4,}["']""",                      "MED"),
    # YAML/ENV không có quotes
    ("YAML credential",    r"""(?i)^[ \t]*(?:password|passwd|secret|api_key|private_key|token|auth_key)\s*:\s*(?!['"{\$<\s#])[\S]{6,}""", "MED"),
]

_COMPILED = [(label, re.compile(pattern), sev) for label, pattern, sev in PATTERNS]

SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".eot",
    ".mp4", ".mp3", ".zip", ".tar", ".gz", ".pdf",
    ".pyc", ".pyo", ".class", ".jar", ".so", ".dll", ".exe",
}

SKIP_FILENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Pipfile.lock", "composer.lock",
}


def _staged_files() -> list:
    result = subprocess.run(
        ["git", "diff", "--staged", "--name-only"],
        capture_output=True, text=True,
    )
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


def _staged_content(filepath: str):
    result = subprocess.run(
        ["git", "show", f":{filepath}"],
        capture_output=True, text=True, encoding="utf-8", errors="ignore",
    )
    return result.stdout if result.returncode == 0 else None


def run_guard() -> int:
    """Trả về 0 nếu sạch, 1 nếu phát hiện vấn đề."""
    staged = _staged_files()
    if not staged:
        console.print("[dim]🔒 guard: không có file staged[/dim]")
        return 0

    findings = []  # (filepath, lineno, line_display, label, severity)

    # Kiểm tra file .env (và variants) bị stage nhầm
    for f in staged:
        name = Path(f).name
        if name == ".env" or name.startswith(".env."):
            findings.append((f, None, None, "File .env đang được stage — nên có trong .gitignore", "HIGH"))

    # Quét nội dung từng file
    for filepath in staged:
        name = Path(filepath).name
        ext  = Path(filepath).suffix.lower()

        if ext in SKIP_EXTENSIONS or name in SKIP_FILENAMES or name == ".env" or name.startswith(".env."):
            continue

        content = _staged_content(filepath)
        if not content:
            continue

        for lineno, line in enumerate(content.splitlines(), start=1):
            # Dòng có # noguard hoặc // noguard → bỏ qua
            if re.search(r"(?:#|//)\s*noguard\s*$", line, re.IGNORECASE):
                continue

            # Dòng comment thuần → skip MED, vẫn giữ HIGH (key thật trong comment vẫn nguy hiểm)
            is_comment = bool(re.match(r"^\s*(?:#|//|/\*|\*)", line))

            for label, pattern, sev in _COMPILED:
                if is_comment and sev == "MED":
                    continue
                if pattern.search(line):
                    display = line.strip()
                    if len(display) > 120:
                        display = display[:120] + "..."
                    findings.append((filepath, lineno, display, label, sev))
                    break  # 1 finding per line

    if not findings:
        console.print("[green]🔒 impact-check guard: OK — không phát hiện thông tin nhạy cảm[/green]")
        return 0

    has_high = any(sev == "HIGH" for *_, sev in findings)

    # Header phản ánh đúng severity ngay từ đầu
    console.print()
    if has_high:
        console.print("[bold red]🔒 impact-check guard: Phát hiện thông tin nhạy cảm — commit bị chặn[/bold red]")
    else:
        console.print("[bold yellow]🔒 impact-check guard: Cảnh báo (commit vẫn tiếp tục)[/bold yellow]")
    console.print()

    for filepath, lineno, display, label, sev in findings:
        icon      = "[red]✗[/red]"      if sev == "HIGH" else "[yellow]⚠[/yellow]"
        sev_style = "bold red"          if sev == "HIGH" else "bold yellow"
        if lineno:
            console.print(f"  {icon} [bold]{filepath}[/bold] (dòng {lineno})")
            console.print(f"    [dim]{display}[/dim]")
        else:
            console.print(f"  {icon} [bold]{filepath}[/bold]")
        console.print(f"    → [{sev_style}]{label}[/{sev_style}]")
        console.print()

    if has_high:
        console.print("[bold red]Xóa thông tin nhạy cảm trước khi commit lại.[/bold red]")
        console.print("[dim]Bỏ qua (không khuyến khích): git commit --no-verify[/dim]")
    else:
        console.print("[yellow]Xem xét sửa các cảnh báo trên.[/yellow]")
    console.print()
    return 1 if has_high else 0
