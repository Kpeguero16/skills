---
name: swarms-standup
description: "Build my standup notes: every PR I opened today in swarms and swarms docs, each explained and defended by a fresh agent with proof."
disable-model-invocation: true
---

# Swarms standup

For every PR I opened today in the swarms and swarms docs repos, give its status, the problem, the fix, a defense of the approach backed by running the code, and its size. One fresh agent per PR writes the prose, so the defense comes from a reader who didn't write the PR.

## Repos

| Repo | Local clone (remote `upstream`) | Default branch |
| --- | --- | --- |
| `kyegomez/swarms` | `~/Documents/Programming/swarms` | `master` |
| `The-Swarm-Corporation/swarms-framework-docs` | `~/Documents/Programming/swarms-framework-docs` | `main` |

## Process

1. **Collect.** "Today" starts at local midnight, and merged or closed PRs count. Save each PR's facts:

   ```bash
   run=$(cd "$(mktemp -d /tmp/swarms-standup.XXXXXX)" && pwd -P)  # real path: git lists worktrees under /private/tmp
   day=$(date +%F)  # or the user's date: `date -v-1d +%F` for yesterday, or YYYY-MM-DD as given
   # each end gets its own UTC offset, so days when DST starts or ends are covered too
   iso() { date -j -f '%Y-%m-%d %H:%M:%S' "$day $1" +%Y-%m-%dT%H:%M:%S%z | sed 's/\(..\)$/:\1/'; }
   range="$(iso 00:00:00)..$(iso 23:59:59)"
   for repo in kyegomez/swarms The-Swarm-Corporation/swarms-framework-docs; do
     for n in $(gh search prs --author=@me --repo "$repo" --created="$range" --limit 100 --json number --jq '.[].number' || echo "SEARCH FAILED: $repo" >&2); do
       gh pr view "$n" --repo "$repo" --json number,title,url,state,createdAt,mergedAt,closedAt,isDraft,mergeable,mergeStateStatus,reviewDecision,additions,deletions,changedFiles,headRefOid,baseRefName,labels,statusCheckRollup \
         > "$run/${repo#*/}-$n.json"
     done
   done
   ls "$run"
   ```

   A `SEARCH FAILED` line means the list is incomplete: rerun before going on. No PRs: say so, `rm -rf "$run"` and stop.

2. **Check out.** In each local clone, fetch every base branch (`baseRefName`) and every PR head in one `git fetch upstream <base-branches> pull/<n>/head ...` call, so parallel agents never fight over fetch locks. Then give each PR a detached worktree at `$run/wt-<repo>-<n>` on its `headRefOid`, where `<repo>` is the short name (`swarms`, `swarms-framework-docs`). Never check out in the main clones; other sessions are using them.

3. **Dispatch.** Launch one fresh `general-purpose` agent per PR with the brief below, all in a single message so they run in parallel, and wait for every one. Merged and closed PRs get an agent too. A dozen PRs take about 10 minutes.

4. **Assemble.** Sort each repo's PRs by `createdAt` and fill the format below. From the facts JSON: the size line, and the status of a merged or closed PR, dated in local time (`jq -r '.mergedAt | fromdate | localtime | strftime("%Y-%m-%d")'`), with the reason for a close taken from the agent. Everything else comes from the agent's reply. Agents run long, so cut every answer to its main point, at most 2 lines (3 when the defense needs its proof). Output the result in a fenced code block so it copies verbatim. Below it, list **Heads-up** items: each agent's `Notes`, plus anything left unproven and why.

