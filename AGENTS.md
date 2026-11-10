# How I work

I'm Khalil (GitHub `Kpeguero16`). Agents write nearly all of my code, in T3 Code with Claude Code and Codex, on a Mac and a Windows PC. I pick the work and approve anything that goes public in my name. Agents do the rest, and they tell me plainly what they proved and what they didn't.

## Rules

- Questions are read-only. When I ask a question, answer it. Don't edit files or post anything until I ask for a change.
- Match the ceremony to the task. A 10-line deletion needs proof and a PR, not a spec. Save plans and grilling for changes over about 100 lines.
- Use subagents for breadth or for adversarial review: to cover more ground at once, or to check work they didn't write.
- Before parallel agents start, say which files each one may edit.
- Ask me through the harness's question tool (`AskUserQuestion` in Claude Code, `request_user_input` in Codex). A question in a normal reply looks like a finished thread, and I miss it.
- Proof is what you saw run in this session. Say what's unproven instead of guessing.
- Fix a repeated mistake in the environment: a script, a check or a test first, a written rule last.
- Never use the git stash. Other sessions share it. Commit to a temporary branch instead.
- Keep facts in files I can read and diff, such as this file, the skills and the tasks folder, not in Claude memory, which Codex can't read.
- Apply the `unslop` skill to anything written for other people.

## Swarms

I contribute to `kyegomez/swarms` every day, and what counts is merged PRs, so small PRs that can merge the same day come first. I open 5 to 10 a day. Kye (`kyegomez`) maintains the repo and is the only one who merges.

| Repo | Mac clone | Default branch |
| --- | --- | --- |
| `kyegomez/swarms` | `~/Documents/Programming/swarms` | `master` |
| `The-Swarm-Corporation/swarms-framework-docs` | `~/Documents/Programming/swarms-framework-docs` | `main` |

In both clones, `upstream` is the main repo and `origin` is my fork. On another machine, set `SWARMS_REPO` and `SWARMS_DOCS_REPO` when the clones live elsewhere.

### The main clones

- Other sessions and scheduled jobs share the main clones. Run no git there except `fetch` and `worktree`: no checkout, branch switch, rebase, stash or reset.
- Work in a T3 worktree or a detached worktree in a temp folder. `swarms-tools` makes and removes them.
- Local `master` is often behind. Start from `git fetch upstream master` and `upstream/master`.
- Push from a T3 worktree with `git push origin HEAD:refs/heads/<branch>`, and don't rename the worktree's branch. T3 has replaced worktrees after a rename.
- `tasks/` in the swarms clone is git-ignored. It holds the daily reports, briefs, PR texts and the outcomes ledger.

### What merges

- Small PRs. Under 100 changed lines usually merge within a few hours, and bigger ones take a day or more. `swarms.py ledger stats` has the current numbers.
- Framework and API work, and deletions.
- Short tests. Kye flagged long ones on 2026-10-29 and 2026-11-09: agents write big tests, and 50 test lines for a 5-line fix only adds code. A PR's non-blank test lines stay within the larger of 20 and its non-blank lines under `swarms/`, which `swarms.py test-budget` checks.
- A deletion needs no new test (the swarms `CLAUDE.md` says so). Run the module's tests before and after.
- "No internal callers" isn't enough to delete public API. Kye kept `Agent.run_batched`, which had docs, a bug-fix history and tests. Lead with what's wrong with the code.
- A change users can see needs a docs PR in `swarms-framework-docs`, opened with the framework PR and never alone.

### PRs

- Titles use WARP: `[TYPE][Symbol][Imperative description]`, such as `[FIX][Agent._run][End each loop's request with a user turn]`.
- The body opens with the problem as a user would see it, then the fix, then the evidence: the check that fails on master and passes on the branch, or for a deletion, the search that shows nothing uses it. Use `Closes #N` for the issue.
- End the body with `🤖 Generated with [Claude Code](https://claude.com/claude-code) (<model>)`, naming the model that did the work, and end commits with a matching `Co-Authored-By` trailer. Never remove the 🤖 line.
- The repo's labeler should add `ai-generated`. When it doesn't, a real wording edit to the body runs it again.
- Nothing goes public until I've approved the exact title and body.
- After a PR is posted, give me its title on one line and the URL on the next, for the Swarm's Python Discord channel. A security PR goes only to "#management or product channel only", never to a public channel.

### Known noise

- Some `kyegomez/swarms` CI jobs fail on master too. A failing job counts against a PR only when the same job passes on master.
- "Bounty guard" in the docs repo has failed on every PR since 2026-10-28 without running a step. It never blocks a PR.
- A gh error saying `can't assign requested address` means the Mac ran out of local ports. Wait a minute and run the command once more.

### Running swarms code

Follow the `verify-swarms` skill. Never import swarms without `SWARMS_TELEMETRY_ON=false`, because telemetry is on when it's unset. Never call a real model. Check that `swarms` imports from the tree under test, since the main clone's venv has an editable install.

### T3 scheduled tasks

- `fixed_time` repeats weekly, and there's no run-once type. A one-off job pauses itself as its last step, even after a failure, with `schedule_task` and `enabled=false`. Put the task's ID in its prompt.
- A run missed by more than 10 minutes moves to the next occurrence without a word. Give one-off jobs a date check.
- Bind a scheduled job to a thread that will still exist when it runs.

### Skills

| Say | Skill | Result |
| --- | --- | --- |
| "morning status" | `swarms-status` | A verdict for each open PR, in `tasks/pr-status/<date>.md` |
| "today's picks" | `swarms-picks` | The shortlist, and a brief per item in `tasks/handoffs/<date>/` |
| "own it, full stop" and a brief | `swarms-own` with `full-stop` | Proof, review and PR text, then my approval, then publish and babysit until ready |
| "verify" | `verify-swarms` | Offline proof, red on the base and green on the branch |
| `/swarms-publish` | `swarms-publish` | Posts approved text, now or at a set time |
| "swarms prs" | `swarms-prs` | The Discord list of today's PRs |
| "standup notes" | `swarms-standup` | Standup notes with proof for each PR |
| "swarms retro" | `swarms-retro` | Up to three proposed changes, from the ledger and transcripts |

They share the `swarms-tools` CLI. Install them together with `unslop` and the tstack skills.
