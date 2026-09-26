#!/usr/bin/env python3
"""把 graph.py 里的内联种子抽到 data/graph-seeds.py，init 改为读文件。

    python3 core/migrate_seeds.py --repo <high repo> [--apply]
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

from core.adapter import load_adapter, path_map
from core.library import SeedEdge, SeedNode, Seeds
from core.render import render


LOADER = '''def _load_seeds():
    """读取 data/graph-seeds.py。缺文件即失败，不回退到内联常量。"""
    import importlib.util

    seeds_path = SKILL_DIR / "data" / "graph-seeds.py"
    sys.dont_write_bytecode = True
    if not seeds_path.is_file():
        print(f"缺少 {seeds_path}", file=sys.stderr)
        raise SystemExit(2)
    spec = importlib.util.spec_from_file_location("graph_seeds", seeds_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SEED_NODES, module.SEED_EDGES


'''


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把内联 SEED 抽到 graph-seeds.py")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--target", default="high-school-ai-tutor")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--pipeline-root", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.pipeline_root or Path(__file__).resolve().parent.parent
    try:
        adapter = load_adapter(root, args.target)
    except SystemExit as exc:
        return int(exc.code)
    mapped = path_map(adapter, args.repo)
    script = mapped["graph_script"]
    seeds_path = mapped["graph_seeds"]
    if not script.is_file():
        print(f"找不到 {script}", file=sys.stderr)
        return 2
    source = script.read_text(encoding="utf-8")
    if _already_migrated(source):
        if seeds_path.is_file():
            print("已经在读 graph-seeds.py，无需再迁。")
            return 0
        print("graph.py 已改读种子文件，但文件不存在。", file=sys.stderr)
        return 1
    try:
        seeds = _seeds_from_source(source, adapter.config["seeds"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    seeds_text = render(adapter.templates["graph-seeds.py"], _context(seeds))
    if not seeds_text.endswith("\n"):
        seeds_text += "\n"
    new_source = _rewrite_script(source)
    if not args.apply:
        print(f"将写入 {seeds_path}")
        print(f"将改写 {script}")
        print("干跑结束，没有 --apply，未写入。")
        return 0
    seeds_path.parent.mkdir(parents=True, exist_ok=True)
    seeds_path.write_text(seeds_text, encoding="utf-8")
    script.write_text(new_source, encoding="utf-8")
    print(f"已写入 {seeds_path}")
    return 0


def _already_migrated(source: str) -> bool:
    return "_load_seeds" in source and "graph-seeds.py" in source


def _seeds_from_source(source: str, seeds_cfg: dict) -> Seeds:
    tree = ast.parse(source)
    found = {}
    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign):
            continue
        for target in stmt.targets:
            if isinstance(target, ast.Name) and target.id in {seeds_cfg["nodes_var"], seeds_cfg["edges_var"]}:
                found[target.id] = ast.literal_eval(stmt.value)
    if seeds_cfg["nodes_var"] not in found or seeds_cfg["edges_var"] not in found:
        raise ValueError("graph.py 里没有可抽取的 SEED_NODES / SEED_EDGES")
    nodes = [SeedNode(item[0], item[1], item[2], item[3], int(item[4])) for item in found[seeds_cfg["nodes_var"]]]
    edges = [SeedEdge(item[0], item[1], item[2]) for item in found[seeds_cfg["edges_var"]]]
    return Seeds(nodes, edges, {})


def _rewrite_script(source: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    spans = []
    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign):
            continue
        names = [target.id for target in stmt.targets if isinstance(target, ast.Name)]
        if "SEED_NODES" in names or "SEED_EDGES" in names:
            spans.append((stmt.lineno, stmt.end_lineno))
    if len(spans) < 2:
        raise ValueError("没有同时找到 SEED_NODES 和 SEED_EDGES")
    start = min(span[0] for span in spans)
    end = max(span[1] for span in spans)
    if start > 1 and lines[start - 2].lstrip().startswith("#"):
        start -= 1
    new_lines = lines[: start - 1] + [LOADER] + lines[end:]
    rewritten = "".join(new_lines)
    nodes_call = "        SEED_NODES,\n"
    edges_call = 'conn.executemany("INSERT INTO edges (src, dst, kind) VALUES (?, ?, ?)", SEED_EDGES)'
    if nodes_call not in rewritten or edges_call not in rewritten:
        raise ValueError("init_db 没有按预期引用 SEED_NODES / SEED_EDGES")
    rewritten = rewritten.replace(
        "    conn.executemany(\n        \"INSERT INTO nodes (id, subject, display_name, chapter_id, grey) VALUES (?, ?, ?, ?, ?)\",\n        SEED_NODES,\n",
        "    seed_nodes, seed_edges = _load_seeds()\n"
        "    conn.executemany(\n"
        "        \"INSERT INTO nodes (id, subject, display_name, chapter_id, grey) VALUES (?, ?, ?, ?, ?)\",\n"
        "        seed_nodes,\n",
        1,
    )
    rewritten = rewritten.replace(edges_call, edges_call.replace("SEED_EDGES", "seed_edges"), 1)
    return rewritten


def _context(seeds: Seeds) -> dict:
    return {
        "owned_later": [],
        "seed_nodes": [
            {
                "id": node.id,
                "subject": node.subject,
                "display": node.display,
                "chapter_id": node.chapter_id,
                "grey": node.grey,
            }
            for node in seeds.nodes
        ],
        "seed_edges": [
            {"src": edge.src, "dst": edge.dst, "kind": edge.kind}
            for edge in seeds.edges
        ],
    }


if __name__ == "__main__":
    sys.exit(main())
