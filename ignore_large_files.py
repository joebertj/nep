#!/usr/bin/env python3
"""Add repository files larger than the configured limit to .gitignore."""

from __future__ import annotations

import argparse
from pathlib import Path


def gitignore_escape(path: str) -> str:
    """Escape characters that have special meaning in gitignore patterns."""
    escaped = path.replace("\\", "\\\\")
    for char in ("*", "?", "["):
        escaped = escaped.replace(char, "\\" + char)
    if escaped.startswith(("#", "!")):
        escaped = "\\" + escaped
    if escaped.endswith(" "):
        escaped = escaped[:-1] + "\\ "
    return escaped


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Add files above a size threshold to the repository .gitignore."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="repository root (defaults to the directory containing this script)",
    )
    parser.add_argument(
        "--threshold-mb",
        type=float,
        default=100,
        help="decimal megabytes; files strictly larger than this are added (default: 100)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="show additions without changing .gitignore"
    )
    args = parser.parse_args()

    root = args.root.resolve()
    ignore_file = root / ".gitignore"
    if not ignore_file.is_file():
        parser.error(f"no .gitignore found at repository root: {root}")
    if args.threshold_mb <= 0:
        parser.error("--threshold-mb must be greater than zero")

    threshold_bytes = int(args.threshold_mb * 1_000_000)
    existing_text = ignore_file.read_text(encoding="utf-8")
    existing = {line.strip() for line in existing_text.splitlines() if line.strip()}
    # An existing root-level basename rule already ignores the anchored form too.
    existing_root_paths = {entry.lstrip("/") for entry in existing if not entry.startswith("!")}

    large_files: list[Path] = []
    for path in root.rglob("*"):
        if ".git" in path.relative_to(root).parts or not path.is_file() or path.is_symlink():
            continue
        try:
            if path.stat().st_size > threshold_bytes:
                large_files.append(path)
        except OSError:
            continue

    additions: list[str] = []
    for path in sorted(large_files):
        relative = "/" + path.relative_to(root).as_posix()
        pattern = gitignore_escape(relative)
        if pattern not in existing and relative.lstrip("/") not in existing_root_paths:
            additions.append(pattern)

    if additions:
        print("Adding to .gitignore:")
        for item in additions:
            print(f"  {item}")
        if not args.dry_run:
            with ignore_file.open("a", encoding="utf-8") as output:
                if existing_text and not existing_text.endswith("\n"):
                    output.write("\n")
                output.write("\n".join(additions) + "\n")
    else:
        print("No new ignore entries needed.")

    print(f"Scanned {len(large_files)} file(s) above {args.threshold_mb:g} MB.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
