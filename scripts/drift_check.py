#!/usr/bin/env python3
"""纪律 6：推进 ref，跑基线机检，再重生成并要求文本 diff 为空。

    python3 scripts/drift_check.py --target high-school-ai-tutor
    python3 scripts/drift_check.py --target stub --repo /path/to/checkout
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.adapter import load_adapter, path_map
from core.library import dump_db
from core.scaffold import main as scaffold_main
from core.validate import run_validate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="推进目标 ref 并检查生成物没有漂移")
    parser.add_argument("--target", default="high-school-ai-tutor")
    parser.add_argument("--repo", type=Path, default=None)
    parser.add_argument("--pipeline-root", type=Path, default=ROOT)
    parser.add_argument("--skip-advance", action="store_true")
    args = parser.parse_args(argv)
    try:
        adapter = load_adapter(args.pipeline_root, args.target)
    except SystemExit as exc:
        return int(exc.code)
    repo = args.repo or _clone(adapter, args.pipeline_root)
    if not args.skip_advance:
        code = advance_ref(args.pipeline_root, args.target, repo)
        if code != 0:
            return code
        adapter = load_adapter(args.pipeline_root, args.target)
    return regenerate_gate(args.pipeline_root, adapter, repo)


def advance_ref(pipeline_root: Path, target: str, repo: Path) -> int:
    adapter = load_adapter(pipeline_root, target)
    head = remote_head(repo)
    last_green = str(adapter.config.get("last_green") or adapter.config["ref"])
    _checkout(repo, head)
    code = run_validate(adapter, repo, str(adapter.config["baseline_chapter"]))
    if code != 0:
        print(f"基线机检失败，ref 停在 {adapter.config['ref']}，检出回到 last-green {last_green}", file=sys.stderr)
        _checkout(repo, last_green)
        return code
    _write_ref(adapter.target_yaml, head)
    print(f"ref 已钉到 {head}")
    _restore_db_bytes(repo, path_map(adapter, repo)["graph_db"])
    return 0


def regenerate_gate(pipeline_root: Path, adapter, repo: Path) -> int:
    mapped = path_map(adapter, repo)
    before = dump_db(mapped["graph_db"]) if mapped["graph_db"].is_file() else ""
    code = scaffold_main([
        "--all",
        "--repo",
        str(repo),
        "--target",
        adapter.name,
        "--apply",
        "--pipeline-root",
        str(pipeline_root),
    ])
    if code != 0:
        return code
    after = dump_db(mapped["graph_db"]) if mapped["graph_db"].is_file() else ""
    if before and after != before:
        print("graph.db 的 SQL dump 与重生成前不一致", file=sys.stderr)
        return 1
    if text_diff(repo) != 0:
        print("重生成后文本 diff 不为空", file=sys.stderr)
        return 1
    print("重生成后文本 diff 为空。")
    return 0


def remote_head(repo: Path) -> str:
    origin = subprocess.run(
        ["git", "-C", str(repo), "remote", "get-url", "origin"],
        check=False,
        capture_output=True,
        text=True,
    )
    if origin.returncode == 0:
        fetched = subprocess.run(["git", "-C", str(repo), "fetch", "origin"], check=False)
        if fetched.returncode != 0:
            print("git fetch 失败", file=sys.stderr)
            raise SystemExit(fetched.returncode or 1)
        ref = "origin/main"
    else:
        ref = "main"
    show = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", ref],
        check=False,
        capture_output=True,
        text=True,
    )
    if show.returncode != 0:
        print(show.stderr, file=sys.stderr)
        raise SystemExit(show.returncode or 1)
    return show.stdout.strip()


def text_diff(repo: Path) -> int:
    completed = subprocess.run(
        ["git", "-C", str(repo), "diff", "--exit-code", "--", ".", ":(exclude)*.db"],
        check=False,
    )
    return completed.returncode


def _checkout(repo: Path, rev: str) -> None:
    completed = subprocess.run(
        ["git", "-C", str(repo), "checkout", "--force", "--detach", rev],
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode or 1)


def _write_ref(path: Path, rev: str) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^ref:\s*\S+", f"ref: {rev}", text, count=1)
    text = re.sub(r"(?m)^last_green:\s*\S+", f"last_green: {rev}", text, count=1)
    path.write_text(text, encoding="utf-8")


def _restore_db_bytes(repo: Path, db: Path) -> None:
    if not db.is_file():
        return
    relative = db.relative_to(repo)
    subprocess.run(["git", "-C", str(repo), "checkout", "--", str(relative)], check=False)


def _clone(adapter, pipeline_root: Path) -> Path:
    url = str(adapter.config["repo"])
    if "://" not in url or url.startswith("stub:"):
        print("这个适配器没有可克隆的远程。请传 --repo。", file=sys.stderr)
        raise SystemExit(2)
    destination = pipeline_root / ".cache" / adapter.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if (destination / ".git").is_dir():
        return destination
    completed = subprocess.run(["git", "clone", url, str(destination)], check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode or 1)
    return destination


if __name__ == "__main__":
    sys.exit(main())
