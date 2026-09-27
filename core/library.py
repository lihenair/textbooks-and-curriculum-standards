"""正典、种子和 graph.db 的读写。路径全部由调用方传入。"""

from __future__ import annotations

import ast
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from core.ir import Chapter, Violation, fold


_ID_LINE = re.compile(r"^#\s*id\s+(\S+)\s+(.+)$")
_BEGIN = re.compile(r"^#\s*pipeline:begin\s+(\S+)\s*$")
_END = re.compile(r"^#\s*pipeline:end\s+(\S+)\s*$")


@dataclass
class CanonEntry:
    node_id: str
    display: str
    line: str
    generated: bool


@dataclass
class SeedNode:
    id: str
    subject: str
    display: str
    chapter_id: str
    grey: int


@dataclass
class SeedEdge:
    src: str
    dst: str
    kind: str


@dataclass
class Seeds:
    nodes: list[SeedNode]
    edges: list[SeedEdge]
    owned_later: dict[str, tuple[str, ...]]


def read_canon(path: Path) -> list[CanonEntry]:
    if not path.exists():
        return []
    entries: list[CanonEntry] = []
    pending_id = ""
    pending_display = ""
    generated = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        begin = _BEGIN.match(raw.strip())
        end = _END.match(raw.strip())
        if begin:
            generated = True
            continue
        if end:
            generated = False
            continue
        matched = _ID_LINE.match(raw.strip())
        if matched:
            pending_id, pending_display = matched.group(1), matched.group(2).strip()
            continue
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        display = parts[0] if parts else ""
        entries.append(
            CanonEntry(
                node_id=pending_id if pending_display == display else "",
                display=display,
                line=line,
                generated=generated,
            )
        )
        pending_id = ""
        pending_display = ""
    return entries


