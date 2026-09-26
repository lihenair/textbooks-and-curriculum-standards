#!/usr/bin/env python3
"""在 Obsidian 库里检索自己写的分析，跳过整段摘录。

    python3 core/find_notes.py --vault ~/库路径 --query 钠
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检索 Obsidian 笔记里的自写分析")
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    if not args.vault.is_dir():
        print(f"找不到库：{args.vault}", file=sys.stderr)
        return 2
    hits, skipped = search_vault(args.vault, args.query)
    lines = [f"# 检索：{args.query}", ""]
    if not hits:
        lines.append("没有命中自写分析。")
    for hit in hits:
        lines.append(f"## {hit['path']}")
        lines.extend(hit["excerpt"])
        lines.append("")
    if skipped:
        lines.append("跳过的摘录：")
        lines.extend(f"- {item}" for item in skipped)
    text = "\n".join(lines).rstrip() + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


def search_vault(vault: Path, query: str) -> tuple[list[dict], list[str]]:
    hits = []
    skipped = []
    for path in sorted(vault.rglob("*.md")):
        if any(part.startswith(".") for part in path.relative_to(vault).parts):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if query not in text:
            continue
        relative = str(path.relative_to(vault))
        if is_excerpt(text):
            skipped.append(relative)
            continue
        hits.append({"path": relative, "excerpt": excerpt(text, query)})
    return hits, skipped


def is_excerpt(text: str) -> bool:
    body = text
    matched = _FRONTMATTER.match(text)
    if matched:
        front = matched.group(1)
        if re.search(r"(?m)^(excerpt:\s*true|tags:.*课文摘录)", front):
            return True
        if "课文摘录" in front:
            return True
        body = text[matched.end() :]
    lines = [line for line in body.splitlines() if line.strip()]
    if not lines:
        return False
    quoted = [line for line in lines if line.strip().startswith(">")]
    return len(quoted) / len(lines) >= 0.6


def excerpt(text: str, query: str) -> list[str]:
    lines = text.splitlines()
    chosen: list[str] = []
    for index, line in enumerate(lines):
        if query not in line:
            continue
        start = max(0, index - 2)
        stop = min(len(lines), index + 3)
        chosen.extend(lines[start:stop])
        chosen.append("")
        if len(chosen) >= 24:
            break
    return chosen[:24]


if __name__ == "__main__":
    sys.exit(main())
