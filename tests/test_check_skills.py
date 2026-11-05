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


class Cli(unittest.TestCase):
    parser = check_skills.swarms.build_parser()

    def errors(self, body):
        return check_skills.cli_errors("x.md", body, self.parser)

    def test_real_calls_pass(self):
        body = ("Run `python3 $T ledger stats --days 7`, then `python3 $T publish post <task dir> --on 2026-11-05`.\n"
                "```\npython3 $T prove --base B --head H --copy tests/t.py \\\n    --evidence <dir> -- pytest -q -p x\n```")
        self.assertEqual(self.errors(body), [])

    def test_unknown_command_action_and_flag_fail(self):
        self.assertEqual(self.errors("`python3 $T statuss`"), ["x.md: swarms.py has no command `statuss`"])
        self.assertEqual(self.errors("`python3 $T publish posts <dir>`"), ["x.md: swarms.py publish has no action `posts`"])
        self.assertEqual(self.errors("`swarms.py ledger stats --dayz 7`"),
                         ["x.md: swarms.py ledger stats has no flag `--dayz`"])

    def test_flags_in_a_continued_code_line_are_checked(self):
        body = "```\npython3 $T prove --base B --head H \\\n    --evidnce <dir> -- pytest -q\n```"
        self.assertEqual(self.errors(body), ["x.md: swarms.py prove has no flag `--evidnce`"])

    def test_flags_after_a_bare_double_dash_belong_to_the_command_run(self):
        self.assertEqual(self.errors("`python3 $T run --tree T -- pytest --lf`"), [])


if __name__ == "__main__":
    unittest.main()
