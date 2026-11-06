---
name: swarms-standup
description: "Build my standup notes: every PR I opened today in swarms and swarms docs, each explained and defended by a fresh agent with proof. Use when the user says \"standup notes\" or \"swarms standup\"."
---

# Swarms standup

For every PR I opened today in the swarms and swarms docs repos, give its status, the problem, and the fix with a defense of the approach backed by running the code. The notes are for me to read in the chat during standup. One fresh agent per PR writes the prose, so the defense comes from a reader who didn't write the PR.

`$T` is `../swarms-tools/scripts/swarms.py`, next to this skill's folder. `../verify-swarms/SKILL.md` and `../unslop/SKILL.md` sit next to it too. Give agents absolute paths.

## Process

1. **Collect.** Make an empty run folder and take its real path, since git lists macOS temp folders under `/private`: `run=$(python3 -c "import os, tempfile; print(os.path.realpath(tempfile.mkdtemp()))")`. It works on Windows too, with `python` and your shell's syntax. Then `python3 $T prs-today --out "$run"`, adding `--date yesterday` or `--date YYYY-MM-DD` for another day. It saves one facts JSON per PR, merged and closed PRs included. With no PRs, say so, remove `$run` and stop.
2. **Check out.** `python3 $T checkout --run "$run"` fetches once per clone, so parallel agents never fight over fetch locks. It makes a detached worktree at each PR head (`$run/wt-<repo>-<n>`) and at its merge base (`$run/base-<repo>-<n>`), where `<repo>` is `swarms` or `swarms-framework-docs`.
3. **Dispatch.** Launch one fresh `general-purpose` agent per PR with the brief below, all in one message so they run in parallel, and wait for every one. Merged and closed PRs get an agent too. A dozen PRs take about 10 minutes.
4. **Assemble.** Sort each repo's PRs by `createdAt` and fill the format below. From the facts JSON, take the status of a merged or closed PR, dated in local time. Take the reason for a close from the agent. Everything else comes from the agent's reply. Agents run long, so cut every answer to its main point: Status and Problem at most 1 line, Fix at most 3. Print the result as normal chat text, not in a code block, so the chat renders it. Apply `unslop` to every line you cut or write.
5. **Clean up**, also after a failure: `python3 $T cleanup --run "$run"`. Check that it printed no `still listed` line. Don't run `git status` in the main clones: it can take their index lock while another session works there.

## Format

Group by repo under `## Swarms` and `## Swarms docs`, PRs in creation order, and drop a heading with no PRs. Each PR gets a `###` heading: the PR number linked to its URL, then the description from the WARP title without the `[TYPE][Symbol]` brackets. Put a blank line between the label lines, because chat markdown joins adjacent lines into one paragraph.

```markdown
## Swarms

### [#3166](https://github.com/kyegomez/swarms/pull/3166) End each loop's request with a user turn so Gemini 3.5+ accepts it

**Status:** Open, ready to merge (mergeable, no review requested, CI failures match master's)

**Problem:** Gemini 3.5+ rejects a request whose last turn is the assistant's, so multi-loop agents stop after loop 1.

**Fix:** Agent._run appends a short user turn before each follow-up call, at the one call site that builds the request, instead of in every provider wrapper. The new test fails on master and passes here.

**Heads-up:** PR #3171 touches the same call site. Whichever merges second needs a rebase.
```

Add the **Heads-up** line only when the PR has one: the agent's `Notes`, or anything left unproven and why. A PR with nothing to flag gets no Heads-up line.

Flag a security PR (vulnerability, injection, auth, secret handling, sandbox or permission bypass, unsafe deserialization; if unsure, treat it as security) by putting `SECURITY` before the description in its heading, like `### [#3201](<url>) SECURITY Redact API keys in logs`.

## Brief

Send each agent this, with the placeholders filled:

````markdown
You are preparing one PR for my standup: <url>
Facts from GitHub: <run>/<repo>-<n>.json. Detached worktrees: the PR head at <run>/wt-<repo>-<n>, its merge base at <run>/base-<repo>-<n>. Put scripts and logs in <run>/scratch-<repo>-<n>/.

Read <verify-swarms SKILL.md path> and follow it to run any code. Its CLI is <swarms.py path>. The worktrees exist already, and I clean up, so skip its Launch and Cleanup steps.

Find out, from the PR body, its linked issue, `gh pr diff`, the review comments (`gh pr view --comments` and `gh api repos/<repo>/pulls/<n>/comments`) and the code:
- the problem it solves, as a user of the library would see it;
- how the change solves it;
- why this approach is the right one: what it was chosen over, and the evidence that it works.

Run the code for proof wherever it can run; reading the diff alone isn't enough. Show the test or repro red on the base and green on the PR with `prove`, using `--copy` for the PR's test files. A docs PR usually tracks a swarms PR, and it isn't ready until that PR merges.

Status, for an open PR: ready to merge means not a draft, `mergeable` is MERGEABLE, `mergeStateStatus` isn't BLOCKED or DIRTY, `reviewDecision` isn't CHANGES_REQUESTED or REVIEW_REQUIRED, no check is still pending, no maintainer comment left unanswered, no unmerged PR it must follow, and CI adds no failures (compare with master as verify-swarms describes). Anything you can't confirm counts as not ready. A merged PR gets its merge date. A closed one gets who closed it and why.

Network: read GitHub through `gh` and git fetch, and install packages from PyPI or npm when a step needs them. Make no other calls: no model providers, no swarms services, nothing the code under test would reach on its own. Toward GitHub you only read: no comments, edits, pushes, reruns or approvals. Work only inside <run>.

Reply with exactly these lines, in plain words. Read <unslop SKILL.md path> first and follow its rules. Status and Problem are at most 30 words each, and Fix at most 50. Put everything else in Notes:

Status: <Open, ready to merge (reason) | Open, not ready: reason | Merged YYYY-MM-DD | Closed unmerged: reason>
Problem: ...
Fix: <what changed, why this way over the alternative, and the proof you ran>
Proof: <commands run and their result, or "not run: reason">
Security: <yes or no>
Notes: <things I should act on: a competing PR, a bug or doc error you found, a reviewer to answer; or "none">

If the evidence goes against the PR (the test passes on master too, a better approach exists, a reviewer's objection stands), say so in "Fix". I'd rather hear it before standup than during it.
````

The `Proof`, `Security` and `Notes` lines are for you, not the notes: use them for each PR's Heads-up line and the security flag.
