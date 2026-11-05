---
name: swarms-tools
description: Reference for swarms.py, the command-line helper the swarms skills share for PR facts, worktrees, offline proof runs, code scans, the outcomes ledger and publishing. Use when a swarms skill points here, or when you need one of those facts about kyegomez/swarms or swarms-framework-docs and would otherwise write the gh queries or scanners by hand.
---

# Swarms tools

`scripts/swarms.py` in this folder does the parts of the swarms work that need no judgment. Call it instead of writing gh loops, scanners or date math by hand. It needs Python 3.10 or newer and `gh`, has no other dependencies, and runs on macOS and Windows.

Run it as `python3 <this folder>/scripts/swarms.py <command>`, or `py -3 ...` on Windows. In Claude Code this folder is `${CLAUDE_SKILL_DIR}`. Other swarms skills reach it at `../swarms-tools/scripts/swarms.py`, next to their own folder.

## Commands

| Command | What it does |
| --- | --- |
| `doctor` | Read-only checks: gh login and rate limits, both clones and their remotes, the venv, the tasks folder. Run it first when anything looks off. |
| `today [--date D]` | The local-midnight range for `gh search --created`. Each end gets its own UTC offset, so DST days work. |
| `discord [--date D] [--out F]` | The Discord list of PRs opened that day, escaped, with the character count on stderr. |
| `prs-today --out DIR [--date D]` | Facts JSON for each PR opened that day, one file per PR. |
| `checkout --run DIR [3166 docs#400 master SHA]` | Detached worktrees under DIR at each PR head and its merge base, with one fetch per clone. With no targets it uses every facts JSON in DIR. |
| `cleanup --run DIR` | Removes every worktree under DIR, then DIR. It touches no other worktree. |
| `run --tree T [--log F] -- CMD` | Runs CMD in T with the pinned offline environment, after checking that `swarms` imports from T. `python`, `pytest`, `black` and `ruff` run from the swarms venv. |
| `prove --base B --head H [--copy F...] [--evidence DIR] -- CMD` | Runs CMD in both trees. It prints `PROOF` and exits 0 only when CMD fails on base and passes on head. |
| `status [--out F]` | Facts, signals and a verdict hint (wait, nudge, rebase, rework, close) for every open PR, plus PRs merged in the last 24 hours. |
| `snapshot --dest DIR` | Fresh shallow clones of both repos' default branches. |
| `scan NAME... --tree T [--docs D]` | Where each identifier appears: swarms, tests, examples, docs. |
| `unused PATH... --tree T [--docs D]` | Functions, classes, methods, constants and `self.` attributes that nothing reads. |
| `competition TERM... [--removed REGEX] [--allow N...]` | PRs that mention the terms, and whether each removes the same lines. |
| `ledger sync`, `ledger add`, `ledger stats` | The outcomes ledger at `tasks/daily-opportunities/outcomes.tsv`. |
| `publish init`, `approve`, `check`, `post` | The publish flow. See the `swarms-publish` skill. |
| `lint FILE... [--discord]` | Em dashes, curly quotes and unslop's rule 7 words. `--discord` adds the 2,000-character limit. |
| `transcripts [--days 7] [--match swarms]` | Claude and Codex sessions from the last N days, the ones with the most errors first. |

## Output

Exit 0 is success and 1 is a failed check or missing proof. Exit 2 is a gh error that survived three tries, with backoff, on network errors such as a reset connection; read it before retrying. Lines that start with `FAIL`, `WARN`, `PASS`, `INFO`, `RESULT` or `PROOF` are meant to be quoted as they are.

## Paths

The defaults are the Mac layout. Set these to override them, for example on the PC:

| Variable | Default |
| --- | --- |
| `SWARMS_REPO` | `~/Documents/Programming/swarms` |
| `SWARMS_DOCS_REPO` | `~/Documents/Programming/swarms-framework-docs` |
| `SWARMS_TASKS` | `$SWARMS_REPO/tasks` |

## Limits

- `unused` and `scan` count names in text. getattr, string dispatch and framework hooks are invisible to them, so a hit is a lead to read, not proof.
- `status` hints are mechanical. The `swarms-status` skill reads the evidence and decides the verdict.
- In the main clones, only `checkout` and `cleanup` run git, and only `fetch` and `worktree`. Nothing here checks out, stashes or switches a branch there.

## Changing it

Add a command when agents do the same deterministic work in two sessions. Keep it standard library only. The tests are in the skills repo: `python3 -m unittest discover -s tests`.
