#!/usr/bin/env python3
"""纪律 6 的空跑：stub 目标上证明能推进 ref、能跑 validate、diff 非空会红灯。"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.migrate_seeds import main as migrate_main
from core.scaffold import main as scaffold_main
from scripts.drift_check import advance_ref, regenerate_gate, text_diff
from tests.support import CHAPTER, git_commit, write_skill_tree


def run_dry() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        origin = root / "origin"
        origin.mkdir()
        write_skill_tree(origin)
        pipe = root / "pipe"
        shutil.copytree(ROOT / "core", pipe / "core")
        shutil.copytree(ROOT / "targets", pipe / "targets")
        shutil.copytree(ROOT / "scripts", pipe / "scripts")
        (pipe / "work" / "chapters").mkdir(parents=True)
        migrate_main(["--repo", str(origin), "--target", "stub", "--apply", "--pipeline-root", str(pipe)])
        subprocess.check_call([
            "python3",
            str(origin / "skills/high-school-ai-tutor/scripts/graph.py"),
            "init",
        ])
        first = git_commit(origin, "green")
        _pin(pipe, first)
        (origin / "README.md").write_text("still green\n", encoding="utf-8")
        second = git_commit(origin, "still green")
        work = root / "work"
        subprocess.check_call(["git", "clone", str(origin), str(work)])
        subprocess.check_call(["git", "config", "user.email", "test@example.com"], cwd=work)
        subprocess.check_call(["git", "config", "user.name", "test"], cwd=work)

        code = advance_ref(pipe, "stub", work)
        if code != 0:
            raise SystemExit(f"推进 ref 失败：{code}")
        pinned = (pipe / "targets" / "stub" / "target.yaml").read_text(encoding="utf-8")
        if f"ref: {second}" not in pinned:
            raise SystemExit("fetch 之后没有把 ref 钉到新的 HEAD")

        (pipe / "work" / "chapters" / "chem-bx1-ch2.yaml").write_text(CHAPTER, encoding="utf-8")
        code = scaffold_main([
            "--all",
            "--repo",
            str(work),
            "--target",
            "stub",
            "--apply",
            "--pipeline-root",
            str(pipe),
        ])
        if code != 0:
            raise SystemExit(f"首次生成失败：{code}")
        subprocess.check_call(["git", "add", "-A"], cwd=work)
        subprocess.check_call(["git", "commit", "-m", "generated"], cwd=work)
        adapter_code = regenerate_gate(pipe, _adapter(pipe), work)
        if adapter_code != 0:
            raise SystemExit("同一 yaml 重生成后 diff 应该为空")

        page = next((work / "skills/high-school-ai-tutor/references/study-pages").rglob("kp_*.md"))
        page.write_text(page.read_text(encoding="utf-8") + "手改\n", encoding="utf-8")
        if text_diff(work) == 0:
            raise SystemExit("文本 diff 非空时必须红灯")

        (origin / "tests" / "fail").write_text("1\n", encoding="utf-8")
        git_commit(origin, "red")
        red = advance_ref(pipe, "stub", work)
        if red == 0:
            raise SystemExit("基线变红时必须停下，不能推进 ref")
        pinned = (pipe / "targets" / "stub" / "target.yaml").read_text(encoding="utf-8")
        if f"ref: {second}" not in pinned:
            raise SystemExit("红灯之后 ref 必须留在上一块绿的提交")
    print("空跑通过：能推进 ref，能跑 validate，diff 非空会红灯。")


def _pin(pipe: Path, rev: str) -> None:
    path = pipe / "targets" / "stub" / "target.yaml"
    text = path.read_text(encoding="utf-8")
    text = text.replace("0000000000000000000000000000000000000000", rev)
    path.write_text(text, encoding="utf-8")


def _adapter(pipe: Path):
    from core.adapter import load_adapter
    return load_adapter(pipe, "stub")


if __name__ == "__main__":
    run_dry()
