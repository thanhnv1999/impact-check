import os
import stat
import sys
from pathlib import Path

import click

from . import analyzer, context_finder, debug, git_collector, reporter
from .providers.factory import PROVIDERS, get_provider


def _load_dotenv():
    """Load .env — project-level first, then tool's own directory as global fallback."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    # 1. Project-level: walk up from cwd to git root
    cwd = Path.cwd()
    for directory in [cwd, *cwd.parents]:
        env_file = directory / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=False)
            break
        if (directory / ".git").exists():
            break

    # 2. Global fallback: tool's own directory (d:\tool\.env)
    global_env = Path(__file__).parent.parent / ".env"
    if global_env.exists():
        load_dotenv(global_env, override=False)


_load_dotenv()

PROVIDER_NAMES = list(PROVIDERS.keys())


@click.group(invoke_without_command=True)
@click.pass_context
@click.option("--root", default=".", show_default=True, help="Project root directory to scan")
@click.option(
    "--provider", "-p",
    default="claude",
    show_default=True,
    type=click.Choice(PROVIDER_NAMES, case_sensitive=False),
    help="AI provider to use for analysis",
)
@click.option("--model", "-m", default=None, help="Override default model for the chosen provider")
@click.option("--dry-run", is_flag=True, help="Chỉ thu thập dữ liệu và ghi log, không gọi AI")
def main(ctx, root: str, provider: str, model: str, dry_run: bool):
    """AI-powered change impact analyzer.

    Supports multiple AI providers:

    \b
      impact-check                        # Claude (default)
      impact-check -p gpt                 # GPT-4o
      impact-check -p gemini              # Gemini 2.5 Flash
      impact-check -p grok                # Grok 3
      impact-check -p ollama              # Ollama local (llama3)
      impact-check -p ollama -m mistral   # Ollama with custom model
      impact-check --dry-run              # Chỉ ghi log, không gọi AI
    """
    if ctx.invoked_subcommand is not None:
        return

    if not dry_run:
        try:
            ai_provider = get_provider(provider, model)
        except (EnvironmentError, ImportError) as exc:
            reporter.print_error(str(exc))
            _print_setup_hint(provider)
            sys.exit(1)

    # 1. Collect staged changes
    changes = None
    with reporter.step("Collecting git changes"):
        try:
            changes = git_collector.get_staged_changes(root)
        except RuntimeError as exc:
            reporter.print_error(str(exc))
            sys.exit(1)

    if not changes.files:
        reporter.print_info("No staged changes found. Run 'git add <files>' first.")
        sys.exit(0)

    # 2. Find related files
    changed_paths = [f.path for f in changes.files]
    deleted_contents = {
        f.path.replace("\\", "/"): f.content
        for f in changes.files
        if f.status == "D" and f.content
    }
    with reporter.step("Scanning project for dependencies"):
        related = context_finder.find_related_files(
            changed_paths, root, deleted_contents or None
        )
        test_files = context_finder.find_test_files(changed_paths, root)
        structure = context_finder.get_project_structure(root)

    # Log dữ liệu tìm được
    debug.init()
    _log_scan_results(changes, related, test_files)

    if dry_run:
        prompt = analyzer.build_prompt(changes, related, structure, test_files)
        debug.section("System prompt gửi đi", analyzer.SYSTEM_PROMPT)
        debug.section("User prompt gửi đi", prompt)
        log_path = Path(__file__).parent.parent / "impact_check.log"
        reporter.print_info(f"Dry-run: đã ghi log tại {log_path}")
        reporter.print_info("Kiểm tra file log xong, chạy lại không có --dry-run để gọi AI.")
        sys.exit(0)

    # 3. Analyze with chosen AI
    analysis = None
    with reporter.step(f"Analyzing impact with {provider.upper()} AI"):
        try:
            analysis = analyzer.analyze(changes, related, structure, ai_provider, test_files)
        except Exception as exc:
            reporter.print_error(f"AI analysis failed: {exc}")
            sys.exit(1)

    # 4. Print report
    reporter.print_report(analysis, changes)


@main.command()
@click.argument("repo_path", default=".")
def install(repo_path: str):
    """Install impact-check as a pre-commit hook in REPO_PATH."""
    git_dir = os.path.join(repo_path, ".git")
    if not os.path.isdir(git_dir):
        reporter.print_error(f"Not a git repository: {repo_path}")
        sys.exit(1)

    hook_path = os.path.join(git_dir, "hooks", "pre-commit")
    hook_script = "#!/bin/sh\nimpact-check\nexit $?\n"

    with open(hook_path, "w", newline="\n") as fh:
        fh.write(hook_script)

    current = os.stat(hook_path).st_mode
    os.chmod(hook_path, current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    reporter.print_info(f"Pre-commit hook installed: {hook_path}")


def _log_scan_results(changes, related: dict, test_files: list) -> None:
    # Changed files
    lines = []
    for f in changes.files:
        lines.append(f"  [{f.status}] {f.path}")
    debug.section("Files thay đổi (staged)", "\n".join(lines))

    # Related files
    lines = []
    for changed_path, refs in related.items():
        if refs:
            lines.append(f"\n  {changed_path}")
            for ref in refs:
                label = "(indirect)" if ref.get("transitive") else "(direct) "
                lines.append(f"    {label}  {ref['path']}")
    if lines:
        debug.section("Files liên quan tìm được", "\n".join(lines))
    else:
        debug.section("Files liên quan tìm được", "  Không tìm thấy file liên quan nào.")

    # Test files
    if test_files:
        lines = [f"  {tf['path']}" for tf in test_files]
        debug.section("Test files tìm được", "\n".join(lines))
    else:
        debug.section("Test files tìm được", "  Không tìm thấy file test nào.")


def _print_setup_hint(provider: str) -> None:
    hints = {
        "claude":  "Set ANTHROPIC_API_KEY=sk-ant-... | pip install anthropic",
        "gpt":     "Set OPENAI_API_KEY=sk-...        | pip install openai",
        "gemini":  "Set GEMINI_API_KEY=AI...          | pip install google-genai",
        "grok":    "Set GROK_API_KEY=xai-...          | pip install openai",
        "ollama":  "Start Ollama: https://ollama.com  | pip install openai",
    }
    hint = hints.get(provider, "")
    if hint:
        reporter.print_info(f"Setup: {hint}")


if __name__ == "__main__":
    main()
