#!/usr/bin/env python3
import unittest

from scripts.ci_dry_run import run_dry


class DriftDryRunTests(unittest.TestCase):
    def test_stub_proves_advance_validate_and_red_diff(self):
        run_dry()


if __name__ == "__main__":
    unittest.main()