def canon_ids(canon_dir: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not canon_dir.is_dir():
        return mapping
    for path in sorted(canon_dir.glob("*.md")):
        pending = ""
        display = ""
        for raw in path.read_text(encoding="utf-8").splitlines():
            matched = _ID_LINE.match(raw.strip())
            if matched:
                pending, display = matched.group(1), matched.group(2).strip()
                mapping[pending] = display
    return mapping


def canon_labels(path: Path) -> dict[str, str]:
    labels: dict[str, str] = {}
    for entry in read_canon(path):
        parts = [part.strip() for part in entry.line.split("|")]
        if len(parts) < 3:
            continue
        aliases = [item.strip() for item in parts[1].split("、") if item.strip()]
        for label in (parts[0], *aliases):
            labels.setdefault(fold(label), parts[0])
    return labels


def render_canon_block(chapter: Chapter, line_template: str, render) -> str:
    rows = []
    for node in chapter.nodes:
        rows.append(
            render(
                line_template,
                {
                    "id": node.id,
                    "display": node.display,
                    "aliases": "、".join(node.aliases),
                    "canon_chapter": chapter.canon_chapter,
                    "l1": node.l1,
                    "l2": node.l2,
                    "l3": node.l3,
                },
            ).rstrip("\n")
        )
    body = "\n".join(rows)
    return f"# pipeline:begin {chapter.chapter_id}\n{body}\n# pipeline:end {chapter.chapter_id}\n"


def merge_canon(existing: str, chapter_id: str, block: str) -> str:
    """已有 pipeline 块原地替换，新章才追加到文末。"""
    lines = existing.splitlines()
    begin = end = None
    for index, line in enumerate(lines):
        matched = _BEGIN.match(line.strip())
        if matched and matched.group(1) == chapter_id:
            begin = index
        matched_end = _END.match(line.strip())
        if begin is not None and matched_end and matched_end.group(1) == chapter_id:
            end = index
            break
    block_lines = block.strip("\n").split("\n") if block.strip("\n") else []
    if begin is not None and end is not None:
        merged = lines[:begin] + block_lines + lines[end + 1 :]
        text = "\n".join(merged).rstrip("\n")
        return (text + "\n") if text else ""
    kept = "\n".join(lines).rstrip("\n")
    if kept:
        kept += "\n"
    if not block_lines:
        return kept
    if kept and not kept.endswith("\n\n"):
        kept += "\n"
    return kept + "\n".join(block_lines) + "\n"


def canon_conflicts(chapter: Chapter, canon_path: Path, line_template: str, render) -> list[Violation]:
    """策展区已有的 id：内容一致则跳过，不一致则拒绝改写。"""
    problems = []
    generated_ids = set()
    if canon_path.exists():
        inside = False
        for raw in canon_path.read_text(encoding="utf-8").splitlines():
            if _BEGIN.match(raw.strip()) and _BEGIN.match(raw.strip()).group(1) == chapter.chapter_id:
                inside = True
                continue
            if _END.match(raw.strip()) and _END.match(raw.strip()).group(1) == chapter.chapter_id:
                inside = False
                continue
            matched = _ID_LINE.match(raw.strip())
            if matched and inside:
                generated_ids.add(matched.group(1))
    fresh = {
        node.id: render(
            line_template,
            {
                "id": node.id,
                "display": node.display,
                "aliases": "、".join(node.aliases),
                "canon_chapter": chapter.canon_chapter,
                "l1": node.l1,
                "l2": node.l2,
                "l3": node.l3,
            },
        ).rstrip("\n")
        for node in chapter.nodes
    }
    entries = read_canon(canon_path)
    by_id = {entry.node_id: entry for entry in entries if entry.node_id}
    for node in chapter.nodes:
        current = by_id.get(node.id)
        if current is None or current.generated or node.id in generated_ids:
            continue
        wanted = fresh[node.id]
        have = f"# id {node.id} {current.display}\n{current.line}"
        if wanted != have:
            problems.append(
                Violation(
                    node.path or node.id,
                    "正典策展区已有该 id，scaffold 不改既有行；请直接改策展区，或换一个 id",
                )
            )
    return problems


def block_ids(path: Path, chapter_id: str) -> set[str]:
    found = set()
    if not path.exists():
        return found
    inside = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        begin = _BEGIN.match(raw.strip())
        end = _END.match(raw.strip())
        if begin and begin.group(1) == chapter_id:
            inside = True
            continue
        if end and end.group(1) == chapter_id:
            inside = False
            continue
        matched = _ID_LINE.match(raw.strip())
        if matched and inside:
            found.add(matched.group(1))
    return found


def outside_ids(path: Path, chapter_id: str) -> set[str]:
    found = set()
    if not path.exists():
        return found
    inside = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        begin = _BEGIN.match(raw.strip())
        end = _END.match(raw.strip())
        if begin and begin.group(1) == chapter_id:
            inside = True
            continue
        if end and end.group(1) == chapter_id:
            inside = False
            continue
        matched = _ID_LINE.match(raw.strip())
        if matched and not inside:
            found.add(matched.group(1))
    return found


def library_identity(canon_dir: Path, chapter: Chapter, subject_file: Path) -> list[Violation]:
    """全库 id 唯一，别名在科目内唯一。本块会整段替换，不跟自己撞。"""
    problems: list[Violation] = []
    own_block = block_ids(subject_file, chapter.chapter_id)
    elsewhere: dict[str, str] = {}
    if canon_dir.is_dir():
        for path in sorted(canon_dir.glob("*.md")):
            if path.resolve() == subject_file.resolve():
                continue
            pending = ""
            for raw in path.read_text(encoding="utf-8").splitlines():
                matched = _ID_LINE.match(raw.strip())
                if matched:
                    pending = matched.group(1)
                    elsewhere[pending] = matched.group(2).strip()
    for node in chapter.nodes:
        if node.id in elsewhere:
            problems.append(
                Violation(node.path or node.id, f"id 在其他正典文件已存在：{elsewhere[node.id]}")
            )
    labels: dict[str, str] = {}
    for entry in read_canon(subject_file):
        if not entry.node_id or entry.node_id in own_block:
            continue
        if entry.node_id in {node.id for node in chapter.nodes}:
            continue
        parts = [part.strip() for part in entry.line.split("|")]
        aliases = [item.strip() for item in parts[1].split("、") if item.strip()] if len(parts) > 1 else []
        for label in (entry.display, *aliases):
            labels.setdefault(fold(label), entry.node_id)
    for node in chapter.nodes:
        for label in (node.display, *node.aliases):
            owner = labels.get(fold(label))
            if owner and owner != node.id:
                problems.append(Violation(node.path or node.id, f"别名在科目内已被占用：{label}"))
    return problems


def load_seeds(path: Path, nodes_var: str, edges_var: str) -> Seeds:
    if not path.is_file():
        return Seeds([], [], {})
    return parse_seeds(path.read_text(encoding="utf-8"), nodes_var, edges_var)


def parse_seeds(source: str, nodes_var: str, edges_var: str) -> Seeds:
    tree = ast.parse(source)
    found: dict[str, object] = {}
    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign):
            continue
        for target in stmt.targets:
            if isinstance(target, ast.Name) and target.id in {nodes_var, edges_var, "OWNED_LATER"}:
                found[target.id] = ast.literal_eval(stmt.value)
    nodes = [
        SeedNode(item[0], item[1], item[2], item[3], int(item[4]))
        for item in found.get(nodes_var, [])
    ]
    edges = [SeedEdge(item[0], item[1], item[2]) for item in found.get(edges_var, [])]
    owned_raw = found.get("OWNED_LATER", {})
    owned = {str(key): tuple(str(item) for item in value) for key, value in owned_raw.items()}
    return Seeds(nodes, edges, owned)


