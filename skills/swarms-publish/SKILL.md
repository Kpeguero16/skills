---
name: swarms-publish
description: Post swarms PRs whose exact title and body Khalil approved, from a task folder, now or at a scheduled time, after read-only checks. Start it only by name, after approval.
disable-model-invocation: true
---

# Swarms publish

Posts one PR, or a framework PR with its docs PR, whose exact text I approved. Every check before `gh pr create` is read-only, so a failed check posts nothing.

`$T` is `../swarms-tools/scripts/swarms.py`, next to this skill's folder.

## The task folder

`<swarms clone>/tasks/<slug>/`, where `<slug>` is the branch name without its prefix.

| File | What it holds |
| --- | --- |
| `publish.json` | The PRs to open, in order: repo, `owner:branch` head, the pushed SHA, the file names, competition terms |
| `pr_title.txt`, `pr_body.md` | The approved text |
| `pr_body_relabel.md` | The same body with one real wording change, used once if the `ai-generated` label doesn't appear |
| `docs_title.txt`, `docs_body.md` | The docs PR's text, when there is one |
| `approved.sha256` | Written by `publish approve` when I approve |

Start it with:

```bash
python3 $T publish init <task dir> --branch <branch> [--docs-branch <branch>] \
  --item "<shortlist title>" --brief <brief path> --source "<source>" --est <lines>
```

`init` records each fork branch's current SHA. Then fill in `competition` for each PR:

- `terms`: the issue number and the symbol names.
- `removed`: for a deletion, a regex for lines the PR removes. Someone else's PR that removes the same lines blocks the post.
- `allow`: PR numbers you've judged that don't compete.

Without `removed`, a PR mentioning the terms blocks the post only if it was opened after the approval, since nobody has judged it yet.

Optional fields per PR: `"drift": "warn"` when the PR's files change often on master and it merges cleanly around them (the default, `fail`, asks for a rebase); `"commits": 1` to require an exact commit count; `"base_counts": [{"path": ..., "needle": ..., "count": ...}]` to check that master still has what the PR changes. At the top level, `"security": true` marks a security PR.

A title or body can name another PR in the folder: `{{framework.url}}`, `{{framework.number}}`, `{{docs.url}}`. A reference to an earlier PR is filled in when the PR is posted. A body that names a later PR gets the link in an edit right after.

## Steps

1. Only after I approve the exact text in this thread: `python3 $T publish approve <task dir>`. It records the hashes of the text and `publish.json`, so any later edit to either fails the checks.
2. `python3 $T publish check <task dir>`. If fixing a failure changes the text, show me the new text and approve again.
3. Post now, or schedule it (below). Now: run `python3 $T publish post <task dir>` once, with a 10-minute timeout. It reruns the checks, opens the PRs, waits for the `ai-generated` label and makes the relabel edit once if needed, records the ledger row, and prints the Discord lines.
4. After `RESULT posted` or `RESULT PARTIAL`, call `link_pull_request` for each URL on an `OPENED` line, as your next call.
5. Report the `FAIL`, `WARN` and `LABEL` lines, then end with the lines after `DISCORD`, exactly as printed.

`RESULT checks failed` means nothing was posted: quote the `FAIL` lines and stop. Don't rebase, edit the approved text, retry the post or post another way. `RESULT PARTIAL` (exit 3) means some PRs exist and their ledger row is written. Say which, and don't run it again, since the checks refuse a PR that exists. When a body still says "(linked in a moment)", the line gives the `gh pr edit` command and the saved body with the links filled. Show me that command and run it only after I say so. A gh error saying `can't assign requested address` means the Mac ran out of local ports. Wait a minute and run the same command once more, since everything before the post is read-only.

## Scheduling

Ask me whether the Mac will be awake at that time. Then create a `fixed_time` task in the swarms project with `bindToCurrentThread: true`, and edit its prompt to include the task ID it returns:

```
Read <absolute path to this SKILL.md> and follow it to post <task dir>, using --on <YYYY-MM-DD> with check and post. This is scheduled task <id>. Last step, even after a failure: pause this task with schedule_task, scheduledTaskId <id>, enabled false. If that call errors, retry it once and report the result.
```

`--on` fails the checks on any other date. T3 has no run-once schedule: `fixed_time` repeats weekly, and a run missed by more than 10 minutes moves to the next week.
