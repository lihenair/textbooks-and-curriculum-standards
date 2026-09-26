"""chapter.yaml 读写，以及与具体仓库路径无关的通用校验。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


SOLID_KINDS = ("直接前置", "同章衔接")
DASHED_KINDS = ("常考组合",)
NODE_TYPES = ("concept", "skill", "experiment")
TYPE_ZH = {"concept": "概念", "skill": "技能", "experiment": "实验"}
_NODE_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CHAPTER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_NODE_KEYS = {
    "id",
    "display",
    "aliases",
    "type",
    "l1",
    "l2",
    "l3",
    "example",
    "pitfall",
    "confusion",
    "source",
}
_SOURCE_KEYS = {"textbook", "curriculum"}
_REQUIRED = (
    "chapter_id",
    "subject",
    "book",
    "book_short",
    "chapter_no",
    "chapter_title",
    "canon_file",
    "canon_chapter",
    "graph_doc",
    "entry_question",
    "sections",
)


@dataclass
class Violation:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


@dataclass
class Node:
    id: str
    display: str
    aliases: list[str]
    type: str
    l1: str
    l2: str
    l3: str
    example: str = ""
    pitfall: str = ""
    confusion: str = ""
    source: dict = field(default_factory=dict)
    section: str = ""
    path: str = ""


@dataclass
class Edge:
    src: str
    dst: str
    kind: str
    path: str
    external: bool = False


@dataclass
class Later:
    id: str
    display: str
    chapter_id: str
    path: str


@dataclass
class Chapter:
    chapter_id: str
    subject: str
    book: str
    book_short: str
    chapter_no: int
    chapter_title: str
    canon_file: str
    canon_chapter: str
    graph_doc: str
    entry_question: str
    sections: list[dict]
    nodes: list[Node]
    edges: list[Edge]
    combo: list[Edge]
    later: list[Later]
    raw: dict


def zh_index(number: int) -> str:
    digits = "零一二三四五六七八九"
    if number <= 0:
        return str(number)
    if number < 10:
        return digits[number]
    if number == 10:
        return "十"
    if number < 20:
        return "十" + digits[number % 10]
    if number < 100:
        tens, ones = divmod(number, 10)
        return digits[tens] + "十" + (digits[ones] if ones else "")
    return str(number)


def load(path: Path) -> Chapter:
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: YAML 无法解析：{exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: chapter.yaml 顶层必须是映射")
    problems = validate_data(data)
    if problems:
        detail = "；".join(str(item) for item in problems)
        raise ValueError(detail)
    return build(data)


def dump(chapter: Chapter, path: Path) -> None:
    Path(path).write_text(
        yaml.safe_dump(chapter.raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def validate(chapter: Chapter) -> list[Violation]:
    return validate_data(chapter.raw)


def validate_data(data: dict) -> list[Violation]:
    problems: list[Violation] = []
    for key in _REQUIRED:
        if key not in data or data[key] in (None, "", []):
            problems.append(Violation(key, "必填"))
    if problems:
        return problems
    if not isinstance(data["chapter_no"], int):
        problems.append(Violation("chapter_no", "必须是整数"))
    for key in ("chapter_id", "canon_file", "graph_doc", "book_short"):
        text = str(data.get(key, ""))
        if ".." in text.split("/") or text.startswith("/"):
            problems.append(Violation(key, "路径不能越出仓库"))
    if not _CHAPTER_ID.match(str(data["chapter_id"])):
        problems.append(Violation("chapter_id", "只能用英文、数字、下划线和连字符"))

    nodes: list[Node] = []
    seen: set[str] = set()
    sections = data["sections"]
    if not isinstance(sections, list):
        return problems + [Violation("sections", "必须是列表")]
    for s_index, section in enumerate(sections):
        path = f"sections[{s_index}]"
        if not isinstance(section, dict) or not str(section.get("title") or "").strip():
            problems.append(Violation(path, "节必须有 title"))
            continue
        raw_nodes = section.get("nodes") or []
        if not isinstance(raw_nodes, list) or not raw_nodes:
            problems.append(Violation(f"{path}.nodes", "节内至少要有一个节点"))
            continue
        for n_index, raw in enumerate(raw_nodes):
            npath = f"{path}.nodes[{n_index}]"
            node, node_problems = _node(raw, npath, str(section["title"]))
            problems.extend(node_problems)
            if node is None:
                continue
            if node.id in seen:
                problems.append(Violation(f"{npath}.id", f"本章内重复：{node.id}"))
            seen.add(node.id)
            nodes.append(node)

    later: list[Later] = []
    later_ids: set[str] = set()
    for index, raw in enumerate(data.get("later") or []):
        path = f"later[{index}]"
        if not isinstance(raw, dict) or not raw.get("id") or not raw.get("display"):
            problems.append(Violation(path, "需要 id 和 display"))
            continue
        later_id = str(raw["id"])
        if not _NODE_ID.match(later_id):
            problems.append(Violation(f"{path}.id", "只能用英文、数字和下划线"))
        if later_id in seen or later_id in later_ids:
            problems.append(Violation(f"{path}.id", f"与已有节点重复：{later_id}"))
        later_ids.add(later_id)
        chapter_id = str(raw.get("chapter_id") or f"{data['book_short']}-later")
        later.append(Later(later_id, str(raw["display"]), chapter_id, path))

    known = seen | later_ids
    edges = _edges(data.get("edges") or [], "edges", SOLID_KINDS, known, problems, allow_external=False)
    combo = _edges(data.get("combo") or [], "combo", DASHED_KINDS, known, problems, allow_external=True)
    _cycles(nodes, edges, problems)
    _alias_collisions(nodes, problems)
    return problems


def build(data: dict) -> Chapter:
    nodes: list[Node] = []
    sections = []
    for s_index, section in enumerate(data["sections"]):
        built_nodes = []
        for n_index, raw in enumerate(section["nodes"]):
            node, _ = _node(raw, f"sections[{s_index}].nodes[{n_index}]", str(section["title"]))
            assert node is not None
            nodes.append(node)
            built_nodes.append(node)
        sections.append({"title": str(section["title"]), "nodes": built_nodes})
    known = {node.id for node in nodes}
    later = []
    for index, raw in enumerate(data.get("later") or []):
        later.append(
            Later(
                str(raw["id"]),
                str(raw["display"]),
                str(raw.get("chapter_id") or f"{data['book_short']}-later"),
                f"later[{index}]",
            )
        )
        known.add(str(raw["id"]))
    problems: list[Violation] = []
    edges = _edges(data.get("edges") or [], "edges", SOLID_KINDS, known, problems, False)
    combo = _edges(data.get("combo") or [], "combo", DASHED_KINDS, known, problems, True)
    return Chapter(
        chapter_id=str(data["chapter_id"]),
        subject=str(data["subject"]),
        book=str(data["book"]),
        book_short=str(data["book_short"]),
        chapter_no=int(data["chapter_no"]),
        chapter_title=str(data["chapter_title"]),
        canon_file=str(data["canon_file"]),
        canon_chapter=str(data["canon_chapter"]),
        graph_doc=str(data["graph_doc"]),
        entry_question=str(data["entry_question"]),
        sections=[{"title": item["title"], "nodes": item["nodes"]} for item in sections],
        nodes=nodes,
        edges=edges,
        combo=combo,
        later=later,
        raw=data,
    )


def _node(raw, path: str, section: str) -> tuple[Node | None, list[Violation]]:
    problems: list[Violation] = []
    if not isinstance(raw, dict):
        return None, [Violation(path, "节点必须是映射")]
    extra = set(raw) - _NODE_KEYS
    if extra:
        problems.append(Violation(path, f"未知字段（原文不能入库）：{'、'.join(sorted(extra))}"))
    node_id = str(raw.get("id") or "")
    display = str(raw.get("display") or "").strip()
    if not _NODE_ID.match(node_id):
        problems.append(Violation(f"{path}.id", "只能用英文、数字和下划线"))
    if not display:
        problems.append(Violation(f"{path}.display", "必填"))
    if "|" in display or "\n" in display:
        problems.append(Violation(f"{path}.display", "不能含竖线或换行"))
    node_type = str(raw.get("type") or "")
    if node_type not in NODE_TYPES:
        problems.append(Violation(f"{path}.type", "只能是 concept、skill 或 experiment"))
    levels = {}
    for key in ("l1", "l2", "l3"):
        value = str(raw.get(key) or "").strip()
        if not value:
            problems.append(Violation(f"{path}.{key}", "必填"))
        if "|" in value or "\n" in value:
            problems.append(Violation(f"{path}.{key}", "不能含竖线或换行"))
        levels[key] = value
    aliases = raw.get("aliases") or []
    if not isinstance(aliases, list) or not all(isinstance(item, str) and item.strip() for item in aliases):
        problems.append(Violation(f"{path}.aliases", "必须是非空字符串列表"))
        aliases = []
    if any("|" in item or "、" in item for item in aliases):
        problems.append(Violation(f"{path}.aliases", "别名本身不能含顿号或竖线"))
    source = raw.get("source") or {}
    if source and (not isinstance(source, dict) or set(source) - _SOURCE_KEYS):
        problems.append(Violation(f"{path}.source", "只能写 textbook 与 curriculum 页码引用"))
    if any(problems):
        return None, problems
    return (
        Node(
            id=node_id,
            display=display,
            aliases=[item.strip() for item in aliases],
            type=node_type,
            l1=levels["l1"],
            l2=levels["l2"],
            l3=levels["l3"],
            example=str(raw.get("example") or "").strip(),
            pitfall=str(raw.get("pitfall") or "").strip(),
            confusion=str(raw.get("confusion") or "").strip(),
            source=dict(source),
            section=section,
            path=path,
        ),
        [],
    )


def _edges(raw_edges, key: str, allowed: tuple[str, ...], known: set[str], problems: list[Violation], allow_external: bool) -> list[Edge]:
    edges: list[Edge] = []
    seen: set[tuple[str, str, str]] = set()
    if not isinstance(raw_edges, list):
        problems.append(Violation(key, "必须是列表"))
        return edges
    for index, raw in enumerate(raw_edges):
        path = f"{key}[{index}]"
        if not isinstance(raw, (list, tuple)) or len(raw) != 3:
            problems.append(Violation(path, "必须是 [起点, 终点, 标签]"))
            continue
        src, dst, kind = (str(raw[0]), str(raw[1]), str(raw[2]))
        if kind not in allowed:
            problems.append(Violation(path, f"标签只能是 {'、'.join(allowed)}"))
            continue
        if src == dst:
            problems.append(Violation(path, "端点不能相同"))
            continue
        missing = src if src not in known else dst if dst not in known else ""
        if missing and not allow_external:
            problems.append(Violation(path, f"端点不存在：{missing}"))
            continue
        pair = (src, dst, kind)
        if pair in seen:
            problems.append(Violation(path, "重复边"))
            continue
        seen.add(pair)
        edges.append(Edge(src, dst, kind, path, external=bool(missing)))
    return edges


def solid_edges_stay_inside(chapter: Chapter) -> list[Violation]:
    """实线两端都必须是本章正式节点，不能落到 later 或他章。"""
    formal = {node.id for node in chapter.nodes}
    problems = []
    for edge in chapter.edges:
        for endpoint in (edge.src, edge.dst):
            if endpoint not in formal:
                problems.append(Violation(edge.path, f"实线端点必须是本章节点：{endpoint}"))
    return problems


def _cycles(nodes: list[Node], edges: list[Edge], problems: list[Violation]) -> None:
    formal = [node.id for node in nodes]
    incoming = {node_id: set() for node_id in formal}
    outgoing = {node_id: set() for node_id in formal}
    for edge in edges:
        if edge.src in incoming and edge.dst in incoming:
            incoming[edge.dst].add(edge.src)
            outgoing[edge.src].add(edge.dst)
    ready = sorted(node_id for node_id in formal if not incoming[node_id])
    seen = 0
    while ready:
        node_id = ready.pop(0)
        seen += 1
        for dst in sorted(outgoing[node_id]):
            incoming[dst].discard(node_id)
            if not incoming[dst] and dst not in ready:
                ready.append(dst)
        ready.sort()
    if seen != len(formal):
        stuck = sorted(node_id for node_id, deps in incoming.items() if deps)
        problems.append(Violation("edges", f"本章实线边有环，涉及：{'、'.join(stuck)}"))


def _alias_collisions(nodes: list[Node], problems: list[Violation]) -> None:
    seen: dict[str, str] = {}
    for node in nodes:
        for label in (node.display, *node.aliases):
            key = fold(label)
            if key in seen:
                problems.append(Violation(node.path or node.id, f"别名在本章内重复：{label}"))
            else:
                seen[key] = node.id


def fold(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").strip())
