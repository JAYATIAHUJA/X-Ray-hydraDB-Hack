from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

RECORD_SEPARATOR = "\x1e"
FIELD_SEPARATOR = "\x1f"
DEPENDS_TRAILER = "Depends-On:"

GIT_LOG_FORMAT = "--format=%x1e%H%x1f%at%x1f%ae%x1f%s%x1f%b"
"""Pass this to ``git log --name-only`` to produce input this adapter parses.

Records are separated by 0x1e so commit bodies with blank lines cannot split a
commit. Optional ``Depends-On: <module>[, <module>]`` trailers in the body become
explicit ``dependency_keys``.
"""


def git_log_rows(
    path: Path,
    *,
    module_prefixes: Mapping[str, str],
) -> tuple[dict[str, object], ...]:
    """Parse ``git log --name-only`` output (see ``GIT_LOG_FORMAT``) into ``code_records`` rows.

    Header per commit: ``<sha>\x1f<epoch>\x1f<author_email>\x1f<subject>[\x1f<body>]``
    followed by changed file paths. Legacy input separated by blank lines (no 0x1e)
    is still accepted for the header-plus-paths shape.
    """
    text = path.read_text(encoding="utf-8")
    blocks = text.split(RECORD_SEPARATOR) if RECORD_SEPARATOR in text else text.split("\n\n")
    rows: list[dict[str, object]] = []
    for block in blocks:
        raw_lines = block.splitlines()
        lines = [line.strip() for line in raw_lines if line.strip()]
        if not lines:
            continue
        header = lines[0].split(FIELD_SEPARATOR)
        if len(header) < 4:
            raise ValueError("git log header must contain sha, epoch, author, and subject")
        sha, epoch, author, subject = header[:4]
        body = header[4] if len(header) > 4 else ""
        # Body lines (until the first path) may follow the header when the body is
        # multi-line; everything that is not a path is treated as body text.
        body_lines, path_lines = _split_body_and_paths(lines[1:], module_prefixes)
        full_body = "\n".join(part for part in (body, *body_lines) if part)
        rows.append(
            {
                "sha": sha,
                "occurred_at_epoch": int(epoch),
                "author_id": author.lower(),
                "message": subject,
                "module_keys": _modules_for_paths(path_lines, module_prefixes),
                "dependency_keys": _dependency_keys(full_body),
            }
        )
    return tuple(rows)


def _split_body_and_paths(
    lines: list[str], module_prefixes: Mapping[str, str]
) -> tuple[list[str], list[str]]:
    """Heuristic-free split: a line is a path if it contains '/' or a '.' extension."""
    body: list[str] = []
    paths: list[str] = []
    for line in lines:
        if "/" in line or ("." in line and " " not in line):
            paths.append(line)
        else:
            body.append(line)
    return body, paths


def _dependency_keys(body: str) -> tuple[str, ...]:
    keys: set[str] = set()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith(DEPENDS_TRAILER):
            for part in stripped[len(DEPENDS_TRAILER) :].split(","):
                key = part.strip().removeprefix("module:")
                if key:
                    keys.add(key)
    return tuple(sorted(keys))


def _modules_for_paths(paths: list[str], module_prefixes: Mapping[str, str]) -> tuple[str, ...]:
    modules = {
        module
        for path in paths
        for prefix, module in module_prefixes.items()
        if path == prefix.rstrip("/") or path.startswith(prefix.rstrip("/") + "/")
    }
    return tuple(sorted(modules))
