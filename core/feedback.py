#!/usr/bin/env python3
"""上线反馈环：别名补录表，以及薄弱点频率。

补录表来自目标仓库 records.py unmatched（表头即「频次 | 原文 | 建议补录为」）。
weak 用来看下一章先补哪里。

    python3 core/feedback.py --repo <high repo>
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from core.adapter import load_adapter, path_map


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="打印别名补录表和薄弱点")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--target", default="high-school-ai-tutor")
    parser.add_argument("--file", type=Path, default=None, help="records.jsonl，缺省用对方脚本的默认路径")
    parser.add_argument("--pipeline-root", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.pipeline_root or Path(__file__).resolve().parent.parent
    try:
        adapter = load_adapter(root, args.target)
    except SystemExit as exc:
        return int(exc.code)
    script = path_map(adapter, args.repo).get("records_script")
    if script is None or not script.is_file():
        print("target.yaml 没有可用的 records_script", file=sys.stderr)
        return 2
    code = _run(script, "unmatched", args.file)
    print()
    return max(code, _run(script, "weak", args.file))


def _run(script: Path, command: str, records: Path | None) -> int:
    argv = [sys.executable, str(script), command]
    if records is not None:
        argv.extend(["--file", str(records)])
    completed = subprocess.run(argv, check=False)
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
