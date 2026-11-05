---
name: swarms-prs
description: Build the end-of-day Discord message listing every PR I opened today in swarms and swarms docs. Use when the user says "swarms prs" or asks for today's PR list for Discord.
---

# Swarms PRs

Build a Discord message with every PR I opened today in the swarms repo and the swarms docs repo, ready to paste.

`$T` is `../swarms-tools/scripts/swarms.py`, next to this skill's folder. Use `py -3` for `python3` on Windows.

## Process

1. `python3 $T discord --out <temp file>`. Add `--date yesterday` or `--date YYYY-MM-DD` for another day. It covers local midnight to local midnight, includes PRs already merged or closed, sorts each repo's PRs by creation time, escapes Discord's formatting characters, and prints the character count and the PR count per repo on stderr. A `FAIL gh` line means the list is incomplete: rerun before going on.
2. Discord rejects messages of 2,000 characters or more. If the count is under 2,000, go to step 4.
3. Over the limit:
   1. Shorten the longest titles first. Keep the `[TYPE][Scope]` prefix and cut the description to a few words. Never cut the link.
   2. If it's still over with every description shortened, split it into messages at line breaks, each under 2,000 characters. Repeat the repo heading at the top of a message that continues a section.

   Recount after each change with `python3 $T lint --discord <file>`. Don't estimate by eye.
4. Output the message in a fenced code block so it copies verbatim, with no trailing blank lines. Below it, give the character count and the PR count per repo. If there were no PRs that day, say so and skip the message.

## Format

```
**Swarms**
- [FIX][Agent.\_run][End each loop's request with a user turn] - <https://github.com/kyegomez/swarms/pull/3166>

**Swarms docs**
- [DOCS][GraphWorkflow][Document the on\_error policy] - <https://github.com/The-Swarm-Corporation/swarms-framework-docs/pull/388>
```

- `- ` at the start of a line renders as a bullet in Discord.
- Links stay wrapped in `<>`, which stops Discord from posting a preview for every PR.
- Underscores, asterisks, tildes, backticks and pipes in titles are backslash-escaped. Without that, names like `__init__` become underlines and `a_b_c` becomes italics.
- A repo with no PRs gets no heading.
