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

1. Fetch and format today's PRs. "Today" runs from local midnight to local midnight, not UTC. This includes PRs that were already merged or closed.

   ```bash
   day=$(date +%F)  # or the user's date: `date -v-1d +%F` for yesterday, or YYYY-MM-DD as given
   # each end gets its own UTC offset, so days when DST starts or ends are covered too
   iso() { date -j -f '%Y-%m-%d %H:%M:%S' "$day $1" +%Y-%m-%dT%H:%M:%S%z | sed 's/\(..\)$/:\1/'; }
   range="$(iso 00:00:00)..$(iso 23:59:59)"
   for r in "kyegomez/swarms|**Swarms**" "The-Swarm-Corporation/swarms-framework-docs|**Swarms docs**"; do
     out=$(gh search prs --author=@me --repo "${r%%|*}" --created="$range" --limit 100 --json title,url,createdAt \
       --jq 'sort_by(.createdAt) | .[] | "- " + (.title | gsub("(?<c>[_*~`|])"; "\\" + .c)) + " - <" + .url + ">"')
     [ -n "$out" ] && printf '%s\n%s\n\n' "${r#*|}" "$out"
   done > /tmp/swarms-prs.txt
   wc -m < /tmp/swarms-prs.txt
   ```

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
