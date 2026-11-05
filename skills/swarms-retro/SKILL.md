---
name: swarms-retro
description: Weekly retro on the swarms workflow. Reads the outcomes ledger, the week's reports and the week's Claude and Codex transcripts, then proposes up to three changes to skills, scripts or AGENTS.md for Khalil to approve. Use when the user says "swarms retro", or from the weekly scheduled task.
---

# Swarms retro

Once a week, find what cost the most and propose up to three changes to the setup. Propose, don't edit: a change to a skill changes every later run, so I approve each one.

`$T` is `../swarms-tools/scripts/swarms.py`, next to this skill's folder. `<tasks>` is the swarms clone's `tasks/` folder.

## 1. Read

- `python3 $T ledger sync`, then `python3 $T ledger stats --days 7` and `--days 30`. Which types, sizes and sources merged this week, which stalled, and what Kye said when he declined or asked for changes.
- Ledger rows listed this week with no PR. Find out why from the brief and the thread.
- `python3 $T transcripts --days 7 --add <file>`, where `<file>` holds the other machine's week. Get it by running `swarms.py transcripts --days 7 --json -` from that machine's copy of `swarms-tools`: in T3, `t3_environment_links` lists linked machines, and `delegate_task` with that machine's `environmentId` can run it and reply with the JSON, which you save here. If you can't reach the other machine, say in the report that its sessions are missing. Read the worst five sessions where it matters: the errors, commands repeated by hand, and places where I corrected the agent. Note any mistake made in two sessions.
- This week's `<tasks>/pr-status/` and `<tasks>/daily-opportunities/` reports: run times, Gaps sections and failures.
- The current skills and AGENTS.md.

## 2. Look for

In this order:

1. **A mistake made twice.** The fix is a check: a `swarms.py` command or flag, a lint rule, a test, or a `publish` check.
2. **Ranking misses.** Items ranked high that stalled or were declined, or kinds of work that merged that the picks skip. The fix is a ranking rule in `swarms-picks`.
3. **Expensive work.** Long sessions, and gh or scanning work done by hand that a command could do.
4. **Rules that change nothing.** A line in a skill or AGENTS.md that no session needed, or that a script now enforces. The fix is deleting it.
5. **Missing information.** Something an agent needed and couldn't reach.

## 3. Rules for a proposal

- It traces to something observed: a ledger row such as `kyegomez/swarms#3166`, or a transcript path and what happened there. One odd session is an anecdote, not a rule.
- A check beats a rule. Write a rule only for a judgment call no script can make.
- It says how it will be tested before it ships: replay a saved day's inputs through the changed skill and compare the output, or run the new check against the session that failed.
- Deleting text beats adding it.

## 4. Write

Write `<tasks>/retro/<date>.md` and give it as your final message:

```
# Swarms retro, <date>
<PRs merged this week, merge rate and median hours, against the last 30 days>

## Proposals
### 1. <the change in a few words>
- Evidence: <ledger rows or transcript paths, and what happened>
- Change: <the file and the edit; a diff when it's short>
- Kind: check, ranking, deletion or rule
- Test: <how it will be shown to work before it ships>

## Seen, no change yet
<Things seen once, or that need more weeks of data.>
```

Then ask me with the question tool which proposals to make. For each one I approve, work in a new worktree of the skills repo (`Kpeguero16/skills`), make the change, run `python3 scripts/check_skills.py` and `python3 -m unittest discover -s tests`, run the test the proposal named, and open a PR with `file-pr`.
