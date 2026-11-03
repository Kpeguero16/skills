---
name: swarms-prs
description: Build the end-of-day Discord message listing every PR I opened today in swarms and swarms docs.
disable-model-invocation: true
---

# Swarms PRs

Build a Discord message with every PR I opened today in the swarms repo and the swarms docs repo, ready to paste.

## Repos

- Swarms: `kyegomez/swarms`
- Swarms docs: `The-Swarm-Corporation/swarms-framework-docs`

## Process

1. Fetch and format today's PRs. "Today" starts at local midnight, not UTC midnight. This includes PRs that were already merged or closed.

   ```bash
   since="$(date +%Y-%m-%d)T00:00:00$(date +%z | sed 's/\(..\)$/:\1/')"
   for r in "kyegomez/swarms|**Swarms**" "The-Swarm-Corporation/swarms-framework-docs|**Swarms docs**"; do
     out=$(gh search prs --author=@me --repo "${r%%|*}" --created=">=$since" --limit 100 --json title,url,createdAt \
       --jq 'sort_by(.createdAt) | .[] | "- " + (.title | gsub("(?<c>[_*~`|])"; "\\" + .c)) + " - <" + .url + ">"')
     [ -n "$out" ] && printf '%s\n%s\n\n' "${r#*|}" "$out"
   done > /tmp/swarms-prs.txt
   wc -m < /tmp/swarms-prs.txt
   ```

   If the user passes a date (e.g. `yesterday`, `2026-11-02`), replace the `--created` value with a range from that day's local midnight to the next: `--created="2026-11-02T00:00:00-05:00..2026-11-03T00:00:00-05:00"`.

2. Check the length. Discord rejects messages of 2,000 characters or more. If the count is under 2,000, go to step 4.

3. Over the limit:
   1. Shorten the longest titles first. Keep the `[TYPE][Scope]` prefix and cut the description to a few words. Never cut the link.
   2. If it is still over with every description shortened, split into multiple messages at a line break, each under 2,000 characters. Keep a repo heading at the top of each message that continues a section.

   Recount after each change with `wc -m`. Don't estimate by eye.

4. Output the message in a fenced code block so it copies verbatim, with no trailing blank lines. Below it, state the character count and the PR count per repo. If there were no PRs today, say so and skip the message.

## Format

```
**Swarms**
- [FIX][Agent.\_run][End each loop's request with a user turn] - <https://github.com/kyegomez/swarms/pull/3166>

**Swarms docs**
- [DOCS][GraphWorkflow][Document the on\_error policy] - <https://github.com/The-Swarm-Corporation/swarms-framework-docs/pull/388>
```

- `- ` at line start renders as a bullet in Discord.
- Links stay wrapped in `<>`. That stops Discord from posting a preview embed for every PR.
- Underscores, asterisks, tildes, backticks and pipes in titles are backslash-escaped. Without that, names like `__init__` turn into underlines and `a_b_c` into italics.
- Drop a repo's heading when it has no PRs.
