#!/usr/bin/env python3
import unittest

from core.ir import load
from core.library import SeedEdge, SeedNode, Seeds, merge_canon, merge_seeds
from tests.support import CHAPTER

import yaml


class CanonMergeTests(unittest.TestCase):
    def test_existing_block_stays_in_place(self):
        existing = (
            "策展行\n\n"
            "# pipeline:begin bio-bx1-ch1\n"
            "# id kp_old 旧\n"
            "旧 |  | 章 | a | b | c\n"
            "# pipeline:end bio-bx1-ch1\n\n"
            "# pipeline:begin bio-bx1-ch2\n"
            "# id kp_keep 留\n"
            "留 |  | 章 | a | b | c\n"
            "# pipeline:end bio-bx1-ch2\n"
        )
        block = (
            "# pipeline:begin bio-bx1-ch1\n"
            "# id kp_new 新\n"
            "新 |  | 章 | a | b | c\n"
            "# pipeline:end bio-bx1-ch1\n"
        )
        merged = merge_canon(existing, "bio-bx1-ch1", block)
        self.assertTrue(merged.startswith("策展行\n"))
        self.assertLess(merged.index("bio-bx1-ch1"), merged.index("bio-bx1-ch2"))
        self.assertIn("# id kp_new 新", merged)
        self.assertNotIn("kp_old", merged)


class SeedOrderTests(unittest.TestCase):
    def test_unchanged_chapter_keeps_seed_order(self):
        data = yaml.safe_load(CHAPTER)
        data["chapter_id"] = "bio-bx1-ch1"
        data["subject"] = "生物"
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chapter.yaml"
            path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
            chapter = load(path)
        existing = Seeds(
            nodes=[
                SeedNode("kp_other", "生物", "其他", "bio-bx1-ch2", 0),
                SeedNode("kp_na", "生物", "钠的性质", "bio-bx1-ch1", 0),
                SeedNode("kp_na2o2", "生物", "过氧化钠", "bio-bx1-ch1", 0),
                SeedNode("ch3_fe", "生物", "第三章 铁", "bio-bx1-later", 1),
            ],
            edges=[
                SeedEdge("kp_other", "kp_na", "同章衔接"),
                SeedEdge("kp_na", "kp_na2o2", "直接前置"),
                SeedEdge("kp_na", "kp_ion", "常考组合"),
            ],
            owned_later={},
        )
        # kp_ion is not in this seed node list; combo endpoint must exist.
        existing.nodes.append(SeedNode("kp_ion", "生物", "离子反应", "bio-bx1-ch9", 0))
        merged, problems = merge_seeds(existing, [chapter])
        self.assertEqual(problems, [])
        self.assertEqual(
            [node.id for node in merged.nodes],
            ["kp_other", "kp_na", "kp_na2o2", "ch3_fe", "kp_ion"],
        )
        self.assertEqual(
            [(edge.src, edge.dst) for edge in merged.edges],
            [("kp_other", "kp_na"), ("kp_na", "kp_na2o2"), ("kp_na", "kp_ion")],
        )


if __name__ == "__main__":
    unittest.main()