def merge_seeds(existing: Seeds, chapters: list[Chapter]) -> tuple[Seeds, list[Violation]]:
    problems: list[Violation] = []
    rebuilding = {chapter.chapter_id for chapter in chapters}
    previous_later = {
        node_id
        for chapter_id, ids in existing.owned_later.items()
        if chapter_id in rebuilding
        for node_id in ids
    }
    old_formal = {node.id for node in existing.nodes if node.chapter_id in rebuilding and not node.grey}
    drop_ids = old_formal | previous_later
    base_nodes = [
        node
        for node in existing.nodes
        if node.id not in drop_ids and not (node.chapter_id in rebuilding and not node.grey)
    ]
    new_nodes: list[SeedNode] = []
    owned_later = {key: value for key, value in existing.owned_later.items() if key not in rebuilding}
    formal_ids: set[str] = set()
    for chapter in chapters:
        created: list[str] = []
        for node in chapter.nodes:
            if any(item.id == node.id for item in base_nodes) or any(item.id == node.id for item in new_nodes):
                problems.append(Violation(node.path or node.id, f"种子里已有同名节点：{node.id}"))
                continue
            new_nodes.append(SeedNode(node.id, chapter.subject, node.display, chapter.chapter_id, 0))
            formal_ids.add(node.id)
        for item in chapter.later:
            current = next((node for node in (*base_nodes, *new_nodes) if node.id == item.id), None)
            if current is not None:
                if current.display != item.display:
                    problems.append(Violation(item.path, f"灰节点已存在且显示名不同：{current.display}"))
                continue
            new_nodes.append(SeedNode(item.id, chapter.subject, item.display, item.chapter_id, 1))
            created.append(item.id)
        if created:
            owned_later[chapter.chapter_id] = tuple(created)
        formal_ids.update(node.id for node in chapter.nodes)
    formal_by_chapter: dict[str, list[SeedNode]] = {}
    grey_new: list[SeedNode] = []
    for node in new_nodes:
        if node.grey:
            grey_new.append(node)
        else:
            formal_by_chapter.setdefault(node.chapter_id, []).append(node)
    known_ids = {node.id for node in base_nodes} | {node.id for node in new_nodes}
    edges_by_chapter: dict[str, list[SeedEdge]] = {}
    seen_edges = {
        (edge.src, edge.dst, edge.kind)
        for edge in existing.edges
        if edge.src not in old_formal and edge.src not in formal_ids
    }
    for chapter in chapters:
        for edge in (*chapter.edges, *chapter.combo):
            if edge.src not in known_ids or edge.dst not in known_ids:
                missing = edge.src if edge.src not in known_ids else edge.dst
                problems.append(Violation(edge.path, f"端点不存在：{missing}"))
                continue
            key = (edge.src, edge.dst, edge.kind)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edges_by_chapter.setdefault(chapter.chapter_id, []).append(SeedEdge(*key))
    if problems:
        return Seeds(base_nodes, [], owned_later), problems
    nodes = _place_rebuilt(
        existing.nodes,
        formal_by_chapter,
        grey_new,
        rebuilding,
        drop_ids,
    )
    edges = _place_edges(existing, formal_by_chapter, edges_by_chapter, rebuilding)
    return Seeds(nodes, edges, owned_later), []


