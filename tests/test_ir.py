#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path

from core.ir import load, validate_data
from tests.support import CHAPTER

import yaml


def _data():
    return yaml.safe_load(CHAPTER)


class IrTests(unittest.TestCase):
    def test_sample_chapter_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chapter.yaml"
            path.write_text(CHAPTER, encoding="utf-8")
            chapter = load(path)
        self.assertEqual([node.id for node in chapter.nodes], ["kp_na", "kp_na2o2"])
        self.assertEqual(chapter.edges[0].kind, "直接前置")
        self.assertTrue(chapter.combo[0].external)

    def test_cycle_and_dangling_edge_fail(self):
        data = _data()
        data["edges"] = [
            ["kp_na", "kp_na2o2", "直接前置"],
            ["kp_na2o2", "kp_na", "直接前置"],
        ]
        messages = "；".join(str(item) for item in validate_data(data))
        self.assertIn("有环", messages)

        data = _data()
        data["edges"] = [["kp_na", "kp_missing", "直接前置"]]
        messages = "；".join(str(item) for item in validate_data(data))
        self.assertIn("端点不存在", messages)

    def test_bad_label_and_verbatim_field_fail(self):
        data = _data()
        data["edges"] = [["kp_na", "kp_na2o2", "好像有关"]]
        messages = "；".join(str(item) for item in validate_data(data))
        self.assertIn("标签只能是", messages)

        data = _data()
        data["sections"][0]["nodes"][0]["原文"] = "钠是一种银白色金属"
        messages = "；".join(str(item) for item in validate_data(data))
        self.assertIn("未知字段", messages)


if __name__ == "__main__":
    unittest.main()
