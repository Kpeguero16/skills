---
name: swarms-own
description: Take one swarms brief or PR from start to ready for Kye. "Own it, full stop" stops once for Khalil's approval of the PR text, and "own it, full send" posts a small PR on Sol's approval instead. Use when the user says "own it", as "own it, full stop" or "own it, full send", with a brief path from tasks/handoffs or a PR number.
---

# Own it

One thread owns one item, a brief in `tasks/handoffs/<date>/` or an existing PR, until it's ready for Kye. It's Theo's `full-stop` with the swarms rules below. Kye merges; this thread never does, in either mode.

- **Full stop**, from "own it, full stop": step 7 asks me to approve the PR text. Big PRs and security fixes always run this way, and so does any run whose message doesn't say "full send".
- **Full send**, from "own it, full send": Sol's approval in step 5 replaces mine, and step 7 posts without asking. It covers a framework PR of 100 changed lines or fewer that isn't a security fix. Anything else falls back to full stop at step 7. `full-send`'s merge permission doesn't apply.

Read `../full-stop/SKILL.md` and `../full-send/SKILL.md`, next to this skill's folder, if they aren't loaded. Where they differ from this file, this file wins. `$T` is `../swarms-tools/scripts/swarms.py`. AGENTS.md has the PR conventions.

## Steps

1. **Restate.** Read the brief. In two or three sentences, give the goal and the smallest change that meets it, before any edit. If master moved, find the code with grep rather than the brief's line numbers. Run `python3 $T competition <issue> <symbol>`, and say so if someone has opened a PR since the brief was written. The brief names the item's issue. When it names none, write a draft as `swarms-picks` step 6 describes, review it with Sol as `swarms-picks` step 7 does, and open it with `python3 $T open-issue <draft>` before step 2. Don't ask me first. A security fix gets no issue.
2. **Prove the problem on master** with `verify-swarms`, before changing anything: a failing test or repro in a base tree. Write the test you'll ship short from the start, as "Tests" below says. For a deletion, prove the fact that makes it safe with `python3 $T scan <name> --tree <base tree> --docs <docs tree>`.
3. **Make the smallest change** in this worktree. Show the same check red on the base and green here with `python3 $T prove`. A deletion has nothing to turn red: run the module's tests on both trees and show the pass and fail sets match, as `verify-swarms` describes. Save the evidence in `tasks/<slug>/evidence/`. Run black and ruff on the changed files. Commit with the co-author trailer, then run `python3 $T test-budget --tree .` and `python3 $T style --tree .`. `style` checks the lines you added against Kye's written style rules; fix each line it names, then commit and run it again.
4. **Write the PR text** in `tasks/<slug>/`: `pr_title.txt`, `pr_body.md`, and `pr_body_relabel.md` (the same body with one real wording change). Use `file-pr`'s problem-first body, add the before-and-after evidence, and say whether the change is a one-way or two-way door. The body closes the issue with `Closes #N`, or says `Part of #N` for one PR of a split big PR. A docs PR also gets `docs_title.txt` and `docs_body.md`, which names the issue as `kyegomez/swarms#N`. A security fix has no issue to name: set `"security": true` in `publish.json` after step 6's `publish init`. Apply `unslop`, then `python3 $T lint <files>`.
5. **Review with `sol-loop`**: at most three rounds, each finding marked blocker, should or nit, stopping when only nits remain. A finding counts only if rerunning its command, or a repro you write for it, shows the failure. Decline the rest with that evidence. Don't push during the loop. Sol reviews the PR text with the code: add `PR text: <paths>. It goes public in Khalil's name. A claim the diff or the evidence doesn't support is a should.` to the round 1 brief, and keep the text in step with each fix. A text finding counts when the diff or the proof output contradicts the claim. In full send, this review is the approval, so it has to end in APPROVE on the final diff and text: a text change after Sol's last APPROVE, even a wording fix that `sol-loop` would let pass, goes to Sol in one more round. A loop that ends stuck or on its budget falls back to full stop.
6. **Push** to my fork with `git push origin HEAD:refs/heads/<branch>`, without renaming the worktree's branch, after committing every review fix, so the pushed commit is the diff Sol reviewed. Then run `publish init` and fill in the competition terms, as `swarms-publish` describes.
7. **Ask me, or go on in full send.** In full stop, ask me with the harness's question tool. Put the full title and body in the question, with the proof in one line and the `test-budget` and `style` lines, and offer: approve and post now, approve and post at a time I give, or change something. A question in a normal reply looks like a finished thread and gets missed. In full send, skip the question when step 5 ended in APPROVE and `test-budget` passes: run `python3 $T publish approve <task dir> --by sol`, then `python3 $T publish check <task dir>`. When it passes, go on to step 8 and post now. When step 5 didn't end in APPROVE, `test-budget` fails, or `check` refuses Sol's approval (a framework PR over 100 changed lines, or one marked security), ask me as full stop does, and after I approve, run `publish approve` again without `--by sol`.
8. **Publish** after approval. Read `../swarms-publish/SKILL.md` and follow it, starting with `publish approve`. In full send, step 7 already ran `approve` and `check`.
9. **Babysit** with `babysit-pr` and `watch_pull_request`. Act only on events newer than the last push. Run `swarms.py ci <pr>`. A CI failure belongs to this PR only if it lists it. Fix real findings with proof before each push. Decline scope growth in a comment written with `leaving-pr-comments`. When the PR conflicts with master, rebase and push with `--force-with-lease`.
10. **Stop** with `unwatch_pull_request` and one verdict: ready, waiting (on Kye's review, or on the framework PR for a docs PR), or blocked (what blocks it, what you tried, what's needed).

## Tests

The swarms `CLAUDE.md` section "Tests: only where they earn their place" says how to write one, and AGENTS.md sets the size. To stay inside it:

- Add the new assertions to an existing test that already builds the object, when one fits. Write a new test function only when none does.
- Reuse the stubs and fixtures already in the test file. A new fake model is where most extra lines come from.
- `test-budget` must print PASS. On FAIL, shorten the test by reusing setup and dropping cases that repeat each other, with one statement per line, and keep the assertion that goes red on master. If it still fails, say why in the approval question.
- Undo each part of the fix in turn and check that a test fails each time. A case you dropped that nothing else catches goes back in.
- A longer repro written for your own confidence stays in the verify-swarms run folder and doesn't ship.
- A sol-loop finding that asks for more cases is like any other finding: it counts only when the case fails on the branch.

## When to ask me

Only when:

- the brief is wrong or stale in a way that changes the PR;
- you can't prove the change;
- the change would pass 100 lines and the brief didn't plan for that;
- someone else's PR now does the same thing.

Decide everything else and list the decisions in the report.

When an item is dropped, write the reason and the evidence to `tasks/<slug>/DROPPED.md`, so `swarms-picks` doesn't list it again. When the finding behind its issue was wrong, the question that tells me about the drop also offers closing the issue with the reason. Close it only after I say so.

## Report

The PR link, the verdict, whose approval posted it (mine or Sol's), the proof in one line, the sol-loop rounds and what they changed, and anything unproven. End with the Discord lines from the publish output.
