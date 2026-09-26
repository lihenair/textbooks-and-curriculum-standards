#!/usr/bin/env python3
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.adapter import load_adapter
from core.extract import extract_pages, write_extract
from core.find_notes import search_vault
from core.feedback import main as feedback_main
from core.library import dump_db
from core.migrate_seeds import main as migrate_main
from core.scaffold import main as scaffold_main
from tests.support import CHAPTER, git_commit, write_skill_tree


ROOT = Path(__file__).resolve().parent.parent


class AdapterTests(unittest.TestCase):
    def test_missing_checks_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            pipe = Path(tmp) / "pipe"
            shutil.copytree(ROOT / "core", pipe / "core")
            shutil.copytree(ROOT / "targets" / "high-school-ai-tutor", pipe / "targets" / "high-school-ai-tutor")
            (pipe / "targets" / "high-school-ai-tutor" / "checks.py").unlink()
            with self.assertRaises(SystemExit) as caught:
                load_adapter(pipe, "high-school-ai-tutor")
        self.assertEqual(caught.exception.code, 2)


class ScaffoldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        write_skill_tree(self.repo)
        code = migrate_main(["--repo", str(self.repo), "--apply", "--pipeline-root", str(ROOT)])
        self.assertEqual(code, 0)
        subprocess.check_call([
            "python3",
            str(self.repo / "skills/high-school-ai-tutor/scripts/graph.py"),
            "init",
        ])
        self.chapter = Path(self.tmp.name) / "chapter.yaml"
        self.chapter.write_text(CHAPTER, encoding="utf-8")
        git_commit(self.repo, "baseline")

    def tearDown(self):
        self.tmp.cleanup()

    def _scaffold(self, *extra):
        return scaffold_main([
            str(self.chapter),
            "--repo",
            str(self.repo),
            "--target",
            "high-school-ai-tutor",
            "--pipeline-root",
            str(ROOT),
            *extra,
        ])

    def test_refuses_unmigrated_graph_without_writing(self):
        fresh = Path(self.tmp.name) / "fresh"
        fresh.mkdir()
        write_skill_tree(fresh)
        canon = (fresh / "skills/high-school-ai-tutor/references/nodes/chemistry.md").read_text(encoding="utf-8")
        code = scaffold_main([
            str(self.chapter),
            "--repo",
            str(fresh),
            "--apply",
            "--pipeline-root",
            str(ROOT),
        ])
        self.assertEqual(code, 1)
        self.assertEqual(
            (fresh / "skills/high-school-ai-tutor/references/nodes/chemistry.md").read_text(encoding="utf-8"),
            canon,
        )

    def test_apply_is_idempotent_and_keeps_curated_lines(self):
        self.assertEqual(self._scaffold("--apply"), 0)
        canon = (self.repo / "skills/high-school-ai-tutor/references/nodes/chemistry.md").read_text(encoding="utf-8")
        self.assertTrue(canon.startswith("# id kp_ion 离子反应\n离子反应 |"))
        self.assertIn("# pipeline:begin chem-bx1-ch2", canon)
        self.assertIn("# id kp_na 钠的性质", canon)
        page = (self.repo / "skills/high-school-ai-tutor/references/study-pages/chem-bx1-ch2/kp_na.md").read_text(encoding="utf-8")
        self.assertIn("【模式：自学 · 状态：节点 · 节点：钠的性质】", page)
        self.assertIn("示例题非教材原题。", page)
        self.assertIn("已机验：通过", page)
        self.assertIn("（待补录：易混辨析）", page)
        self.assertEqual(page.split("已机验：通过")[0].count("Step 6"), 1)
        graph = (self.repo / "skills/high-school-ai-tutor/references/pep-chem-bx1-ch2.md").read_text(encoding="utf-8")
        self.assertIn("classDef concept fill:#E8F1FF,stroke:#3B6FB6,color:#1A1A1A", graph)
        self.assertIn("kp_na -->|直接前置| kp_na2o2", graph)
        self.assertIn("kp_na -.->|常考组合| kp_ion", graph)
        subprocess.check_call(["git", "add", "-A"], cwd=self.repo)
        subprocess.check_call(["git", "commit", "-m", "chapter"], cwd=self.repo)
        dump_before = dump_db(self.repo / "skills/high-school-ai-tutor/data/graph.db")
        self.assertEqual(self._scaffold("--apply"), 0)
        self.assertEqual(subprocess.call(["git", "diff", "--exit-code", "--", ".", ":(exclude)*.db"], cwd=self.repo), 0)
        self.assertEqual(dump_db(self.repo / "skills/high-school-ai-tutor/data/graph.db"), dump_before)

    def test_dangling_combo_writes_nothing(self):
        text = CHAPTER.replace("[kp_na, kp_ion, 常考组合]", "[kp_na, kp_missing, 常考组合]")
        self.chapter.write_text(text, encoding="utf-8")
        before = (self.repo / "skills/high-school-ai-tutor/references/nodes/chemistry.md").read_text(encoding="utf-8")
        self.assertEqual(self._scaffold("--apply"), 1)
        self.assertEqual(
            (self.repo / "skills/high-school-ai-tutor/references/nodes/chemistry.md").read_text(encoding="utf-8"),
            before,
        )
        self.assertFalse((self.repo / "skills/high-school-ai-tutor/references/pep-chem-bx1-ch2.md").exists())

    def test_does_not_rewrite_curated_id(self):
        text = CHAPTER.replace("id: kp_na\n", "id: kp_ion\n", 1).replace(
            "display: 钠的性质", "display: 另一种离子反应", 1
        ).replace("[kp_na, kp_na2o2", "[kp_ion, kp_na2o2")
        self.chapter.write_text(text, encoding="utf-8")
        before = (self.repo / "skills/high-school-ai-tutor/references/nodes/chemistry.md").read_text(encoding="utf-8")
        self.assertEqual(self._scaffold("--apply"), 1)
        self.assertEqual(
            (self.repo / "skills/high-school-ai-tutor/references/nodes/chemistry.md").read_text(encoding="utf-8"),
            before,
        )


