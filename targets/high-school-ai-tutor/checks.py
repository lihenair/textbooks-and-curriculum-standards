"""目标侧格式闸。签名固定为 check(ir, artifacts) -> list[Violation]。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.ir import Violation


CLASS_DEFS = (
    "classDef concept fill:#E8F1FF,stroke:#3B6FB6,color:#1A1A1A",
    "classDef skill fill:#E7F6EE,stroke:#2E7D4F,color:#1A1A1A",
    "classDef experiment fill:#FFF4E5,stroke:#C47B17,color:#1A1A1A",
    "classDef later fill:#F4F4F5,stroke:#71717A,color:#1A1A1A",
)
VERIFY = "已机验：通过"


def check(ir, artifacts) -> list[Violation]:
    problems: list[Violation] = []
    graph = artifacts.get("graph_doc") or ""
    for line in CLASS_DEFS:
        if line not in graph:
            problems.append(Violation("graph_doc", f"整章图缺少配色：{line}"))
    if "flowchart TD" not in graph:
        problems.append(Violation("graph_doc", "整章图必须是 mermaid flowchart TD"))
    incoming: dict[str, list[str]] = {}
    for edge in ir.get("edges") or []:
        if edge["kind"] == "直接前置":
            incoming.setdefault(edge["dst"], []).append(edge["src"])
    for dst, sources in incoming.items():
        if len(sources) > 1:
            problems.append(Violation(dst, "一个节点只能有一条直接前置"))
    pages = artifacts.get("study_pages") or {}
    for node in ir.get("nodes") or []:
        page = pages.get(node["id"]) or ""
        label = f"【模式：自学 · 状态：节点 · 节点：{node['display']}】"
        if label not in page:
            problems.append(Violation(node["id"], "学习页状态标签必须使用正典显示名"))
        for step in range(1, 8):
            if f"Step {step}\n" not in page and f"Step {step}\r\n" not in page:
                problems.append(Violation(node["id"], f"学习页缺少 Step {step}"))
        if page.count(VERIFY) != 1 or "Step 6" not in page or "Step 7" not in page:
            problems.append(Violation(node["id"], "已机验：通过 只能标在判别自测槽，且只能出现一次"))
        else:
            head, rest = page.split("Step 6", 1)
            middle, tail = rest.split("Step 7", 1)
            if VERIFY in head or VERIFY in tail or VERIFY not in middle:
                problems.append(Violation(node["id"], "已机验：通过 只能标在判别自测槽"))
        if not node.get("example") and "（待补录：最小例子）" not in page:
            problems.append(Violation(node["id"], "空例子必须显式写待补录"))
        if not node.get("pitfall") and "（待补录：易错点）" not in page:
            problems.append(Violation(node["id"], "空易错点必须显式写待补录"))
        if not node.get("confusion") and "（待补录：易混辨析）" not in page:
            problems.append(Violation(node["id"], "空易混辨析必须显式写待补录"))
    if "graph-seeds.py" not in (artifacts.get("graph_script_text") or ""):
        problems.append(Violation("graph.py", "init 必须读取 data/graph-seeds.py"))
    return problems
