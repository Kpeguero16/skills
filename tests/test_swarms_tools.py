"""Unit tests for skills/swarms-tools/scripts/swarms.py. Offline: nothing here calls gh or git."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("swarms_cli", ROOT / "skills/swarms-tools/scripts/swarms.py")
swarms = importlib.util.module_from_spec(spec)
sys.modules["swarms_cli"] = swarms
spec.loader.exec_module(swarms)


class Dates(unittest.TestCase):
    def test_dst_days_get_an_offset_per_end(self):
        try:
            from zoneinfo import ZoneInfo
            eastern = ZoneInfo("America/New_York")
        except Exception:  # Windows without the tzdata package
            self.skipTest("no tz database")
        self.assertEqual(
            swarms.day_range(dt.date(2026, 11, 1), eastern),
            ("2026-11-01T00:00:00-04:00", "2026-11-01T23:59:59-05:00"),
        )
        self.assertEqual(
            swarms.day_range(dt.date(2026, 3, 8), eastern),
            ("2026-03-08T00:00:00-05:00", "2026-03-08T23:59:59-04:00"),
        )

    def test_local_range_covers_the_day(self):
        start, end = swarms.day_range(dt.date(2026, 11, 4))
        self.assertTrue(start.startswith("2026-11-04T00:00:00"))
        self.assertTrue(end.startswith("2026-11-04T23:59:59"))

    def test_parse_day(self):
        self.assertEqual(swarms.parse_day("2026-11-04"), dt.date(2026, 11, 4))
        self.assertEqual(swarms.parse_day("yesterday"), dt.date.today() - dt.timedelta(days=1))

    def test_github_timestamps_parse(self):
        self.assertEqual(swarms.parse_ts("2026-11-04T12:00:00Z").utcoffset(), dt.timedelta(0))
        self.assertIsNotNone(swarms.parse_ts("2026-11-04T20:12:01.123Z"))


class Discord(unittest.TestCase):
    def test_escapes_formatting_characters(self):
        self.assertEqual(swarms.discord_escape("[FIX][Agent.__init__][a*b~c`d|e]"),
                         "[FIX][Agent.\\_\\_init\\_\\_][a\\*b\\~c\\`d\\|e]")

    def test_message_groups_sorts_and_drops_empty_repos(self):
        groups = {
            swarms.SWARMS: [
                {"title": "[FIX][b][Second]", "url": "https://x/2", "createdAt": "2026-11-04T15:00:00Z"},
                {"title": "[FIX][a_b][First]", "url": "https://x/1", "createdAt": "2026-11-04T14:00:00Z"},
            ],
            swarms.DOCS: [],
        }
        self.assertEqual(swarms.discord_message(groups),
                         "**Swarms**\n- [FIX][a\\_b][First] - <https://x/1>\n- [FIX][b][Second] - <https://x/2>")


class Titles(unittest.TestCase):
    def test_type_and_size(self):
        self.assertEqual(swarms.pr_type("[chore][x][y]"), "CHORE")
        self.assertEqual(swarms.pr_type("no prefix"), "")
        self.assertEqual([swarms.size_bucket(n) for n in (0, 29, 30, 99, 100, 299, 300)],
                         ["under 30", "under 30", "30 to 99", "30 to 99", "100 to 299", "100 to 299", "300 and up"])

    def test_budget_counts_swarms_and_tests_only(self):
        files = swarms.numstat_files("12\t1\tswarms/a.py\n34\t0\ttests/t.py\n50\t0\texamples/x.py\n-\t-\tswarms/i.png\n")
        self.assertEqual(swarms.budget_for(files), (12, 34, 15))
        self.assertEqual(swarms.budget_for([("swarms/a.py", 108), ("tests/t.py", 57)]), (108, 57, 108))


class Lint(unittest.TestCase):
    def test_flags_dashes_quotes_and_vocabulary_outside_code(self):
        text = "A crucial fix — really.\nSay “done”.\n```\ncrucial = 1\n```\nUse `delve` here."
        found = swarms.lint_text(text, vocabulary=["crucial", "delve"])
        self.assertIn((1, "em dash (unslop rule 13)"), found)
        self.assertIn((2, "curly quote (unslop rule 19)"), found)
        self.assertIn((1, "'crucial' (unslop rule 7)"), found)
        self.assertEqual([f for f in found if "rule 7" in f[1]], [(1, "'crucial' (unslop rule 7)")])

    def test_discord_limit(self):
        self.assertTrue(swarms.lint_text("x" * 2000, discord=True, vocabulary=[]))
        self.assertFalse(swarms.lint_text("x" * 1999, discord=True, vocabulary=[]))

    def test_vocabulary_comes_from_unslop_rule_7(self):
        words = swarms.unslop_vocabulary()
        self.assertIn("delve", words)
        self.assertNotIn("landscape", " ".join(words))  # marked (abstract): context decides


class Checks(unittest.TestCase):
    def test_rollup_normalizes_noise_and_reruns(self):
        rollup = [
            {"__typename": "CheckRun", "name": "test", "status": "COMPLETED", "conclusion": "FAILURE"},
            {"__typename": "CheckRun", "name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"},
            {"__typename": "CheckRun", "name": "lint", "status": "IN_PROGRESS", "conclusion": ""},
            {"__typename": "StatusContext", "context": "Bounty guard", "state": "FAILURE"},
        ]
        self.assertEqual(swarms.check_results(rollup, swarms.DOCS), [
            {"name": "Bounty guard", "result": "noise"},
            {"name": "lint", "result": "pending"},
            {"name": "test", "result": "pass"},
        ])

    def test_removed_lines_skip_headers_and_short_lines(self):
        diff = "\n".join([
            "diff --git a/x.py b/x.py", "--- a/x.py", "+++ b/x.py", "@@ -1,3 +0,0 @@",
            "-def helper_that_nobody_calls():", "-    )", "-    return compute_the_value(1)",
            "--- /dev/null", "+++ b/new.py", "+print('hi')",
        ])
        self.assertEqual(dict(swarms.removed_lines_by_file(diff)),
                         {"x.py": ["def helper_that_nobody_calls():", "return compute_the_value(1)"]})

    def test_docs_pr_is_not_ready_while_its_framework_pr_is_open(self):
        def fake(*args, json_out=True, **kwargs):
            args = tuple(map(str, args))
            if args[:3] == ("pr", "view", "https://github.com/The-Swarm-Corporation/swarms-framework-docs/pull/358"):
                return {"number": 358, "body": body,
                        "baseRefName": "main", "headRefOid": "a" * 40, "createdAt": "2026-11-01T00:00:00Z",
                        "updatedAt": "2026-11-04T00:00:00Z", "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN",
                        "reviewDecision": "", "isDraft": False, "labels": [], "comments": [], "reviews": [],
                        "commits": [], "statusCheckRollup": [], "deletions": 0}
            if args[:3] == ("pr", "view", "3124"):
                return {"state": state}
            if args[:3] == ("pr", "view", "2606"):
                raise swarms.GhError("gh pr view 2606: GraphQL: Could not resolve to a PullRequest with the number of 2606.")
            if args[:2] == ("api", "--paginate"):
                return []
            if args[0] == "api" and "/compare/" in args[1]:
                return {"behind_by": 0, "files": []}
            raise AssertionError(f"unexpected gh call {args}")

        url = "https://github.com/The-Swarm-Corporation/swarms-framework-docs/pull/358"
        body = "Tracks https://github.com/kyegomez/swarms/pull/3124."
        with mock.patch.object(swarms, "gh", fake):
            state = "OPEN"
            self.assertFalse(swarms.pr_facts(url)["ready"])
            state = "MERGED"
            self.assertTrue(swarms.pr_facts(url)["ready"])
            # Hand-written bodies name the PR in short form, next to the issue it closes.
            body = "Merge after kyegomez/swarms#3124. Closes kyegomez/swarms#2606."
            state = "OPEN"
            facts = swarms.pr_facts(url)
            self.assertEqual(facts["waits_on"], [{"pr": "kyegomez/swarms#3124", "state": "OPEN"}])
            self.assertFalse(facts["ready"])

    def test_ci_reports_only_failures_the_forked_base_did_not_have(self):
        stamp = "2026-11-07T13:31:32.6984345Z "
        base_log = "\n".join([stamp + "\x1b[31mFAILED tests/a.py::test_old - boom\x1b[0m",
                              stamp + "swarms/p.py:4:8: F401 [*] `uuid` imported but unused"])
        cases = [  # (PR log, base conclusion, expected exit, expected line)
            (base_log.replace(":4:8:", ":9:8:"), "failure", 0, "PASS test: 2 failures here, 0 not on master"),
            (base_log + "\nFAILED tests/b.py::test_new - x", "failure", 1, "  FAILED tests/b.py::test_new"),
            (base_log, "success", 1, "FAIL test: fails here and passes on master"),
            ("no test names here", "failure", 1, "WARN test: fails here and on master, and the log names no test"),
        ]
        for pr_log, base_conclusion, code, line in cases:
            def fake(*args, json_out=True, **kwargs):
                args = tuple(map(str, args))
                if args[:2] == ("pr", "view"):
                    return {"headRefOid": "h" * 40, "statusCheckRollup": [
                        {"name": "test", "status": "COMPLETED", "conclusion": "FAILURE",
                         "detailsUrl": "https://github.com/kyegomez/swarms/actions/runs/1/job/11"},
                        {"name": "lint", "status": "COMPLETED", "conclusion": "SUCCESS"}]}
                if args[-1].endswith(f"/compare/master...{'h' * 40}"):
                    return {"merge_base_commit": {"sha": "f" * 40}}
                if args[-1].endswith(f"commits?sha={'f' * 40}&per_page=10"):
                    return [{"sha": "f" * 40}]
                if "/check-runs" in args[-1]:
                    return {"check_runs": [{"id": 22, "name": "test", "status": "completed", "conclusion": base_conclusion}]}
                if args[-1].endswith("/jobs/11/logs"):
                    return pr_log
                if args[-1].endswith("/jobs/22/logs"):
                    return base_log
                raise AssertionError(f"unexpected gh call {args}")

            with self.subTest(line=line), mock.patch.object(swarms, "gh", fake):
                lines, got = swarms.ci_report(swarms.SWARMS, 7)
                self.assertEqual(got, code, lines)
                self.assertTrue(any(l.startswith(line) for l in lines), lines)

    def test_bots(self):
        self.assertTrue(swarms.is_bot("coderabbitai[bot]"))
        self.assertTrue(swarms.is_bot("github-actions"))
        self.assertFalse(swarms.is_bot("kyegomez"))


class Ledger(unittest.TestCase):
    def test_round_trip_upsert_and_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "outcomes.tsv"
            rows = []
            swarms.ledger_upsert(rows, listed="2026-11-01", item="[CHORE][a][Delete a]", source="deletion", est_lines="6")
            swarms.ledger_upsert(rows, item="[CHORE][a][Delete a]", pr="kyegomez/swarms#1", state="merged",
                                 lines="6", hours="1.5", type="CHORE")
            swarms.ledger_upsert(rows, listed="2026-11-01", item="[FIX][b][Fix b]\twith a tab", pr="kyegomez/swarms#2",
                                 state="closed", lines="140", type="FIX", reason="Not needed.\nThanks")
            swarms.write_ledger(path, rows)
            back = swarms.read_ledger(path)
            self.assertEqual(len(back), 2)
            self.assertEqual(back[0]["source"], "deletion")
            self.assertEqual(back[0]["pr"], "kyegomez/swarms#1")
            self.assertEqual(back[1]["item"], "[FIX][b][Fix b] with a tab")
            self.assertEqual(back[1]["reason"], "Not needed. Thanks")
            stats = swarms.ledger_stats(back, None, swarms.SWARMS)
            self.assertIn("| CHORE | 1 | 1 | 0 | 0 | 1.5 |", stats)
            self.assertIn("| 100 to 299 | 1 | 0 | 0 | 1 |  |", stats)
            self.assertIn("kyegomez/swarms#2 [FIX][b][Fix b] with a tab: Not needed. Thanks", stats)

    def test_failed_write_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "outcomes.tsv"
            with mock.patch.object(swarms.os, "replace", side_effect=PermissionError("locked")):
                with self.assertRaises(PermissionError):
                    swarms.write_ledger(path, [{"pr": "x#1"}])
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_empty_values_never_overwrite(self):
        rows = [{"item": "x", "source": "issue #1", "pr": ""}]
        swarms.ledger_upsert(rows, item="x", source="", est_lines="5", reason=None)
        self.assertEqual(rows[0]["source"], "issue #1")
        self.assertEqual(rows[0]["est_lines"], "5")
        rows[0]["reason"] = "keep this"
        swarms.ledger_upsert(rows, item="x", source=" \t\n ", reason="  ")  # whitespace is empty too
        self.assertEqual((rows[0]["source"], rows[0]["reason"]), ("issue #1", "keep this"))

    def test_a_post_under_another_item_name_lands_on_the_pick_with_the_same_brief(self):
        clone = Path(tempfile.gettempdir()) / "swarms-clone"
        brief = "tasks/handoffs/2026-11-05/3-dead-test.md"
        pick = {"listed": "2026-11-05", "item": "[TEST][t][Delete the dead test]", "source": "deletion",
                "est_lines": "55", "pr": "", "brief": brief, "state": "listed"}
        with mock.patch.dict(os.environ, {"SWARMS_REPO": str(clone)}):
            rows = [dict(pick)]  # posted later under a reworded item and the absolute brief
            swarms.ledger_upsert(rows, item="Delete the dead test", pr="kyegomez/swarms#9", source="daily-opportunities",
                                 est_lines="57", brief=str(clone / brief), state="open")
            # Rows the old code already split: sync folds them back into one.
            split = [dict(pick), {"listed": "2026-11-05", "item": "Delete the dead test", "pr": "kyegomez/swarms#9",
                                  "brief": str(clone / brief), "state": "merged", "source": "daily-opportunities"}]
            self.assertEqual(swarms.fold_by_brief(split), 1)
        for got in (rows, split):
            self.assertEqual(len(got), 1)
            self.assertEqual((got[0]["pr"], got[0]["item"], got[0]["source"], got[0]["est_lines"]),
                             ("kyegomez/swarms#9", "[TEST][t][Delete the dead test]", "deletion", "55"))

    def test_infer_source(self):
        self.assertEqual(swarms.infer_source("Closes #3157.\n\nDeletes it."), "issue #3157")
        self.assertEqual(swarms.infer_source("No issue."), "")


class Publish(unittest.TestCase):
    def test_render_fills_known_and_marks_pending(self):
        posted = {"framework": {"url": "https://github.com/kyegomez/swarms/pull/9", "number": 9}}
        text = "Tracks #{{framework.number}}. Docs: {{docs.url}}"
        self.assertEqual(swarms.render(text, posted), "Tracks #9. Docs: (linked in a moment)")

    def test_placeholders(self):
        found = swarms.PLACEHOLDER.findall("tests: <N> passed by <model>; Docs: <docs PR link>; see <https://x.y>")
        self.assertEqual(found, ["<N>", "<model>", "<docs PR link>"])

    def test_manifest_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "publish.json").write_text(
                '{"prs": [{"id": "framework", "repo": "kyegomez/swarms", "head": "Kpeguero16:refactor/x",'
                ' "sha": "abc", "title": "t.txt", "body": "b.md"}]}', encoding="utf-8")
            m = swarms.load_manifest(Path(tmp))
            pr = m["prs"][0]
            self.assertEqual((pr["base"], pr["label"], pr["drift"]), ("master", True, "fail"))
            self.assertEqual(swarms.approved_files(m), ["publish.json", "t.txt", "b.md"])


class FakeGh:
    """Answers the gh calls publish makes, and records them."""

    def __init__(self, labeled_after_edit: bool = True, fail_create: str = "", fail_edits: int = 0):
        self.calls: list[tuple] = []
        self.fail_create, self.fail_edits = fail_create, fail_edits
        self.next_number = 100
        self.edited: set[str] = set()
        self.labeled_after_edit = labeled_after_edit

    def __call__(self, *args, json_out=True, **kwargs):
        args = tuple(map(str, args))
        self.calls.append(args)
        if args[:2] == ("pr", "create"):
            repo = args[args.index("--repo") + 1]
            if repo == self.fail_create:
                raise swarms.GhError("HTTP 502")
            self.next_number += 1
            return f"https://github.com/{repo}/pull/{self.next_number}\n"
        if args[:2] == ("pr", "edit"):
            if self.fail_edits:
                self.fail_edits -= 1
                raise swarms.GhError("HTTP 502")
            self.edited.add(args[2])
            return ""
        if args[:2] == ("pr", "view"):
            on = args[2] in self.edited and self.labeled_after_edit
            return {"labels": [{"name": swarms.AI_LABEL}] if on else []}
        if args[:2] == ("api", "user"):
            return "Kpeguero16\n"
        raise AssertionError(f"unexpected gh call {args}")


class PublishFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.task = Path(self.tmp.name) / "task"
        self.task.mkdir()
        files = {
            "pr_title.txt": "[FEAT][X.arun][Add an awaitable entry point]\n",
            "pr_body.md": "Closes #1.\n\nDocs: {{docs.url}}\n\n🤖 Generated with Claude Code\n",
            "pr_body_relabel.md": "Closes #1.\n\nDocs PR: {{docs.url}}\n\n🤖 Generated with Claude Code\n",
            "docs_title.txt": "[DOCS][X.arun][Document it (tracks swarms #{{framework.number}})]\n",
            "docs_body.md": "Tracks {{framework.url}}.\n\n🤖 Generated with Claude Code\n",
        }
        for name, text in files.items():
            (self.task / name).write_text(text, encoding="utf-8")
        self.manifest = {
            "item": "[FEAT][X.arun][Add an awaitable entry point]", "source": "issue #1", "est_lines": "40",
            "prs": [
                {"id": "framework", "repo": swarms.SWARMS, "head": "Kpeguero16:feat/x-arun", "sha": "a" * 40,
                 "title": "pr_title.txt", "body": "pr_body.md", "relabel_body": "pr_body_relabel.md"},
                {"id": "docs", "repo": swarms.DOCS, "head": "Kpeguero16:docs/x-arun", "sha": "b" * 40,
                 "title": "docs_title.txt", "body": "docs_body.md"},
            ],
        }
        (self.task / "publish.json").write_text(__import__("json").dumps(self.manifest), encoding="utf-8")
        self.saved = (swarms.gh, os.environ.get("SWARMS_TASKS"))
        os.environ["SWARMS_TASKS"] = str(Path(self.tmp.name) / "tasks")

    def tearDown(self):
        swarms.gh = self.saved[0]
        if self.saved[1] is None:
            os.environ.pop("SWARMS_TASKS", None)
        else:
            os.environ["SWARMS_TASKS"] = self.saved[1]
        self.tmp.cleanup()

    def post(self, fake):
        import contextlib
        import io
        swarms.gh = fake
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = swarms.publish_post(self.task, swarms.load_manifest(self.task), label_wait=0)
        return code, out.getvalue()

    def test_posts_in_order_fills_links_relabels_and_records(self):
        fake = FakeGh()
        code, out = self.post(fake)
        self.assertEqual(code, 0, out)
        creates = [c for c in fake.calls if c[:2] == ("pr", "create")]
        self.assertEqual([c[c.index("--repo") + 1] for c in creates], [swarms.SWARMS, swarms.DOCS])
        self.assertIn("[DOCS][X.arun][Document it (tracks swarms #101)]", creates[1])
        # The framework body named the docs PR, which didn't exist yet, so it gets one edit with the link.
        # That edit changes the wording, which re-runs the labeler, so no relabel edit follows.
        framework = "https://github.com/kyegomez/swarms/pull/101"
        edits = [c for c in fake.calls if c[:2] == ("pr", "edit")]
        self.assertEqual([c[2] for c in edits], [framework])
        self.assertIn("LINKED framework", out)
        self.assertIn("LABEL [framework] ai-generated present", out)
        self.assertTrue(out.rstrip().endswith(f"DISCORD\n[FEAT][X.arun][Add an awaitable entry point]\n{framework}"))
        rows = swarms.read_ledger(swarms.ledger_path())
        self.assertEqual((rows[0]["pr"], rows[0]["source"], rows[0]["est_lines"]), ("kyegomez/swarms#101", "issue #1", "40"))

    def test_relabel_edit_runs_once_when_the_label_is_missing(self):
        self.manifest["prs"] = self.manifest["prs"][:1]
        (self.task / "pr_body.md").write_text("Closes #1.\n\n🤖 Generated with Claude Code\n", encoding="utf-8")
        (self.task / "publish.json").write_text(__import__("json").dumps(self.manifest), encoding="utf-8")
        fake = FakeGh()
        code, out = self.post(fake)
        self.assertEqual(code, 0, out)
        self.assertEqual(len([c for c in fake.calls if c[:2] == ("pr", "edit")]), 1)
        self.assertIn("LABEL [framework] ai-generated present after the wording edit", out)

    def test_label_still_missing_is_reported(self):
        self.manifest["prs"] = self.manifest["prs"][:1]
        (self.task / "pr_body.md").write_text("Closes #1.\n\n🤖 Generated with Claude Code\n", encoding="utf-8")
        (self.task / "publish.json").write_text(__import__("json").dumps(self.manifest), encoding="utf-8")
        code, out = self.post(FakeGh(labeled_after_edit=False))
        self.assertEqual(code, 0, out)
        self.assertIn("still missing after the wording edit", out)

    def test_security_pr_never_gets_the_public_channel(self):
        self.manifest["security"] = True
        (self.task / "publish.json").write_text(__import__("json").dumps(self.manifest), encoding="utf-8")
        code, out = self.post(FakeGh())
        self.assertEqual(code, 0)
        self.assertIn("DISCORD #management or product channel only", out)

    def test_partial_create_still_records_the_ledger_row(self):
        code, out = self.post(FakeGh(fail_create=swarms.DOCS))
        self.assertEqual(code, 3, out)
        self.assertIn("RESULT PARTIAL: [docs] gh pr create failed", out)
        self.assertIn("not posted: docs", out)
        self.assertEqual(swarms.read_ledger(swarms.ledger_path())[0]["pr"], "kyegomez/swarms#101")

    def test_failed_link_fill_is_partial_and_names_the_fix(self):
        code, out = self.post(FakeGh(fail_edits=99))
        self.assertEqual(code, 3, out)
        saved = self.task / "framework.linked.md"
        self.assertIn(f"RESULT PARTIAL: posted", out)
        self.assertIn(f"gh pr edit https://github.com/kyegomez/swarms/pull/101 --body-file {saved}", out)
        self.assertIn("Docs: https://github.com/The-Swarm-Corporation/swarms-framework-docs/pull/102",
                      saved.read_text(encoding="utf-8"))
        self.assertEqual(swarms.read_ledger(swarms.ledger_path())[0]["pr"], "kyegomez/swarms#101")

    def test_a_relabel_edit_that_lands_finishes_a_failed_link_fill(self):
        fake = FakeGh(fail_edits=1)  # the link fill fails; the relabel edit, with links filled, lands
        code, out = self.post(fake)
        self.assertEqual(code, 0, out)
        self.assertIn("LINKED framework the wording edit filled the links", out)
        self.assertIn("RESULT posted", out)

    def checks(self, on=None):
        fake = FakeGh()
        shas = {"feat/x-arun": "a" * 40, "docs/x-arun": "b" * 40}

        def answer(*args, json_out=True, **kwargs):
            args = tuple(map(str, args))
            if args[0] == "api" and "/git/ref/heads/" in args[1]:
                return shas[args[1].split("/git/ref/heads/")[1]] + "\n"
            if args[0] == "api" and "/compare/" in args[1]:
                return {"ahead_by": 1, "behind_by": 0, "files": [], "merge_base_commit": {"sha": "c" * 40}}
            if args[:2] == ("pr", "list"):
                return []
            return fake(*args, json_out=json_out, **kwargs)

        swarms.gh = answer
        return swarms.publish_checks(self.task, swarms.load_manifest(self.task), on)

    def test_checks_pass_on_approved_text(self):
        swarms.main(["publish", "approve", str(self.task)])
        lines = self.checks()
        self.assertFalse([line for line in lines if line.startswith("FAIL")], lines)

    def test_checks_catch_edits_placeholders_missing_disclosure_and_wrong_day(self):
        swarms.main(["publish", "approve", str(self.task)])
        (self.task / "pr_body.md").write_text("Closes #1.\n\nTests: <N> passed. Docs: {{doc.url}}\n", encoding="utf-8")
        fails = [line for line in self.checks(on="2000-01-01") if line.startswith("FAIL")]
        self.assertTrue(any("but this publish is for 2000-01-01" in f for f in fails), fails)
        self.assertTrue(any("approved text changed or missing: pr_body.md" in f for f in fails), fails)
        self.assertTrue(any("still has placeholders: <N>" in f for f in fails), fails)
        self.assertTrue(any("no '🤖 Generated with' line" in f for f in fails), fails)
        self.assertTrue(any("names unknown PR ids: doc" in f for f in fails), fails)

    def test_checks_catch_a_manifest_edit_after_approval(self):
        swarms.main(["publish", "approve", str(self.task)])
        self.manifest["prs"][0]["base"] = "release"
        (self.task / "publish.json").write_text(__import__("json").dumps(self.manifest), encoding="utf-8")
        fails = [line for line in self.checks() if line.startswith("FAIL")]
        self.assertTrue(any("approved text changed or missing: publish.json" in f for f in fails), fails)

    def test_checks_catch_a_relabel_body_without_disclosure(self):
        (self.task / "pr_body_relabel.md").write_text("Closes #1.\n\nDocs PR: {{docs.url}}\n", encoding="utf-8")
        swarms.main(["publish", "approve", str(self.task)])
        fails = [line for line in self.checks() if line.startswith("FAIL")]
        self.assertTrue(any("pr_body_relabel.md has no '🤖 Generated with' line" in f for f in fails), fails)

    def test_checks_catch_a_title_that_names_a_later_pr(self):
        (self.task / "pr_title.txt").write_text("[FEAT][X.arun][Add it (docs in {{docs.url}})]\n", encoding="utf-8")
        swarms.main(["publish", "approve", str(self.task)])
        fails = [line for line in self.checks() if line.startswith("FAIL")]
        self.assertTrue(any("pr_title.txt names docs, which posts after it" in f for f in fails), fails)

    def test_checks_fail_without_approval(self):
        fails = [line for line in self.checks() if line.startswith("FAIL")]
        self.assertTrue(any("no approved.sha256" in f for f in fails), fails)


class Scans(unittest.TestCase):
    def test_unused_finds_unread_names_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            (tree / "swarms").mkdir()
            (tree / "tests").mkdir()
            (tree / "swarms" / "mod.py").write_text(
                "LIMIT = 3\nUNUSED_LIMIT = 4\n\n"
                "def used():\n    return LIMIT\n\n"
                "def dead():\n    return 1\n\n"
                "class Box:\n    def __init__(self):\n        self.kept = 1\n        self.write_only = 2\n\n"
                "    def size(self):\n        return self.kept\n",
                encoding="utf-8")
            (tree / "tests" / "test_mod.py").write_text("from swarms.mod import used, Box\nused()\nBox().size()\n",
                                                        encoding="utf-8")
            found = {d["name"] for d in swarms.find_unused([tree / "swarms"], tree, None)}
            self.assertEqual(found, {"UNUSED_LIMIT", "dead", "write_only"})
            hits = swarms.scan_names(["used"], tree, None)["used"]
            self.assertEqual(hits["areas"], {"swarms": 1, "tests": 2})


class Environment(unittest.TestCase):
    def test_pinned_env_blanks_keys_and_pins_the_tree(self):
        os.environ["SOME_PROVIDER_API_KEY"] = "secret"
        try:
            env = swarms.pinned_env(Path("/tmp/tree"))
        finally:
            del os.environ["SOME_PROVIDER_API_KEY"]
        self.assertEqual(env["SOME_PROVIDER_API_KEY"], "")
        self.assertEqual(env["OPENAI_API_KEY"], "")
        self.assertEqual(env["SWARMS_TELEMETRY_ON"], "false")
        self.assertEqual(env["PYTHONPATH"], str(Path("/tmp/tree")))

    def test_resolve_command_uses_the_venv(self):
        py = Path("/venv/bin/python")
        self.assertEqual(swarms.resolve_command(["pytest", "-q"], py), [str(py), "-m", "pytest", "-q"])
        self.assertEqual(swarms.resolve_command(["python", "x.py"], py), [str(py), "x.py"])
        self.assertEqual(swarms.resolve_command(["no-such-tool-here", "x"], py), ["no-such-tool-here", "x"])

    def test_resolve_command_runs_shims_on_path(self):
        """npx is npx.cmd on Windows, which runs only by its full path."""
        with tempfile.TemporaryDirectory() as tmp:
            if os.name == "nt":
                shim = Path(tmp) / "fakeshim.cmd"
                shim.write_text("@echo shim ok\r\n", encoding="utf-8")
            else:
                shim = Path(tmp) / "fakeshim"
                shim.write_text("#!/bin/sh\necho shim ok\n", encoding="utf-8")
                shim.chmod(0o755)
            with mock.patch.dict(os.environ, {"PATH": tmp + os.pathsep + os.environ.get("PATH", "")}):
                cmd = swarms.resolve_command(["fakeshim"], Path(sys.executable))
                out = subprocess.run(cmd, capture_output=True, text=True).stdout
        self.assertTrue(Path(cmd[0]).is_absolute(), cmd)
        self.assertEqual(Path(cmd[0]).name.lower(), shim.name.lower())
        self.assertIn("shim ok", out)

    def test_read_remotes_from_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            git = Path(tmp) / ".git"
            git.mkdir()
            (git / "config").write_text(
                '[core]\n\tbare = false\n[remote "upstream"]\n\turl = https://github.com/kyegomez/swarms.git\n'
                '[remote "origin"]\n\turl = https://github.com/Kpeguero16/swarms.git\n[branch "master"]\n\tremote = origin\n',
                encoding="utf-8")
            self.assertEqual(swarms.read_remotes(Path(tmp)), {
                "upstream": "https://github.com/kyegomez/swarms.git",
                "origin": "https://github.com/Kpeguero16/swarms.git",
            })
            self.assertEqual(swarms.upstream_remote(Path(tmp), swarms.SWARMS), "upstream")

    def test_checkout_runs_only_fetch_and_worktree_in_the_main_clone(self):
        """AGENTS.md: other sessions share the main clones, so only fetch and worktree run there."""
        calls = []

        def fake_git(path, *args, check=True):
            calls.append((Path(path), args))
            return {"merge-base": "b" * 40, "rev-parse": "c" * 40}.get(args[0], "")

        with tempfile.TemporaryDirectory() as tmp:
            clone, run = Path(tmp) / "clone", Path(tmp) / "run"
            run.mkdir()
            (run / "swarms-12.json").write_text('{"baseRefName": "master", "headRefOid": "' + "a" * 40 + '"}',
                                                encoding="utf-8")
            os.environ["SWARMS_REPO"] = str(clone)
            try:
                with mock.patch.object(swarms, "git", fake_git), \
                        mock.patch.object(swarms, "upstream_remote", lambda c, r: "upstream"):
                    made = swarms.checkout(run, [(swarms.SWARMS, "pr:12"), (swarms.SWARMS, "master")])
            finally:
                del os.environ["SWARMS_REPO"]
        in_clone = {args[0] for path, args in calls if path == clone}
        self.assertEqual(in_clone, {"fetch", "worktree"})
        self.assertEqual([m["head_sha"] for m in made], ["a" * 40, "c" * 40])
        self.assertEqual(made[0]["base_sha"], "b" * 40)


class Secrets(unittest.TestCase):
    def test_redact(self):
        self.assertEqual(swarms.redact("https://Kpeguero16:ghp_abcdefghijklmnopqrstuvwxyz0123@github.com/x.git"),
                         "https://***@github.com/x.git")
        self.assertEqual(swarms.redact("export OPENAI_API_KEY=sk-live-123 and token: abc"),
                         "export OPENAI_API_KEY=*** and token: ***")
        self.assertEqual(swarms.redact("use sk-proj-ABCDEFGHIJKLMNOPQRST here"), "use *** here")
        self.assertEqual(swarms.redact("https://github.com/kyegomez/swarms.git"), "https://github.com/kyegomez/swarms.git")
        self.assertEqual(swarms.redact('{"PASSWORD": "SYNTHETIC_NOT_REAL", "user": "k"}'), '{"PASSWORD": "***", "user": "k"}')
        self.assertEqual(swarms.redact("{'api_key': 'sk_live_x,y'}"), "{'api_key': '***'}")
        self.assertEqual(swarms.redact("PASSWORD=ab,cd and TOKEN=abc}def"), "PASSWORD=*** and TOKEN=***")
        self.assertEqual(swarms.redact('PASSWORD="unterminated'), "PASSWORD=***")

    def test_errors_are_redacted_before_they_are_cut(self):
        key = "sk-proj-" + "S" * 30
        line = {"type": "user", "timestamp": "2026-11-05T10:00:00Z", "message": {"content": [
            {"type": "tool_result", "is_error": True, "content": "E" * 109 + " " + key}]}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.jsonl"
            path.write_text(json.dumps(line) + "\n", encoding="utf-8")
            errors = swarms.summarize_claude(path)["errors"]
        self.assertEqual(list(errors), ["E" * 109 + " ***"])

    def test_redacted_errors_keep_their_counts(self):
        pc = [{"harness": "codex", "path": "a.jsonl", "tools": {}, "errors": {"ERROR TOKEN=alpha": 2, "ERROR TOKEN=beta": 3},
               "first": "", "start": "", "minutes": 1, "tool_calls": 0, "error_count": 5, "machine": "pc"}]
        with tempfile.TemporaryDirectory() as tmp:
            saved = Path(tmp) / "pc.json"
            saved.write_text(json.dumps(pc), encoding="utf-8")
            with mock.patch("pathlib.Path.home", return_value=Path(tmp) / "empty-home"):
                rows = swarms.transcripts(7, "swarms", [str(saved)])
        self.assertEqual(dict(rows[0]["errors"]), {"ERROR TOKEN=***": 5})


class Transcripts(unittest.TestCase):
    def test_another_machines_sessions_merge_in(self):
        pc = [{"harness": "codex", "path": "C:\\Users\\k\\.codex\\sessions\\a.jsonl", "tools": {"shell": 9},
               "errors": {"exit 1: pytest": 3}, "first": "fix it, OPENAI_API_KEY=sk-test-123", "cwd": "C:\\swarms", "start": "2026-11-03 09:00",
               "minutes": 40, "tool_calls": 9, "error_count": 3, "machine": "pc"}]
        with tempfile.TemporaryDirectory() as tmp:
            saved = Path(tmp) / "pc.json"
            saved.write_text(json.dumps(pc), encoding="utf-8")
            with mock.patch("pathlib.Path.home", return_value=Path(tmp) / "empty-home"):
                rows = swarms.transcripts(7, "swarms", [str(saved)])
                self.assertEqual(swarms.main(["transcripts", "--add", str(saved), "--json", str(Path(tmp) / "out.json")]), 0)
            again = json.loads((Path(tmp) / "out.json").read_text(encoding="utf-8"))
        self.assertEqual([r["machine"] for r in rows], ["pc"])
        self.assertEqual(rows[0]["errors"].most_common(1), [("exit 1: pytest", 3)])
        self.assertEqual(rows[0]["first"], "fix it, OPENAI_API_KEY=***")
        self.assertEqual(again[0]["first"], "fix it, OPENAI_API_KEY=***")


class Cli(unittest.TestCase):
    def test_today_runs(self):
        self.assertEqual(swarms.main(["today", "--date", "2026-11-04"]), 0)


if __name__ == "__main__":
    unittest.main()