class ExtractTests(unittest.TestCase):
    def test_splits_chapters_and_marks_blank_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_extract(out, ["封面", "第1章 物质及其变化\n正文", "", "第2章 钠和氯\n钠"])
            toc = (out / "toc.txt").read_text(encoding="utf-8")
            self.assertIn("第 2 页\t第1章 物质及其变化", toc)
            self.assertIn("无文本，需人工补页码", toc)
            chapters = sorted((out / "chapters").glob("*.txt"))
            self.assertEqual(len(chapters), 2)
            self.assertIn("正文", chapters[0].read_text(encoding="utf-8"))

    def test_reads_pdf_pages(self):
        from pypdf import PdfWriter

        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "blank.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            with pdf.open("wb") as handle:
                writer.write(handle)
            pages = extract_pages(pdf)
        self.assertEqual(len(pages), 1)


class NotesTests(unittest.TestCase):
    def test_skips_verbatim_excerpts(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "own.md").write_text("# 钠\n钠先与水反应，再考虑产物。\n", encoding="utf-8")
            (vault / "copy.md").write_text("---\ntags: [课文摘录]\n---\n钠的课文。\n", encoding="utf-8")
            (vault / "quote.md").write_text("> 钠\n> 整段课文\n> 还是课文\n\n", encoding="utf-8")
            hits, skipped = search_vault(vault, "钠")
        self.assertEqual([item["path"] for item in hits], ["own.md"])
        self.assertEqual(skipped, ["copy.md", "quote.md"])


class FeedbackTests(unittest.TestCase):
    def test_prints_alias_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            write_skill_tree(repo)
            code = feedback_main(["--repo", str(repo), "--pipeline-root", str(ROOT)])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
