# skills
Collection of skills to build fast MVP in a hackathon environment. The goal is to go from idea to MVP within 24-36 of development.

## Install

```bash
npx skills add Kpeguero16/skills -g
```

The [skills CLI](https://github.com/vercel-labs/skills) asks which agents to install to, such as Claude Code, Codex or Cursor. Drop `-g` to install into the current project only.

Install `unslop` along with any skill that uses it. `swarms-standup` reads the rules in `unslop` from the folder next to its own. If you pick skills with `--skill`, add `--skill unslop`.

No skill starts on its own. Start one with `/name` in Claude Code, or `$name` in Codex and T3 Code.

## Skills

| Skill | What it does | Requirements |
| --- | --- | --- |
| `swarms-prs` | Builds the end-of-day Discord message that lists the PRs you opened today in swarms and swarms docs. | macOS, `gh` |
| `swarms-standup` | Writes standup notes for each PR you opened today in swarms and swarms docs. A fresh agent explains each PR and runs the code to back it up. | Anthropic models only, because it runs its subagents through Claude Code. macOS, `gh`, local clones of both repos. |
| `unslop` | Removes AI tells from writing. | None |

## Credits

`unslop` comes from [Lauren Tan's pstack](https://github.com/cursor/plugins/tree/main/pstack/skills/unslop) under the MIT license. Her license is in [`skills/unslop/LICENSE`](skills/unslop/LICENSE).
