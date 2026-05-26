import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class ChangedFile:
    path: str
    status: str  # A=added, M=modified, D=deleted, R=renamed
    diff: str
    content: Optional[str]


@dataclass
class GitChanges:
    files: list
    raw_diff: str
    branch: str


def get_staged_changes(root: str = ".") -> GitChanges:
    branch = _run("git rev-parse --abbrev-ref HEAD", root).strip() or "HEAD"
    status_output = _run("git diff --staged --name-status", root)
    files = _parse_files(status_output, staged=True, root=root)
    raw_diff = _run("git diff --staged", root)
    return GitChanges(files=files, raw_diff=raw_diff, branch=branch)


def get_unstaged_changes(root: str = ".") -> GitChanges:
    branch = _run("git rev-parse --abbrev-ref HEAD", root).strip() or "HEAD"
    status_output = _run("git diff --name-status", root)
    files = _parse_files(status_output, staged=False, root=root)
    raw_diff = _run("git diff", root)
    return GitChanges(files=files, raw_diff=raw_diff, branch=branch)


def _parse_files(status_output: str, staged: bool, root: str) -> list:
    files = []
    for line in status_output.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0][0]
        path = parts[-1]

        diff_flag = "--staged" if staged else ""
        file_diff = _run(f'git diff {diff_flag} -- "{path}"', root)

        content = None
        if status != "D":
            try:
                if staged:
                    content = _run(f'git show ":{path}"', root)
                else:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
            except Exception:
                pass
        else:
            # Lấy content trước khi xóa để impact analysis vẫn tìm được importer
            try:
                content = _run(f'git show "HEAD:{path}"', root)
            except Exception:
                pass

        files.append(ChangedFile(path=path, status=status, diff=file_diff, content=content))
    return files


def _run(cmd: str, cwd: str = ".") -> str:
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        cwd=cwd,
    )
    if result.returncode != 0 and result.stderr.strip():
        raise RuntimeError(result.stderr.strip())
    return result.stdout
