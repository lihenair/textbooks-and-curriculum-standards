#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path

from core.extract import write_extract


def _run(pages):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        write_extract(out, pages)
        toc = (out / "toc.txt").read_text(encoding="utf-8")
        chapter_names = sorted(p.name for p in (out / "chapters").glob("*.txt"))
        return toc, chapter_names


class ExtractTests(unittest.TestCase):
    def test_toc_page_with_dot_leaders_does_not_seed_chapters(self):
        toc_page = "\n".join(
            [
                "目录",
                "第一章",
                "绪论",
                "1",
                "第一节　研究对象 . . . . . . . . . . . . . . 1",
                "第二节　研究方法 . . . . . . . . . . . . . . 3",
                "第三节　基本特征 . . . . . . . . . . . . . . 5",
            ]
        )
        body1 = "第一章  绪论\n这是第一章正文。\n"
        body2 = "第二章  细胞\n这是第二章正文。\n"
        toc, names = _run([toc_page, body1, body2])
        self.assertIn("第 2 页\t第一章  绪论", toc)
        self.assertIn("第 3 页\t第二章  细胞", toc)
        self.assertNotIn("第 1 页\t第一章", toc)
        self.assertEqual(len(names), 2)

    def test_page_listing_several_chapters_is_not_chapter_start(self):
        list_page = "第一章  绪论 1\n第二章  细胞 12\n第三章  代谢 29\n"
        body1 = "第一章  绪论\n这是第一章正文。\n"
        toc, names = _run([list_page, body1])
        self.assertNotIn("第 1 页", toc)
        self.assertIn("第 2 页\t第一章  绪论", toc)
        self.assertEqual(len(names), 1)

    def test_consecutive_empty_pages_collapse_into_one_toc_line(self):
        pages = ["", "", "", "第一章  绪论\n正文。\n", "", ""]
        toc, _ = _run(pages)
        self.assertIn("第 1-3 页\t（无文本，需人工补页码，共 3 页）", toc)
        self.assertIn("第 5-6 页\t（无文本，需人工补页码，共 2 页）", toc)

    def test_out_of_sequence_heading_still_flagged(self):
        toc, _ = _run(["第一章  绪论\n正文。\n", "第三章  代谢\n正文。\n"])
        self.assertIn("（跳过，疑似页眉或引文）第三章  代谢", toc)


if __name__ == "__main__":
    unittest.main()
