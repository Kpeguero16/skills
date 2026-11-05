#!/usr/bin/env python3
"""Check every skill in skills/. Exit 1 on any error. Run from anywhere: python3 scripts/check_skills.py

- Frontmatter: `name` matches the folder, and `description` is there and under 1,024 characters.
- Invocation: `disable-model-invocation: true` and agents/openai.yaml's `allow_implicit_invocation: false` agree.
- Links: every `../<skill>/...` path a skill names exists in this repo.
- Writing, for skills written here: no em dashes, en dashes, curly quotes or unslop rule 7 words.
  A skill folder with its own LICENSE is someone else's (unslop, Theo's tstack copies) and keeps its upstream text.
- The README's skill table lists every skill.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
spec = importlib.util.spec_from_file_location("swarms_cli", SKILLS / "swarms-tools/scripts/swarms.py")
swarms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(swarms)


def frontmatter(text: str) -> dict[str, str]:
    """The small YAML subset skills use: key: value, quoted values, and >- or | blocks."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    key = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m and not line.startswith((" ", "\t")):
            key, value = m.group(1), m.group(2).strip()
            if value in (">", ">-", "|", "|-"):
                value = ""
            elif len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1].replace('\\"', '"')
            out[key] = value
        elif key and line.strip():
            out[key] = (out[key] + " " + line.strip()).strip()
    return out


def implicit_policy(skill: Path) -> bool | None:
    path = skill / "agents" / "openai.yaml"
    if not path.exists():
        return None
    m = re.search(r"allow_implicit_invocation:\s*(true|false)", path.read_text(encoding="utf-8"))
    return None if not m else m.group(1) == "true"


def main() -> int:
    errors: list[str] = []
    sizes = []
    names = sorted(p.name for p in SKILLS.iterdir() if (p / "SKILL.md").exists())
    vocabulary = swarms.unslop_vocabulary()
    if not vocabulary:
        errors.append("skills/unslop/SKILL.md rule 7 not found; the writing check has no word list")
    for name in names:
        skill = SKILLS / name
        text = (skill / "SKILL.md").read_text(encoding="utf-8")
        sizes.append((len(text.encode("utf-8")), name))
        meta = frontmatter(text)
        where = f"skills/{name}/SKILL.md"
        if meta.get("name") != name:
            errors.append(f"{where}: frontmatter name is {meta.get('name')!r}, expected {name!r}")
        description = meta.get("description", "")
        if not description:
            errors.append(f"{where}: no description, so the skill never registers")
        elif len(description) > 1024:
            errors.append(f"{where}: description is {len(description)} characters; the limit is 1,024")
        disabled = meta.get("disable-model-invocation", "false").lower() == "true"
        implicit = implicit_policy(skill)
        if disabled and implicit is not False:
            errors.append(f"{where}: disable-model-invocation is true, but agents/openai.yaml doesn't set allow_implicit_invocation: false, so Codex can still start it")
        if implicit is False and not disabled:
            errors.append(f"{where}: agents/openai.yaml blocks implicit invocation, but Claude can still start it; set disable-model-invocation: true")
        for path in sorted(skill.rglob("*.md")):
            body = path.read_text(encoding="utf-8")
            rel = path.relative_to(ROOT).as_posix()
            for target in sorted(set(re.findall(r"\.\./([a-z0-9-]+)/", body))):
                if not (SKILLS / target).is_dir():
                    errors.append(f"{rel}: names ../{target}/, which isn't a skill in this repo")
            if (skill / "LICENSE").exists():
                continue
            for line, msg in swarms.lint_text(body, vocabulary=vocabulary):
                errors.append(f"{rel}:{line}: {msg}")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for name in names:
        if f"`{name}`" not in readme:
            errors.append(f"README.md: the skill table doesn't list `{name}`")
    for doc in ("README.md", "AGENTS.md"):
        for line, msg in swarms.lint_text((ROOT / doc).read_text(encoding="utf-8"), vocabulary=vocabulary):
            errors.append(f"{doc}:{line}: {msg}")

    for size, name in sorted(sizes, reverse=True):
        print(f"{size:6d} bytes  {name}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"{len(names)} skills, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
