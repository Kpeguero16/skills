# skills

The agent skills I use in my day-to-day work. I run them in T3 Code with Claude Code and Codex. The `swarms-*` skills cover my work on the swarms and swarms docs repos, and `unslop` removes AI tells from what my agents write.

## Install

```bash
npx skills add Kpeguero16/skills -g
```

The [skills CLI](https://github.com/vercel-labs/skills) asks which agents to install to, such as Claude Code, Codex or Cursor. Drop `-g` to install into the current project only.

Install all of them. The skills call each other by folder: every `swarms-*` skill runs `swarms-tools`, several read `unslop` and `verify-swarms`, `swarms-own` reads Theo's tstack skills, and `full-stop` reads `full-send`. If you pick skills with `--skill`, take the ones they name too.

Skills start in two ways. Most start when you say the phrase in their description, such as "own it, full stop", so one sentence can load two skills. `swarms-publish` and `unslop` start only by name: `/name` in Claude Code, or `$name` in Codex and T3 Code.

## One instruction file

`AGENTS.md` holds how I work and the swarms facts every agent needs, for both harnesses on both machines. Link it once per machine from a clone of this repo:

```bash
printf '@%s\n' "$PWD/AGENTS.md" > ~/.claude/CLAUDE.md   # Claude Code imports it
ln -s "$PWD/AGENTS.md" ~/.codex/AGENTS.md                # Codex reads it directly
```

On Windows, write the same `@<path>` line to `%USERPROFILE%\.claude\CLAUDE.md`, and copy `AGENTS.md` to `%USERPROFILE%\.codex\AGENTS.md` (or link it with `New-Item -ItemType SymbolicLink` in Developer Mode).

## Skills

| Skill | What it does | Requirements |
| --- | --- | --- |
| `swarms-status` | Gives each of my open PRs a verdict: wait, nudge, rebase, rework or close. | `gh` |
| `swarms-picks` | Finds the day's PR opportunities, ranks them by what has merged before, and writes a brief for each. | `gh`, the Wispr Flow connector |
| `swarms-own` | Takes one brief from proof to a PR that's ready for the maintainer, stopping once for my approval of the text. | T3 Code, Codex for the review |
| `verify-swarms` | Runs swarms code offline and proves a change red on the base and green on the branch. | Local clones, the swarms venv |
| `swarms-publish` | Posts approved PR text after read-only checks, now or at a scheduled time. | `gh` |
| `swarms-prs` | Builds the end-of-day Discord message that lists the PRs I opened today. | `gh` |
| `swarms-standup` | Writes standup notes for each PR I opened today. A fresh agent explains each PR and runs the code to back it up. | Anthropic models only, because it runs its subagents through Claude Code. `gh`, local clones. |
| `swarms-retro` | Proposes up to three changes a week to these skills, from the outcomes ledger and the week's transcripts. | `gh` |
| `swarms-tools` | The shared CLI: PR facts, worktrees, proof runs, code scans, the outcomes ledger and publishing. | Python 3.10+, `gh` |
| `full-stop` | Takes a change to a PR that's ready to merge, without merging. | `gh` |
| `full-send` | The same, and merges. For repos I can merge in. | `gh` |
| `sol-loop` | Reviews a change with GPT Sol in a loop, up to three rounds. | T3 Code or another way to run Sol |
| `file-pr` | Files a short PR that leads with the problem. | `gh` |
| `babysit-pr` | Watches a PR through CI and review bots, and fixes the real findings. | `gh`, `python3` for `pr-wait` outside T3 |
| `modernize` | Rebases an old PR and decides whether it should still exist. | `gh` |
| `leaving-pr-comments` | Formats comments an agent posts for me. | None |
| `unslop` | Removes AI tells from writing. | None |

All swarms skills run on macOS and Windows. Set `SWARMS_REPO` and `SWARMS_DOCS_REPO` when the clones aren't in `~/Documents/Programming/`.

## Checks

```bash
python3 scripts/check_skills.py            # frontmatter, invocation settings, links, writing rules
python3 -m unittest discover -s tests      # the swarms-tools CLI
```

CI runs both on every push. A skill folder with its own `LICENSE` is someone else's, and the writing check leaves its text as upstream wrote it.

## Credits

`unslop` comes from [Lauren Tan's pstack](https://github.com/cursor/plugins/tree/main/pstack/skills/unslop) under the MIT license. Her license is in [`skills/unslop/LICENSE`](skills/unslop/LICENSE).

`full-send`, `full-stop`, `sol-loop`, `file-pr`, `babysit-pr`, `modernize` and `leaving-pr-comments` come unchanged from [Theo Browne's tstack](https://github.com/t3dotgg/tstack) under the MIT license. His license is in each of those folders. `swarms-own` holds my changes to how they run on swarms, so the copies can be updated from upstream.

`verify-swarms` follows the Launch, Doctor, Drive, Evidence and Cleanup layout from pstack's `create-verification-skill`. `swarms-retro` draws on Matt Pocock's `retro` skill.