5. **Clean up**, also when an earlier step failed. In both clones, `git worktree remove --force` every worktree whose path starts with `$run` (the agents' base worktrees too), then `rm -rf "$run"`. Confirm `git worktree list` shows none under `$run` and `git status` in each clone is unchanged. Leave other worktrees alone, stale ones included; other sessions own them.

## Format

Group by repo in creation order, and drop a heading with no PRs.

```
**Swarms**
- [FIX][Agent._run][End each loop's request with a user turn so Gemini 3.5+ accepts it] - <https://github.com/kyegomez/swarms/pull/3166>
  - Status: Open, ready to merge (mergeable, no review requested; CI failures match master's)
  - Problem: Gemini 3.5+ rejects a request whose last turn is the assistant's, so multi-loop agents stop after loop 1.
  - Solution: Agent._run appends a short user turn before each follow-up call.
  - Why this way: One append at the single call site that builds the request, instead of rewriting history in every provider wrapper. The new test fails on master and passes here.
  - Size: +28 / -5 (net +23), 2 files
```

Flag a security PR (vulnerability, injection, auth, secret handling, sandbox or permission bypass, unsafe deserialization; if unsure, treat it as security) by appending ` (security: keep out of public channels)` to its title line.

## Brief

Send each agent this, with the placeholders filled:

````markdown
You are preparing one PR for my standup: <url>
Facts from GitHub: <run>/<repo>-<n>.json. Detached worktree at the PR head: <worktree>.

Find out, from the PR body, its linked issue, `gh pr diff`, the review comments (`gh pr view --comments` and `gh api repos/<repo>/pulls/<n>/comments`) and the code:
- the problem it solves, as a user of the library would see it;
- how the change solves it;
- why this approach is the right one: what it was chosen over, and the evidence that it works.

Run the code for proof wherever it can be run; reading the diff alone isn't enough. Show the test or repro goes red on the base and green on the PR. For the base, add a second detached worktree at <run>/base-<repo>-<n> on `git merge-base HEAD upstream/<baseRefName>` (`baseRefName` is in the facts JSON), with the PR's test files copied in. Put scripts and logs in <run>/scratch-<repo>-<n>/.

Running swarms applies to every PR. Add the Docs section only for a docs PR.

Running swarms:
- Use `~/Documents/Programming/swarms/.venv/bin/python`. Prefix every run with `SWARMS_TELEMETRY_ON=false LITELLM_LOCAL_MODEL_COST_MAP=True PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 OPENAI_API_KEY= ANTHROPIC_API_KEY= GEMINI_API_KEY= PYTHONPATH=<tree>`. Telemetry is on when the variable is unset, and without `PYTHONPATH` swarms imports the main checkout, not the tree under test. Print `swarms.__file__` and confirm it's under <tree>.
- Proof is offline: tests, mocks, recorded responses. When only a live model call could prove something, say what's unproven.
- That `.venv` has master's dependencies. If the PR changes `pyproject.toml` or requirements, install into a throwaway venv under <run>, or say the run used the old versions.
- `.venv` is Python 3.14; CI runs 3.10-3.12. Mention it if the PR's behavior could depend on the version.

Docs (`swarms-framework-docs`):
- Run `npx -y mint@4.2.970 validate` and `npx -y mint@4.2.970 broken-links` in the worktree. `validate` sometimes fails with ENOENT on a `src/_props/...` file while other mint runs are going; rerun it before calling it a failure.
- The proof is that the page matches the code. Read the swarms source it documents with `git -C ~/Documents/Programming/swarms show upstream/master:<path>`, or `git archive` it into <run>/scratch-<repo>-<n>/. Run the page's examples offline with the model mocked, using the Python and environment from Running swarms. A docs PR's "red on base" is the old page's claims failing against the new code.
- A docs PR usually tracks a swarms PR, and it isn't ready until that PR merges.
- The "Bounty guard" check has failed on every docs PR and issue since 2026-10-28 without starting a step (the org's Actions billing is locked). If merged PRs fail it too, it doesn't block readiness.

Status, for an open PR: ready to merge means not a draft, `mergeable` is MERGEABLE, `mergeStateStatus` isn't BLOCKED or DIRTY, `reviewDecision` isn't CHANGES_REQUESTED or REVIEW_REQUIRED, no check is still pending, no maintainer comment left unanswered, no unmerged PR it must follow, and CI adds no failures. Anything you can't confirm counts as not ready. Red CI on kyegomez/swarms is normal, since master fails some of the same jobs: compare each failing job with the same job's latest run on master (`gh run list --workflow <name> --branch master`, then `gh api repos/kyegomez/swarms/actions/jobs/<id>/logs`). Diff the sorted FAILED/ERROR test lines; for a job that fails before any test runs (lint, build, install), compare the error itself. A merged PR gets its merge date. A closed one gets who closed it and why.

Network: read GitHub through `gh` and git fetch, and install packages from PyPI or npm when a step needs them. Make no other calls: no model providers, no swarms services, nothing the code under test would reach on its own. Toward GitHub you only read: no comments, edits, pushes, reruns or approvals. Work only inside <run>.

Reply with exactly these lines, in plain words (apply the unslop skill). Status, Problem and Solution are at most 30 words each, and Why this way at most 50. Put everything else in Notes:

Status: <Open, ready to merge (reason) | Open, not ready: reason | Merged YYYY-MM-DD | Closed unmerged: reason>
Problem: ...
Solution: ...
Why this way: <the choice and the proof you ran>
Proof: <commands run and their result, or "not run: reason">
Security: <yes or no>
Notes: <things I should act on: a competing PR, a bug or doc error you found, a reviewer to answer; or "none">

If the evidence goes against the PR (the test passes on master too, a better approach exists, a reviewer's objection stands), say so in "Why this way". I'd rather hear it before standup than during it.
````

The `Proof`, `Security` and `Notes` lines are for you, not the output block: use them for the Heads-up list and the security flag.