def _node_key(node: SeedNode) -> tuple:
    return (node.id, node.subject, node.display, node.chapter_id, node.grey)


def _edge_key(edge: SeedEdge) -> tuple:
    return (edge.src, edge.dst, edge.kind)


def _place_rebuilt(existing_nodes, formal_by_chapter, grey_new, rebuilding, drop_ids) -> list[SeedNode]:
    """内容没变的章留在原位置；有变化时只替换该章那一组。"""
    stable = {
        chapter_id
        for chapter_id in rebuilding
        if _same_nodes(
            [node for node in existing_nodes if node.chapter_id == chapter_id and not node.grey],
            formal_by_chapter.get(chapter_id, []),
        )
    }
    result: list[SeedNode] = []
    placed: set[str] = set()
    for node in existing_nodes:
        if node.chapter_id in stable and not node.grey:
            result.append(node)
            continue
        if node.chapter_id in rebuilding and not node.grey:
            if node.chapter_id not in placed:
                result.extend(formal_by_chapter.get(node.chapter_id, []))
                placed.add(node.chapter_id)
            continue
        if node.id in drop_ids:
            continue
        result.append(node)
    for chapter_id, group in formal_by_chapter.items():
        if chapter_id not in placed and chapter_id not in stable:
            result.extend(group)
    result.extend(grey_new)
    return result


def _same_nodes(old: list[SeedNode], new: list[SeedNode]) -> bool:
    return {_node_key(node) for node in old} == {_node_key(node) for node in new}


def _place_edges(existing: Seeds, formal_by_chapter, edges_by_chapter, rebuilding) -> list[SeedEdge]:
    owners = _edge_owners(existing, formal_by_chapter, rebuilding)
    stable = set()
    for chapter_id in rebuilding:
        old = [edge for edge in existing.edges if owners.get(edge.src) == chapter_id]
        new = edges_by_chapter.get(chapter_id, [])
        if {_edge_key(edge) for edge in old} == {_edge_key(edge) for edge in new}:
            stable.add(chapter_id)
    result: list[SeedEdge] = []
    placed: set[str] = set()
    for edge in existing.edges:
        owner = owners.get(edge.src)
        if owner in stable:
            result.append(edge)
            continue
        if owner in rebuilding:
            if owner not in placed:
                result.extend(edges_by_chapter.get(owner, []))
                placed.add(owner)
            continue
        result.append(edge)
    for chapter_id, group in edges_by_chapter.items():
        if chapter_id not in placed and chapter_id not in stable:
            result.extend(group)
    return result


def _edge_owners(existing: Seeds, formal_by_chapter, rebuilding) -> dict[str, str]:
    owners: dict[str, str] = {}
    for node in existing.nodes:
        if node.chapter_id in rebuilding and not node.grey:
            owners[node.id] = node.chapter_id
    for chapter_id, group in formal_by_chapter.items():
        for node in group:
            owners[node.id] = chapter_id
    return owners


def dump_db(path: Path) -> str:
    conn = sqlite3.connect(path)
    try:
        nodes = conn.execute(
            "SELECT id, subject, display_name, chapter_id, grey FROM nodes ORDER BY id"
        ).fetchall()
        edges = conn.execute(
            "SELECT src, dst, kind FROM edges ORDER BY src, dst, kind"
        ).fetchall()
    finally:
        conn.close()
    lines = ["nodes"]
    lines.extend("\t".join(str(part) for part in row) for row in nodes)
    lines.append("edges")
    lines.extend("\t".join(row) for row in edges)
    return "\n".join(lines) + "\n"


def graph_script_loads_seeds(source: str) -> bool:
    return "graph-seeds.py" in source and "_load_seeds" in source
