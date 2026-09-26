#!/usr/bin/env python3
"""把 chapter.yaml 写成目标仓库里的正典追加、整章图、学习页和种子。

    python3 core/scaffold.py work/chapters/chem-bx1-ch2.yaml --repo <high repo> [--apply]
    python3 core/scaffold.py --all --repo <high repo> [--apply]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from core.adapter import load_adapter, path_map
from core.ir import TYPE_ZH, Chapter, Violation, load, solid_edges_stay_inside, zh_index
from core.library import (
    Seeds,
    canon_conflicts,
    graph_script_loads_seeds,
    library_identity,
    load_seeds,
    merge_canon,
    merge_seeds,
    outside_ids,
    parse_seeds,
    render_canon_block,
)
from core.render import render


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按 chapter.yaml 生成知识库资产")
    parser.add_argument("chapter", nargs="?", type=Path)
    parser.add_argument("--all", action="store_true", help="重生成 work/chapters 下的全部 yaml")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--target", default="high-school-ai-tutor")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--pipeline-root", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.pipeline_root or Path(__file__).resolve().parent.parent
    if args.all == bool(args.chapter):
        print("请指定一个 chapter.yaml，或使用 --all", file=sys.stderr)
        return 2
    try:
        adapter = load_adapter(root, args.target)
    except SystemExit as exc:
        return int(exc.code)
    _warn_ref(args.repo, str(adapter.config["ref"]))
    paths = _chapters(root, args.chapter, args.all)
    try:
        chapters = [load(path) for path in paths]
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not chapters:
        print("没有 chapter.yaml，跳过生成。")
        return 0
    problems, artifacts = plan(adapter, args.repo, chapters, root)
    if problems:
        for item in problems:
            print(item, file=sys.stderr)
        print("未写入任何文件。", file=sys.stderr)
        return 1
    if not args.apply:
        for label in artifacts["written"]:
            print(f"将写入 {label}")
        print(artifacts["snippet"])
        print("干跑结束，没有 --apply，未写入。")
        return 0
    _write(artifacts)
    init_code = _init_db(artifacts)
    if init_code != 0:
        return init_code
    _warn_order(artifacts, chapters)
    print(artifacts["snippet"])
    print(f"已写入 {len(artifacts['written'])} 个路径。")
    return 0


def plan(adapter, repo: Path, chapters: list[Chapter], pipeline_root: Path) -> tuple[list[Violation], dict]:
    problems: list[Violation] = []
    mapped = path_map(adapter, repo)
    graph_script = mapped["graph_script"]
    script_text = graph_script.read_text(encoding="utf-8") if graph_script.is_file() else ""
    if not graph_script_loads_seeds(script_text):
        problems.append(
            Violation(
                "graph.py",
                "init 必须读取 data/graph-seeds.py。先跑 python3 core/migrate_seeds.py --repo <high repo> --apply",
            )
        )
        return problems, {}
    seeds_cfg = adapter.config["seeds"]
    existing = load_seeds(mapped["graph_seeds"], seeds_cfg["nodes_var"], seeds_cfg["edges_var"])
    for chapter in chapters:
        problems.extend(solid_edges_stay_inside(chapter))
        canon_path = _skill_path(adapter, repo, chapter.canon_file)
        problems.extend(canon_conflicts(chapter, canon_path, adapter.templates["canon-line.txt"], render))
        problems.extend(library_identity(mapped["canon_dir"], chapter, canon_path))
    merged, merge_problems = merge_seeds(existing, chapters)
    problems.extend(merge_problems)
    if problems:
        return problems, {}
    rendered = _render_chapters(adapter, repo, chapters, merged, pipeline_root)
    problems.extend(_three_way(adapter, chapters, rendered))
    artifacts = {
        "ir": [_public_ir(chapter) for chapter in chapters],
        "chapters": rendered,
        "seeds": rendered["seeds_text"],
        "graph_script_text": script_text,
        "formal_ids": {chapter.chapter_id: [node.id for node in chapter.nodes] for chapter in chapters},
    }
    for chapter, chapter_artifacts in zip(chapters, rendered["chapters"]):
        found = adapter.checks.check(_public_ir(chapter), chapter_artifacts | {
            "seeds": rendered["seeds_text"],
            "graph_script_text": script_text,
        })
        for item in found or []:
            if not isinstance(item, Violation):
                problems.append(Violation(chapter.chapter_id, str(item)))
            else:
                problems.append(item)
    if problems:
        return problems, {}
    return [], rendered


def _render_chapters(adapter, repo, chapters, seeds: Seeds, pipeline_root: Path) -> dict:
    per_chapter = []
    canon_writes = []
    for chapter in chapters:
        canon_path = _skill_path(adapter, repo, chapter.canon_file)
        existing = canon_path.read_text(encoding="utf-8") if canon_path.exists() else ""
        kept = outside_ids(canon_path, chapter.chapter_id)
        emitting = [node for node in chapter.nodes if node.id not in kept]
        block = ""
        if emitting:
            block = _canon_block(adapter, chapter, emitting)
        canon_text = merge_canon(existing, chapter.chapter_id, block)
        graph_text = render(adapter.templates["chapter-graph.md"], _graph_context(chapter))
        pages = {}
        for node in chapter.nodes:
            pages[node.id] = render(adapter.templates["study-page.md"], _page_context(node))
            if not pages[node.id].endswith("\n"):
                pages[node.id] += "\n"
        snippet = render(adapter.templates["skill-snippet.md"], _snippet_context(chapter)).strip() + "\n"
        per_chapter.append({
            "chapter_id": chapter.chapter_id,
            "canon_path": str(canon_path),
            "canon_text": canon_text,
            "canon_block": block,
            "graph_path": str(_skill_path(adapter, repo, chapter.graph_doc)),
            "graph_doc": graph_text if graph_text.endswith("\n") else graph_text + "\n",
            "study_dir": str(path_map(adapter, repo)["study_pages_dir"] / chapter.chapter_id),
            "study_pages": pages,
            "snippet": snippet,
            "formal_ids": [node.id for node in chapter.nodes],
            "later_ids": [item.id for item in chapter.later],
        })
        canon_writes.append((canon_path, canon_text))
    seeds_text = render(adapter.templates["graph-seeds.py"], _seeds_context(seeds))
    if not seeds_text.endswith("\n"):
        seeds_text += "\n"
    mapped = path_map(adapter, repo)
    written = []
    for item in per_chapter:
        written.append(item["canon_path"])
        written.append(item["graph_path"])
        for node_id in item["study_pages"]:
            written.append(str(Path(item["study_dir"]) / f"{node_id}.md"))
    written.append(str(mapped["graph_seeds"]))
    written.append(str(mapped["graph_db"]))
    snippet_dir = pipeline_root / "work" / "snippets"
    return {
        "chapters": per_chapter,
        "seeds_text": seeds_text,
        "seeds_path": mapped["graph_seeds"],
        "graph_script": mapped["graph_script"],
        "graph_db": mapped["graph_db"],
        "snippet": "\n".join(item["snippet"].rstrip() for item in per_chapter) + "\n",
        "snippet_paths": [(snippet_dir / f"{item['chapter_id']}.md", item["snippet"]) for item in per_chapter],
        "written": written,
    }


def _three_way(adapter, chapters: list[Chapter], rendered: dict) -> list[Violation]:
    problems: list[Violation] = []
    seeds_cfg = adapter.config["seeds"]
    parsed = parse_seeds(rendered["seeds_text"], seeds_cfg["nodes_var"], seeds_cfg["edges_var"])
    by_id = {item["chapter_id"]: item for item in rendered["chapters"]}
    for chapter in chapters:
        item = by_id[chapter.chapter_id]
        formal = {node.id for node in chapter.nodes}
        seed_formal = {
            node.id
            for node in parsed.nodes
            if node.chapter_id == chapter.chapter_id and not node.grey
        }
        if seed_formal != formal:
            missing = "、".join(sorted(formal ^ seed_formal))
            problems.append(Violation(chapter.chapter_id, f"正典节点与种子不一致：{missing}"))
        for node in chapter.nodes:
            if node.id not in item["graph_doc"]:
                problems.append(Violation(node.path or node.id, "整章图缺少该节点"))
            if f"# id {node.id} {node.display}" not in item["canon_text"]:
                problems.append(Violation(node.path or node.id, "正典缺少指向显示名的 id 注释"))
        for later in chapter.later:
            if later.id not in item["graph_doc"]:
                problems.append(Violation(later.path, "整章图缺少灰节点"))
    return problems


def _canon_block(adapter, chapter: Chapter, nodes) -> str:
    partial = Chapter(**{**chapter.__dict__, "nodes": nodes})
    return render_canon_block(partial, adapter.templates["canon-line.txt"], render)


def _graph_context(chapter: Chapter) -> dict:
    sections = []
    for section in chapter.sections:
        sections.append({
            "title": section["title"],
            "nodes": [
                {
                    "id": node.id,
                    "graph_label": f"{node.display}（{TYPE_ZH[node.type]}）",
                    "type": node.type,
                }
                for node in section["nodes"]
            ],
        })
    return {
        "book": chapter.book,
        "chapter_no_zh": zh_index(chapter.chapter_no),
        "chapter_title": chapter.chapter_title,
        "entry_question": chapter.entry_question,
        "sections": sections,
        "later": [{"id": item.id, "display": item.display} for item in chapter.later],
        "solid_edges": [{"src": edge.src, "dst": edge.dst, "kind": edge.kind} for edge in chapter.edges],
        "combo_edges": [{"src": edge.src, "dst": edge.dst, "kind": edge.kind} for edge in chapter.combo],
        "has_later": bool(chapter.later),
    }


def _page_context(node) -> dict:
    l3 = node.l3.rstrip("。")
    return {
        "display": node.display,
        "l1": node.l1,
        "l2": node.l2,
        "l3_slot": f"{l3}。想深挖说深挖。",
        "example_slot": f"示例题非教材原题。{node.example}" if node.example else "（待补录：最小例子）",
        "pitfall_slot": node.pitfall or "（待补录：易错点）",
        "confusion_slot": node.confusion or "（待补录：易混辨析）",
        "self_test": f"哪一句说法符合「{node.display}」？要能做到：{node.l1}",
    }


def _snippet_context(chapter: Chapter) -> dict:
    return {
        "book": chapter.book,
        "chapter_no_zh": zh_index(chapter.chapter_no),
        "graph_doc": chapter.graph_doc,
        "chapter_title": chapter.chapter_title,
    }


def _seeds_context(seeds: Seeds) -> dict:
    return {
        "owned_later": [
            {"chapter_id": chapter_id, "ids": ids}
            for chapter_id, ids in seeds.owned_later.items()
        ],
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


def _public_ir(chapter: Chapter) -> dict:
    return {
        "chapter_id": chapter.chapter_id,
        "subject": chapter.subject,
        "book": chapter.book,
        "chapter_no": chapter.chapter_no,
        "chapter_title": chapter.chapter_title,
        "canon_chapter": chapter.canon_chapter,
        "nodes": [
            {
                "id": node.id,
                "display": node.display,
                "type": node.type,
                "example": node.example,
                "pitfall": node.pitfall,
                "confusion": node.confusion,
            }
            for node in chapter.nodes
        ],
        "edges": [{"src": edge.src, "dst": edge.dst, "kind": edge.kind} for edge in chapter.edges],
        "combo": [{"src": edge.src, "dst": edge.dst, "kind": edge.kind} for edge in chapter.combo],
        "later": [{"id": item.id, "display": item.display} for item in chapter.later],
    }


def _write(artifacts: dict) -> None:
    for item in artifacts["chapters"]:
        canon_path = Path(item["canon_path"])
        canon_path.parent.mkdir(parents=True, exist_ok=True)
        canon_path.write_text(item["canon_text"], encoding="utf-8")
        graph_path = Path(item["graph_path"])
        graph_path.parent.mkdir(parents=True, exist_ok=True)
        graph_path.write_text(item["graph_doc"], encoding="utf-8")
        study_dir = Path(item["study_dir"])
        study_dir.mkdir(parents=True, exist_ok=True)
        keep = set()
        for node_id, text in item["study_pages"].items():
            path = study_dir / f"{node_id}.md"
            path.write_text(text, encoding="utf-8")
            keep.add(path.name)
        for path in study_dir.glob("kp_*.md"):
            if path.name not in keep:
                path.unlink()
    seeds_path = Path(artifacts["seeds_path"])
    seeds_path.parent.mkdir(parents=True, exist_ok=True)
    seeds_path.write_text(artifacts["seeds_text"], encoding="utf-8")
    for path, text in artifacts["snippet_paths"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _init_db(artifacts: dict) -> int:
    script = artifacts["graph_script"]
    db = artifacts["graph_db"]
    completed = subprocess.run(
        [sys.executable, str(script), "init", "--db", str(db)],
        check=False,
    )
    return completed.returncode


def _chapters(root: Path, chapter: Path | None, all_chapters: bool) -> list[Path]:
    if all_chapters:
        directory = root / "work" / "chapters"
        return sorted(path for path in directory.glob("*.yaml") if path.is_file())
    assert chapter is not None
    return [chapter]


def _skill_path(adapter, repo: Path, relative: str) -> Path:
    if relative.startswith("/") or ".." in relative.split("/"):
        raise ValueError(f"路径越界：{relative}")
    return repo / str(adapter.config["skill_dir"]) / relative


def _warn_order(artifacts: dict, chapters: list) -> None:
    """topo 同层平局按 id 字母序（graph.py 用 ready.sort()）。
    与 yaml 教学顺序不一致时警告：不阻塞，但建议起草侧调整 id 选词。"""
    script = artifacts["graph_script"]
    db = artifacts["graph_db"]
    for chapter in chapters:
        completed = subprocess.run(
            [sys.executable, str(script), "topo", "--chapter", chapter.chapter_id, "--db", str(db)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            print(f"WARN topo 失败，跳过顺序检查：{chapter.chapter_id}", file=sys.stderr)
            continue
        ordered = [line.split("\t", 1)[0] for line in completed.stdout.splitlines() if line.strip()]
        expected = [node.id for node in chapter.nodes]
        if ordered != expected:
            print(
                "WARN topo 顺序与 yaml 教学顺序不一致（同层平局按 id 字母序）：\n"
                f"  topo: {' → '.join(ordered)}\n"
                f"  yaml: {' → '.join(expected)}",
                file=sys.stderr,
            )


def _warn_ref(repo: Path, ref: str) -> None:
    if not (repo / ".git").exists():
        return
    exists = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{ref}^{{commit}}"],
        check=False,
        capture_output=True,
    )
    if exists.returncode != 0:
        print(f"警告：repo 里没有 target.yaml 钉住的 ref {ref}", file=sys.stderr)
        return
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if head.returncode != 0:
        return
    if head.stdout.strip() == ref:
        return
    ancestor = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", ref, "HEAD"],
        check=False,
    )
    if ancestor.returncode != 0:
        print(f"警告：repo HEAD 不是 target.yaml 钉住的 ref {ref}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
