"""测试夹具：一份带内联种子的最小 skill 仓库。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


GRAPH_PY = '''#!/usr/bin/env python3
import argparse
import sqlite3
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
ORDER_KINDS = ("直接前置", "同章衔接")

# 夹具种子，迁移前内联在这里。
SEED_NODES = (
    ("kp_ion", "化学", "离子反应", "chem-bx1-ch1", 0),
    ("kp_seed", "化学", "夹具节点", "demo-ch1", 0),
    ("ch3_fe", "化学", "第三章 铁", "chem-bx1-later", 1),
)
SEED_EDGES = (
    ("kp_ion", "ch3_fe", "常考组合"),
)


def default_db():
    return SKILL_DIR / "data" / "graph.db"


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path)


def init_db(path):
    conn = connect(path)
    conn.executescript(
        """
        DROP TABLE IF EXISTS edges;
        DROP TABLE IF EXISTS nodes;
        CREATE TABLE nodes (
            id TEXT PRIMARY KEY,
            subject TEXT NOT NULL,
            display_name TEXT NOT NULL,
            chapter_id TEXT NOT NULL,
            grey INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE edges (
            src TEXT NOT NULL,
            dst TEXT NOT NULL,
            kind TEXT NOT NULL
        );
        """
    )
    conn.executemany(
        "INSERT INTO nodes (id, subject, display_name, chapter_id, grey) VALUES (?, ?, ?, ?, ?)",
        SEED_NODES,
    )
    conn.executemany("INSERT INTO edges (src, dst, kind) VALUES (?, ?, ?)", SEED_EDGES)
    conn.commit()
    conn.close()
    return Path(path)


def topo_order(chapter, path=None):
    conn = connect(path or default_db())
    rows = conn.execute(
        "SELECT id, display_name, grey FROM nodes WHERE chapter_id = ? ORDER BY id",
        (chapter,),
    ).fetchall()
    ids = [row[0] for row in rows if not row[2]]
    names = {row[0]: row[1] for row in rows}
    incoming = {node_id: set() for node_id in ids}
    outgoing = {node_id: set() for node_id in ids}
    if ids:
        query = (
            "SELECT src, dst FROM edges WHERE kind IN (?, ?) AND src IN ({}) AND dst IN ({})"
        ).format(",".join("?" * len(ids)), ",".join("?" * len(ids)))
        for src, dst in conn.execute(query, (*ORDER_KINDS, *ids, *ids)):
            incoming[dst].add(src)
            outgoing[src].add(dst)
    ready = sorted(node_id for node_id in ids if not incoming[node_id])
    ordered = []
    while ready:
        node_id = ready.pop(0)
        ordered.append(node_id)
        for dst in sorted(outgoing[node_id]):
            incoming[dst].discard(node_id)
            if not incoming[dst] and dst not in ordered and dst not in ready:
                ready.append(dst)
        ready.sort()
    conn.close()
    return [(node_id, names.get(node_id, node_id)) for node_id in ordered]


def main(argv=None):
    parser = argparse.ArgumentParser()
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--db", type=Path, default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", parents=[shared])
    topo = sub.add_parser("topo", parents=[shared])
    topo.add_argument("--chapter", required=True)
    args = parser.parse_args(argv)
    path = args.db or default_db()
    if args.cmd == "init":
        init_db(path)
        print(f"已写入 {path}")
        return 0
    if not path.exists():
        print("缺少 graph.db", file=sys.stderr)
        return 2
    if args.cmd == "topo":
        for node_id, name in topo_order(args.chapter, path):
            print(f"{node_id}\\t{name}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
'''

CANON = """# id kp_ion 离子反应
离子反应 |  | 必修第一册 第一章 物质及其变化 | 能说出离子反应是有离子参加的反应 | 能把离子反应和离子方程式对应起来 | 待补录：延伸不在本节点展开
"""

CHECK_PY = """#!/usr/bin/env python3
import sys
from pathlib import Path
if Path("tests/fail").exists():
    sys.exit(1)
print("ok")
"""

RUN_SH = """#!/usr/bin/env bash
exit 0
"""

CHAPTER = """chapter_id: chem-bx1-ch2
subject: 化学
book: 人教版《化学 必修 第一册》（2019）
book_short: chem-bx1
chapter_no: 2
chapter_title: 海水中的重要元素——钠和氯
canon_file: references/nodes/chemistry.md
canon_chapter: 必修第一册 第二章 海水中的重要元素——钠和氯
graph_doc: references/pep-chem-bx1-ch2.md
entry_question: 先学哪个节点：钠及其化合物，还是氯及其化合物？
sections:
  - title: 钠及其化合物
    nodes:
      - id: kp_na
        display: 钠的性质
        aliases: [钠单质]
        type: concept
        l1: 能说出钠的物理性质
        l2: 能解释钠与水反应的现象
        l3: 待补录：延伸不在本节点展开
        example: 钠投入滴有酚酞的蒸馏水，浮、熔、游、响、红
        pitfall: 与盐酸反应不能写成钠先与水反应再中和
      - id: kp_na2o2
        display: 过氧化钠
        aliases: []
        type: concept
        l1: 能说出过氧化钠的颜色
        l2: 能写出过氧化钠与水的反应
        l3: 待补录：延伸不在本节点展开
edges:
  - [kp_na, kp_na2o2, 直接前置]
combo:
  - [kp_na, kp_ion, 常考组合]
later:
  - id: ch3_fe
    display: 第三章 铁
"""


def write_skill_tree(root: Path) -> None:
    skill = root / "skills" / "high-school-ai-tutor"
    (skill / "scripts").mkdir(parents=True)
    (skill / "references" / "nodes").mkdir(parents=True)
    (skill / "data").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    (skill / "scripts" / "graph.py").write_text(GRAPH_PY, encoding="utf-8")
    (skill / "references" / "nodes" / "chemistry.md").write_text(CANON, encoding="utf-8")
    (skill / "scripts" / "records.py").write_text(
        "#!/usr/bin/env python3\nimport sys\n"
        "cmd = sys.argv[1]\n"
        "if cmd == 'unmatched':\n"
        "    print('频次 | 原文 | 建议补录为')\n"
        "    print('1 | 化学 · 钠单质 | 钠的性质')\n"
        "elif cmd == 'weak':\n"
        "    print('薄弱点')\n"
        "    print('1. 化学 · 钠的性质：做错 2，跳过 0，做对 0')\n",
        encoding="utf-8",
    )
    (root / "tests" / "check.py").write_text(CHECK_PY, encoding="utf-8")
    run = root / "tests" / "run.sh"
    run.write_text(RUN_SH, encoding="utf-8")
    run.chmod(0o755)


def git_commit(repo: Path, message: str) -> str:
    if not (repo / ".git").exists():
        subprocess.check_call(["git", "init", "-b", "main"], cwd=repo)
        subprocess.check_call(["git", "config", "user.email", "test@example.com"], cwd=repo)
        subprocess.check_call(["git", "config", "user.name", "test"], cwd=repo)
    for cache in repo.rglob("__pycache__"):
        shutil.rmtree(cache)
    subprocess.check_call(["git", "add", "-A"], cwd=repo)
    subprocess.check_call(["git", "commit", "-m", message], cwd=repo)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
