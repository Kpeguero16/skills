---
name: swarms-own
description: Take one swarms brief or PR from start to ready for Kye, stopping once for Khalil's approval of the PR text. Use when the user says "own it", usually as "own it, full stop", with a brief path from tasks/handoffs or a PR number.
---

# Own it

One thread owns one item, a brief in `tasks/handoffs/<date>/` or an existing PR, until it's ready for Kye. It's Theo's `full-stop` with the swarms rules below. Kye merges; this thread never does.

Read `../full-stop/SKILL.md` and `../full-send/SKILL.md`, next to this skill's folder, if they aren't loaded. Where they differ from this file, this file wins. `$T` is `../swarms-tools/scripts/swarms.py`. AGENTS.md has the PR conventions.

## Steps

1. **Restate.** Read the brief. In two or three sentences, give the goal and the smallest change that meets it, before any edit. If master moved, find the code with grep rather than the brief's line numbers. Run `python3 $T competition <issue> <symbol>`, and say so if someone has opened a PR since the brief was written.
2. **Prove the problem on master** with `verify-swarms`, before changing anything: a failing test or repro in a base tree. For a deletion, prove the fact that makes it safe with `python3 $T scan <name> --tree <base tree> --docs <docs tree>`.
3. **Make the smallest change** in this worktree. Show the same check red on the base and green here with `python3 $T prove`. A deletion has nothing to turn red: run the module's tests on both trees and show the pass and fail sets match, as `verify-swarms` describes. Save the evidence in `tasks/<slug>/evidence/`. Run black and ruff on the changed files. Commit with the co-author trailer.
4. **Review with `sol-loop`**: at most three rounds, each finding marked blocker, should or nit, stopping when only nits remain. A finding counts only if rerunning its command, or a repro you write for it, shows the failure. Decline the rest with that evidence. Don't push during the loop.
5. **Write the PR text** in `tasks/<slug>/`: `pr_title.txt`, `pr_body.md`, and `pr_body_relabel.md` (the same body with one real wording change). Use `file-pr`'s problem-first body, add the before-and-after evidence, and say whether the change is a one-way or two-way door. A docs PR also gets `docs_title.txt` and `docs_body.md`. Apply `unslop`, then `python3 $T lint <files>`.
6. **Push** to my fork with `git push origin HEAD:refs/heads/<branch>`, without renaming the worktree's branch. Then run `publish init` and fill in the competition terms, as `swarms-publish` describes.
7. **Ask me** with the harness's question tool. Put the full title and body in the question, with the proof in one line, and offer: approve and post now, approve and post at a time I give, or change something. A question in a normal reply looks like a finished thread and gets missed.
8. **Publish** after approval. Read `../swarms-publish/SKILL.md` and follow it, starting with `publish approve`.
9. **Babysit** with `babysit-pr` and `watch_pull_request`. Act only on events newer than the last push. Run `swarms.py ci <pr>`. A CI failure belongs to this PR only if it lists it. Fix real findings with proof before each push. Decline scope growth in a comment written with `leaving-pr-comments`. When the PR conflicts with master, rebase and push with `--force-with-lease`.
10. **Stop** with `unwatch_pull_request` and one verdict: ready, waiting (on Kye's review, or on the framework PR for a docs PR), or blocked (what blocks it, what you tried, what's needed).

## When to ask me

Only when:

- the brief is wrong or stale in a way that changes the PR;
- you can't prove the change;
- the change would pass 100 lines and the brief didn't plan for that;
- someone else's PR now does the same thing.

Decide everything else and list the decisions in the report.

## Report

The PR link, the verdict, the proof in one line, the sol-loop rounds and what they changed, and anything unproven. End with the Discord lines from the publish output.
