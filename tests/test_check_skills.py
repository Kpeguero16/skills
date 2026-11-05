"""Unit tests for scripts/check_skills.py."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("check_skills", ROOT / "scripts/check_skills.py")
check_skills = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_skills)


class Links(unittest.TestCase):
    def test_existing_paths_pass(self):
        body = "Read `../full-send/SKILL.md`. Run ../swarms-tools/scripts/swarms.py, then see ../unslop/."
        self.assertEqual(check_skills.link_errors("x.md", body), [])

    def test_missing_file_in_a_real_skill_fails(self):
        errors = check_skills.link_errors("x.md", "Follow ../full-stop/DOES-NOT-EXIST.md")
        self.assertEqual(errors, ["x.md: names ../full-stop/DOES-NOT-EXIST.md, which doesn't exist"])

    def test_missing_skill_fails(self):
        errors = check_skills.link_errors("x.md", "Follow ../no-such-skill/SKILL.md")
        self.assertEqual(errors, ["x.md: names ../no-such-skill/, which isn't a skill in this repo"])


if __name__ == "__main__":
    unittest.main()
