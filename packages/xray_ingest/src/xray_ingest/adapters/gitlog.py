from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


def git_log_rows(
    path: Path,
    *,
    module_prefixes: Mapping[str, str],
) -> tuple[dict[str, object], ...]:
    """Parse ``git log --name-only`` style text into rows accepted by ``code_records``.

    Expected commit header format:
    ``<sha>\x1f<epoch>\x1f<author_email>\x1f<subject>`` followed by changed file
    paths, with blank lines between commits.
    """
    rows: list[dict[str, object]] = []
    for block in path.read_text(encoding="utf-8").split("\n\n"):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        header = lines[0].split("\x1f")
        if len(header) != 4:
            raise ValueError("git log header must contain sha, epoch, author, and subject")
        sha, epoch, author, subject = header
        rows.append(
            {
                "sha": sha,
                "occurred_at_epoch": int(epoch),
                "author_id": author.lower(),
                "message": subject,
                "module_keys": _modules_for_paths(lines[1:], module_prefixes),
                "dependency_keys": (),
            }
        )
    return tuple(rows)


def _modules_for_paths(paths: list[str], module_prefixes: Mapping[str, str]) -> tuple[str, ...]:
    modules = {
        module
        for path in paths
        for prefix, module in module_prefixes.items()
        if path == prefix.rstrip("/") or path.startswith(prefix.rstrip("/") + "/")
    }
    return tuple(sorted(modules))
