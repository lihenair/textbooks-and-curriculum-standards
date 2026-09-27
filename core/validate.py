#!/usr/bin/env python3
"""对钉住的检出跑对方 check.py、run.sh，以及 graph init + topo。

    python3 core/validate.py --repo <high repo> --chapter chem-bx1-ch1
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parent.parent
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

from core.adapter import load_adapter, path_map
from core.library import load_seeds, parse_seeds


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="跑目标仓库的三道机检，并核对拓扑没有丢掉正式节点")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--chapter", required=True)
    parser.add_argument("--target", default="high-school-ai-tutor")
    parser.add_argument("--pipeline-root", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.pipeline_root or Path(__file__).resolve().parent.parent
    try:
        adapter = load_adapter(root, args.target)
    except SystemExit as exc:
        return int(exc.code)
    return run_validate(adapter, args.repo, args.chapter)


def run_validate(adapter, repo: Path, chapter: str) -> int:
    mapped = path_map(adapter, repo)
    steps = (
        [sys.executable, str(mapped["check_script"])],
        ["bash", str(mapped["run_script"])],
    )
    for command in steps:
        completed = subprocess.run(command, cwd=repo, check=False)
        if completed.returncode != 0:
            print(f"机检失败：{' '.join(command)}", file=sys.stderr)
            return completed.returncode or 1
    canon_sync = Path(repo) / str(adapter.config["skill_dir"]) / "scripts" / "canon_sync.py"
    if canon_sync.is_file():
        synced = subprocess.run([sys.executable, str(canon_sync)], cwd=repo, check=False)
        if synced.returncode != 0:
            print("canon_sync 对账失败", file=sys.stderr)
            return synced.returncode or 1
    init = subprocess.run(
        [sys.executable, str(mapped["graph_script"]), "init", "--db", str(mapped["graph_db"])],
        cwd=repo,
        check=False,
    )
    if init.returncode != 0:
        print("graph.py init 失败", file=sys.stderr)
        return init.returncode or 1
    topo = subprocess.run(
        [
            sys.executable,
            str(mapped["graph_script"]),
            "topo",
            "--chapter",
            chapter,
            "--db",
            str(mapped["graph_db"]),
        ],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if topo.returncode != 0:
        print(topo.stderr, file=sys.stderr)
        print("graph.py topo 失败", file=sys.stderr)
        return topo.returncode or 1
    ordered = [line.split("\t", 1)[0] for line in topo.stdout.splitlines() if line.strip()]
    missing = _missing_formal(adapter, mapped, chapter, ordered)
    if missing:
        print(f"拓扑丢掉了正式节点（实线边有环或端点被静默忽略）：{'、'.join(missing)}", file=sys.stderr)
        return 1
    print(f"三道机检通过：{chapter}")
    return 0


def _missing_formal(adapter, mapped, chapter: str, ordered: list[str]) -> list[str]:
    seeds_cfg = adapter.config["seeds"]
    seeds_path = mapped["graph_seeds"]
    if seeds_path.is_file():
        seeds = load_seeds(seeds_path, seeds_cfg["nodes_var"], seeds_cfg["edges_var"])
    elif mapped["graph_script"].is_file():
        seeds = parse_seeds(
            mapped["graph_script"].read_text(encoding="utf-8"),
            seeds_cfg["nodes_var"],
            seeds_cfg["edges_var"],
        )
    else:
        return []
    formal = [node.id for node in seeds.nodes if node.chapter_id == chapter and not node.grey]
    if not formal:
        print(f"种子里没有章 {chapter} 的正式节点——先 scaffold 入库再 validate", file=sys.stderr)
        return ["该章未入库"]
    return [node_id for node_id in formal if node_id not in ordered]


if __name__ == "__main__":
    sys.exit(main())
