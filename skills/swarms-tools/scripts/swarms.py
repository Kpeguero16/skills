#!/usr/bin/env python3
"""Deterministic helpers for the swarms skills.

Standard library only, Python 3.10 or newer, macOS and Windows. Run it with
`python3 swarms.py <command>` (`py -3 swarms.py <command>` on Windows) and see
`--help` on each command. The skills in this repo call it so that agents stop
rewriting the same gh queries, scanners and checks every morning.
"""
from __future__ import annotations

import argparse
import ast
import collections
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

USER = "Kpeguero16"
MAINTAINER = "kyegomez"
SWARMS = "kyegomez/swarms"
DOCS = "The-Swarm-Corporation/swarms-framework-docs"
REPO_LABEL = {SWARMS: "Swarms", DOCS: "Swarms docs"}
SHORT = {SWARMS: "swarms", DOCS: "swarms-framework-docs"}
DEFAULT_BRANCH = {SWARMS: "master", DOCS: "main"}
# "Bounty guard" has failed on every docs PR since 2026-10-28 without starting a step,
# because the org's Actions billing is locked. It never blocks readiness.
NOISE_CHECKS = {DOCS: {"Bounty guard"}}
AI_LABEL = "ai-generated"
ROBOT_LINE = "🤖 Generated with"
SIZE_BUCKETS = ((30, "under 30"), (100, "30 to 99"), (300, "100 to 299"), (None, "300 and up"))
SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SCRIPT_DIR.parent.parent


# ---------------------------------------------------------------- paths


def _home_path(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or (Path.home() / default)).expanduser()


def swarms_clone() -> Path:
    return _home_path("SWARMS_REPO", "Documents/Programming/swarms")


def docs_clone() -> Path:
    return _home_path("SWARMS_DOCS_REPO", "Documents/Programming/swarms-framework-docs")


def clone_for(repo: str) -> Path:
    return swarms_clone() if repo == SWARMS else docs_clone()


def tasks_dir() -> Path:
    return Path(os.environ.get("SWARMS_TASKS") or swarms_clone() / "tasks").expanduser()


def ledger_path() -> Path:
    return tasks_dir() / "daily-opportunities" / "outcomes.tsv"


def venv_python() -> Path:
    venv = swarms_clone() / ".venv"
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


# ---------------------------------------------------------------- gh


class GhError(RuntimeError):
    pass


# Failures worth one more try. Nov 4's status run died on a connection reset, and a
# Mac out of local ports says "can't assign requested address".
TRANSIENT = re.compile(
    r"can't assign requested address|connection reset|unexpected EOF|i/o timeout|"
    r"TLS handshake timeout|HTTP 50[234]|timed out|temporarily unavailable|"
    r"stream error|GOAWAY|connection refused",
    re.I,
)


def gh(*args, json_out: bool = True, timeout: int = 120, tries: int = 3, input: str | None = None):
    """Run gh with a timeout and retries on network errors. Raises GhError otherwise."""
    cmd = ["gh", *map(str, args)]
    err = ""
    for attempt in range(tries):
        try:
            p = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                input=input, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            err = f"timed out after {timeout}s"
        else:
            if p.returncode == 0:
                if not json_out:
                    return p.stdout
                return json.loads(p.stdout) if p.stdout.strip() else None
            err = (p.stderr or p.stdout).strip()
            if not TRANSIENT.search(err):
                break
        if attempt < tries - 1:
            time.sleep(5 * 3**attempt)
    shown = " ".join(cmd[:5]) + (" ..." if len(cmd) > 5 else "")
    raise GhError(f"{shown}: {err[:500]}")


def gh_pages(path: str) -> list:
    """GET a paginated REST list and flatten the pages."""
    pages = gh("api", "--paginate", "--slurp", path) or []
    out: list = []
    for page in pages:
        out.extend(page if isinstance(page, list) else [page])
    return out


def raw_file(repo: str, path: str, ref: str) -> str | None:
    """A file's text on a ref, or None when it doesn't exist there."""
    try:
        return gh("api", "-H", "Accept: application/vnd.github.raw+json",
                  f"repos/{repo}/contents/{path}?ref={ref}", json_out=False)
    except GhError as e:
        if "404" in str(e) or "Not Found" in str(e):
            return None
        raise


# ---------------------------------------------------------------- dates


def parse_day(text: str | None) -> dt.date:
    today = dt.date.today()
    if not text or text == "today":
        return today
    if text == "yesterday":
        return today - dt.timedelta(days=1)
    return dt.date.fromisoformat(text)


def day_range(day: dt.date, tz: dt.tzinfo | None = None) -> tuple[str, str]:
    """Local midnight to local midnight. Each end gets its own UTC offset, so DST days work."""
    if tz is None:
        start = dt.datetime.combine(day, dt.time(0, 0, 0)).astimezone()
        end = dt.datetime.combine(day, dt.time(23, 59, 59)).astimezone()
    else:
        start = dt.datetime.combine(day, dt.time(0, 0, 0), tzinfo=tz)
        end = dt.datetime.combine(day, dt.time(23, 59, 59), tzinfo=tz)
    return start.isoformat(), end.isoformat()


def parse_ts(text: str | None) -> dt.datetime | None:
    if not text:
        return None
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


def local(ts: dt.datetime | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    return ts.astimezone().strftime(fmt) if ts else ""


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ---------------------------------------------------------------- titles, sizes


def pr_type(title: str) -> str:
    m = re.match(r"\s*\[([A-Za-z]+)\]", title or "")
    return m.group(1).upper() if m else ""


def size_bucket(lines: int) -> str:
    for limit, name in SIZE_BUCKETS:
        if limit is None or lines < limit:
            return name
    return SIZE_BUCKETS[-1][1]


DISCORD_SPECIAL = re.compile(r"([_*~`|])")


def discord_escape(title: str) -> str:
    """Escape what Discord would turn into formatting: __init__ becomes underlined otherwise."""
    return DISCORD_SPECIAL.sub(lambda m: "\\" + m.group(1), title)


def discord_message(groups: dict[str, list[dict]]) -> str:
    parts = []
    for repo, prs in groups.items():
        if not prs:
            continue
        lines = [f"**{REPO_LABEL.get(repo, repo)}**"]
        for pr in sorted(prs, key=lambda p: p["createdAt"]):
            lines.append(f"- {discord_escape(pr['title'])} - <{pr['url']}>")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


# ---------------------------------------------------------------- lint


def unslop_vocabulary() -> list[str]:
    """Rule 7 of the unslop skill next to this one, minus the words it marks '(abstract)'."""
    path = SKILLS_DIR / "unslop" / "SKILL.md"
    if not path.exists():
        return []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"7\. \*\*AI vocabulary\.\*\* (.*)", line.strip())
        if m:
            words = m.group(1).split("Replace with")[0]
            out = []
            for w in words.split(","):
                w = w.strip().rstrip(".")
                if w and "(abstract)" not in w:
                    out.append(w)
            return out
    return []


def strip_code(text: str) -> str:
    """Blank out fenced code blocks and inline code, keeping line numbers."""
    out, fence = [], False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
            out.append("")
            continue
        out.append("" if fence else re.sub(r"`[^`\n]*`", "", line))
    return "\n".join(out)


def lint_text(text: str, discord: bool = False, vocabulary: list[str] | None = None) -> list[tuple[int, str]]:
    """Findings as (line, message). Rule numbers point into the unslop skill."""
    found: list[tuple[int, str]] = []
    for i, line in enumerate(text.splitlines(), 1):
        if "—" in line:
            found.append((i, "em dash (unslop rule 13)"))
        if "–" in line:
            found.append((i, "en dash (unslop rule 13)"))
        if re.search("[‘’“”]", line):
            found.append((i, "curly quote (unslop rule 19)"))
    words = vocabulary if vocabulary is not None else unslop_vocabulary()
    if words:
        pattern = re.compile(r"\b(" + "|".join(map(re.escape, words)) + r")\b", re.I)
        for i, line in enumerate(strip_code(text).splitlines(), 1):
            for m in pattern.finditer(line):
                found.append((i, f"'{m.group(1)}' (unslop rule 7)"))
    if discord and len(text) >= 2000:
        found.append((0, f"{len(text)} characters; Discord rejects 2,000 or more"))
    return found


# ---------------------------------------------------------------- PR facts

VIEW_FIELDS = (
    "number,title,url,state,author,isDraft,createdAt,updatedAt,mergedAt,closedAt,mergeable,"
    "mergeStateStatus,reviewDecision,additions,deletions,changedFiles,headRefOid,headRefName,"
    "baseRefName,labels,statusCheckRollup"
)


def search_prs(*filters: str, fields: str = "url,number,title,createdAt,state,repository") -> list[dict]:
    return gh("search", "prs", *filters, "--limit", "1000", "--json", fields) or []


def prs_on_day(day: dt.date) -> dict[str, list[dict]]:
    start, end = day_range(day)
    out = {}
    for repo in REPO_LABEL:
        out[repo] = search_prs("--author=@me", "--repo", repo, f"--created={start}..{end}",
                               fields="number,title,url,createdAt,state")
    return out


def check_results(rollup: list[dict] | None, repo: str) -> list[dict]:
    """Normalize statusCheckRollup into name/result pairs: pass, fail, pending, skip or noise."""
    results: dict[str, str] = {}
    for item in rollup or []:
        if item.get("__typename") == "StatusContext" or "context" in item:
            name = item.get("context", "")
            state = (item.get("state") or "").upper()
            result = {"SUCCESS": "pass", "PENDING": "pending", "EXPECTED": "pending"}.get(state, "fail")
        else:
            name = item.get("name", "")
            if (item.get("status") or "").upper() != "COMPLETED":
                result = "pending"
            else:
                conclusion = (item.get("conclusion") or "").upper()
                result = {"SUCCESS": "pass", "NEUTRAL": "pass", "SKIPPED": "skip"}.get(conclusion, "fail")
        if name in NOISE_CHECKS.get(repo, set()):
            result = "noise"
        # A rerun shows up twice; any pass among them wins over an older failure.
        if results.get(name) != "pass":
            results[name] = result
    return [{"name": n, "result": r} for n, r in sorted(results.items())]


_branch_checks: dict[str, dict[str, str]] = {}


def default_branch_checks(repo: str) -> dict[str, str]:
    """Check results on the default branch: the newest result per check name over the last 10 commits."""
    if repo in _branch_checks:
        return _branch_checks[repo]
    seen: dict[str, str] = {}
    try:
        commits = gh("api", f"repos/{repo}/commits?sha={DEFAULT_BRANCH.get(repo, 'main')}&per_page=10") or []
        for c in commits:
            runs = gh("api", f"repos/{repo}/commits/{c['sha']}/check-runs?per_page=100") or {}
            for run in runs.get("check_runs", []):
                if run.get("status") != "completed" or run["name"] in seen:
                    continue
                seen[run["name"]] = "pass" if run.get("conclusion") in ("success", "neutral", "skipped") else "fail"
    except GhError as e:
        seen["__error__"] = str(e)
    _branch_checks[repo] = seen
    return seen


BOTS = {"coderabbitai", "github-actions", "dependabot", "copilot-pull-request-reviewer", "greptile-apps",
        "macroscopeapp", "cursor", "codecov", "sonarqubecloud", "netlify", "vercel", "mintlify"}


def is_bot(login: str) -> bool:
    login = (login or "").lower()
    return login.endswith("[bot]") or login.removesuffix("[bot]") in BOTS


def removed_lines_by_file(diff: str) -> dict[str, list[str]]:
    """Lines a unified diff removes, per old path. Short lines like ')' are skipped."""
    out: dict[str, list[str]] = collections.defaultdict(list)
    path = None
    for line in diff.splitlines():
        if line.startswith("--- "):
            path = line[6:] if line.startswith("--- a/") else None
        elif line.startswith("-") and not line.startswith("---") and path:
            text = line[1:].strip()
            if len(text) >= 12:
                out[path].append(text)
    return out


def superseded(repo: str, number: int, base: str) -> str | None:
    """Return a reason when none of the lines the PR removes are still on the base branch."""
    diff = gh("pr", "diff", str(number), "--repo", repo, json_out=False)
    removed = removed_lines_by_file(diff)
    total = sum(len(v) for v in removed.values())
    if total < 3 or len(removed) > 10:
        return None
    still = 0
    for path, lines in removed.items():
        text = raw_file(repo, path, base)
        if text is None:
            continue
        have = {line.strip() for line in text.splitlines()}
        still += sum(1 for line in lines if line in have)
    if still == 0:
        return f"{base} no longer has any of the {total} lines this PR removes"
    return None


def pr_facts(url: str) -> dict:
    """Everything the status skill needs about one open PR, plus mechanical signals and a verdict hint."""
    fields = VIEW_FIELDS + ",body,reviews,comments,commits,latestReviews,reviewRequests,headRepositoryOwner"
    pr = gh("pr", "view", url, "--json", fields)
    repo = "/".join(url.split("/")[3:5])
    n = pr["number"]
    me = USER.lower()
    pr["repo"] = repo
    pr["checks"] = check_results(pr.pop("statusCheckRollup", None), repo)
    signals: list[str] = []
    hint = "wait"

    failing = [c["name"] for c in pr["checks"] if c["result"] == "fail"]
    pending = [c["name"] for c in pr["checks"] if c["result"] == "pending"]
    pr_caused, also_on_base = [], []
    if failing and repo in DEFAULT_BRANCH:
        base_checks = default_branch_checks(repo)
        for name in failing:
            (also_on_base if base_checks.get(name) == "fail" else pr_caused).append(name)
    else:
        pr_caused = failing
    pr["ci"] = {"failing_pr_caused": pr_caused, "failing_also_on_base": also_on_base, "pending": pending}

    # Activity: who said what, and whether the last word belongs to someone other than me.
    events = []
    for c in pr.get("comments") or []:
        events.append(("comment", c["author"]["login"], c["createdAt"], c.get("body", "")))
    for r in pr.get("reviews") or []:
        events.append((f"review {r.get('state', '').lower()}", r["author"]["login"], r.get("submittedAt"), r.get("body", "")))
    try:
        for c in gh_pages(f"repos/{repo}/pulls/{n}/comments"):
            events.append(("inline comment", c["user"]["login"], c["created_at"], c.get("body", "")))
    except GhError as e:
        signals.append(f"inline comments unread: {e}")
    for c in pr.get("commits") or []:
        authors = [a.get("login") or a.get("name") or "" for a in c.get("authors") or []]
        events.append(("commit", authors[0] if authors else "", c.get("committedDate"), c.get("messageHeadline", "")))
    events = [e for e in events if e[2]]
    events.sort(key=lambda e: e[2])
    cutoff = now_utc() - dt.timedelta(hours=24)
    pr["activity_24h"] = [
        {"kind": k, "who": w, "at": local(parse_ts(t)), "text": (b or "")[:200]}
        for k, w, t, b in events if parse_ts(t) >= cutoff and not is_bot(w)
    ]
    humans = [e for e in events if not is_bot(e[1])]
    last_mine = max((e[2] for e in humans if e[1].lower() == me), default="")
    # An approval or a pushed commit asks nothing of me; a comment or a review with words might.
    unanswered = [e for e in humans if e[1].lower() != me and e[2] > last_mine
                  and e[0] not in ("commit", "review approved") and (e[3] or "").strip()]
    pr["unanswered"] = [{"kind": k, "who": w, "at": local(parse_ts(t)), "text": (b or "")[:300]} for k, w, t, b in unanswered]
    last = parse_ts(humans[-1][2]) if humans else parse_ts(pr["updatedAt"])
    pr["age_days"] = round((now_utc() - parse_ts(pr["createdAt"])).total_seconds() / 86400, 1)
    pr["idle_days"] = round((now_utc() - last).total_seconds() / 86400, 1)
    pr["has_ai_label"] = any(label["name"] == AI_LABEL for label in pr.get("labels") or [])

    # Drift: commits on the base since the branch point that touch this PR's files.
    base = pr["baseRefName"]
    pr["behind_by"], pr["base_touched_files"] = None, []
    try:
        cmp = gh("api", f"repos/{repo}/compare/{base}...{pr['headRefOid']}")
        pr["behind_by"] = cmp.get("behind_by")
        mine_files = {f["filename"] for f in cmp.get("files") or []}
        if pr["behind_by"]:
            since = gh("api", f"repos/{repo}/compare/{cmp['merge_base_commit']['sha']}...{base}")
            pr["base_touched_files"] = sorted(mine_files & {f["filename"] for f in since.get("files") or []})
    except GhError as e:
        signals.append(f"compare failed: {e}")

    # A docs PR waits for the swarms PR it documents.
    pr["waits_on"] = []
    if repo == DOCS:
        body = pr.get("body") or ""
        nums = set(re.findall(r"github\.com/kyegomez/swarms/pull/(\d+)", body))
        nums |= set(re.findall(r"\bkyegomez/swarms#(\d+)", body))  # "Merge after kyegomez/swarms#3124"
        for num in sorted(nums, key=int):
            try:
                state = gh("pr", "view", num, "--repo", SWARMS, "--json", "state")["state"]
            except GhError as e:
                if "Could not resolve to a PullRequest" in str(e):
                    continue  # an issue, such as the one the framework PR closes; nothing waits on it
                state = "UNKNOWN"
            pr["waits_on"].append({"pr": f"{SWARMS}#{num}", "state": state})

    gone = None
    if pr.get("deletions", 0) >= 3 and repo in DEFAULT_BRANCH:
        try:
            gone = superseded(repo, n, base)
        except GhError as e:
            signals.append(f"superseded check failed: {e}")

    conflicting = pr.get("mergeable") == "CONFLICTING" or pr.get("mergeStateStatus") == "DIRTY"
    if gone:
        hint, signals = "close", signals + [f"superseded: {gone}"]
    elif conflicting:
        hint, signals = "rebase", signals + ["conflicts with the base branch"]
    elif pr.get("reviewDecision") == "CHANGES_REQUESTED" or pr["unanswered"]:
        hint = "rework"
        if pr.get("reviewDecision") == "CHANGES_REQUESTED":
            signals.append("changes requested")
        for u in pr["unanswered"]:
            signals.append(f"unanswered {u['kind']} by {u['who']} at {u['at']}")
    elif pr_caused:
        hint, signals = "rework", signals + [f"failing here but not on {base}: {', '.join(pr_caused)}"]
    elif [w for w in pr["waits_on"] if w["state"] == "OPEN"]:
        hint, signals = "wait", signals + [f"waits on {', '.join(w['pr'] for w in pr['waits_on'])}"]
    elif pending:
        hint, signals = "wait", signals + [f"checks pending: {', '.join(pending)}"]
    elif pr["idle_days"] >= 3 and not pr.get("isDraft"):
        hint, signals = "nudge", signals + [f"no human activity for {pr['idle_days']} days"]
    if pr["base_touched_files"]:
        # Master moves daily, so this alone isn't a rebase; GitHub's mergeable state decides that.
        signals.append(f"{base} changed {', '.join(pr['base_touched_files'])} since the branch point")
    if repo == SWARMS and not pr["has_ai_label"]:
        signals.append(f"missing the {AI_LABEL} label")
    pr["ready"] = (
        not pr.get("isDraft") and pr.get("mergeable") == "MERGEABLE"
        and pr.get("mergeStateStatus") not in ("BLOCKED", "DIRTY")
        and pr.get("reviewDecision") not in ("CHANGES_REQUESTED", "REVIEW_REQUIRED")
        and not pending and not pr_caused and not pr["unanswered"] and not gone
        and not any(w["state"] != "MERGED" for w in pr["waits_on"])
    )
    pr["hint"], pr["signals"] = hint, signals
    for key in ("comments", "reviews", "commits", "body"):
        pr.pop(key, None)
    return pr


def collect_status(workers: int = 4) -> dict:
    errors: list[str] = []
    try:
        mine = search_prs("--author=@me", "--state=open")
    except GhError as e:
        return {"errors": [f"listing your open PRs failed, so this report is empty: {e}"], "prs": []}
    try:
        theirs = [p for p in search_prs(f"--owner={USER}", "--state=open") if p["url"] not in {m["url"] for m in mine}]
    except GhError as e:
        theirs, errors = [], errors + [f"listing others' PRs on your repos failed: {e}"]
    since = (now_utc() - dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        merged = search_prs("--author=@me", f"--merged-at=>={since}", fields="url,number,title,repository,closedAt")
    except GhError as e:
        merged, errors = [], errors + [f"listing merged PRs failed: {e}"]
    urls = [(p["url"], "mine") for p in mine] + [(p["url"], "theirs") for p in theirs]
    prs = []
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(pr_facts, url): (url, whose) for url, whose in urls}
        for fut in cf.as_completed(futures):
            url, whose = futures[fut]
            try:
                facts = fut.result()
                facts["whose"] = whose
                prs.append(facts)
            except GhError as e:
                errors.append(f"{url}: {e}")
    prs.sort(key=lambda p: (p["whose"], p["repo"], p["number"]))
    return {
        "generated": local(now_utc()),
        "counts": {"open": len(prs), "repos": len({p["repo"] for p in prs})},
        "merged_24h": [{"pr": f"{p['repository']['nameWithOwner']}#{p['number']}", "title": p["title"], "url": p["url"]} for p in merged],
        "errors": errors,
        "prs": prs,
    }


# ---------------------------------------------------------------- ledger

LEDGER_COLUMNS = ["listed", "item", "source", "type", "est_lines", "pr", "opened", "lines",
                  "state", "merged", "hours", "reason", "brief"]


def read_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t") if lines else LEDGER_COLUMNS
    for line in lines[1:]:
        if line.strip():
            values = line.split("\t")
            rows.append({c: (values[i] if i < len(values) else "") for i, c in enumerate(header)})
    return rows


SECRETS = [
    (re.compile(r"(?<=://)[^/\s@]+@"), "***@"),  # credentials in a URL
    (re.compile(r"(?i)\b([A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD))(\s*[=:]\s*)[\"']?[^\s\"']+"), r"\1\2***"),
    (re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w{20,}"
                r"|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,})"), "***"),
]


def redact(text: str) -> str:
    for pattern, repl in SECRETS:
        text = pattern.sub(repl, text)
    return text


def clean_cell(value) -> str:
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip()


def write_ledger(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = ["\t".join(LEDGER_COLUMNS)]
    for row in rows:
        body.append("\t".join(clean_cell(row.get(c, "")) for c in LEDGER_COLUMNS))
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".outcomes.", suffix=".tsv")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(body) + "\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def ledger_upsert(rows: list[dict], **fields) -> dict:
    """Update the row for this PR or item, or add one. Empty values never overwrite."""
    pr, item = fields.get("pr"), fields.get("item")
    row = next((r for r in rows if pr and r.get("pr") == pr), None)
    if row is None and item:
        row = next((r for r in rows if r.get("item") == item and not r.get("pr")), None)
    if row is None:
        row = {c: "" for c in LEDGER_COLUMNS}
        rows.append(row)
    for key, value in fields.items():
        value = clean_cell(value)  # whitespace-only counts as empty
        if value:
            row[key] = value
    return row


def maintainer_reason(repo: str, number: int) -> str:
    data = gh("pr", "view", str(number), "--repo", repo, "--json", "reviews,comments")
    said = [(c["createdAt"], c.get("body", "")) for c in data.get("comments") or [] if c["author"]["login"] == MAINTAINER]
    said += [(r.get("submittedAt") or "", r.get("body", "")) for r in data.get("reviews") or [] if r["author"]["login"] == MAINTAINER]
    said = [s for s in said if (s[1] or "").strip()]
    return clean_cell(sorted(said)[-1][1])[:300] if said else ""


def infer_source(body: str) -> str:
    m = re.search(r"(?i)\b(?:closes|fixes|resolves)\s+#(\d+)", body or "")
    return f"issue #{m.group(1)}" if m else ""


def ledger_sync(path: Path, since: dt.date | None) -> tuple[int, int]:
    rows = read_ledger(path)
    if since is None:
        dates = [r["listed"] for r in rows if r.get("listed")] + [r["opened"][:10] for r in rows if r.get("opened")]
        if not dates:
            raise SystemExit("The ledger is empty. Backfill it first with --since YYYY-MM-DD.")
        since = dt.date.fromisoformat(min(dates))
    added = updated = 0
    for repo in REPO_LABEL:
        prs = gh("pr", "list", "--repo", repo, "--author", USER, "--state", "all", "--limit", "1000", "--json",
                 "number,title,state,createdAt,mergedAt,closedAt,additions,deletions,url,reviewDecision,body")
        for p in prs:
            created = parse_ts(p["createdAt"])
            if created.astimezone().date() < since:
                continue
            key = f"{repo}#{p['number']}"
            row = next((r for r in rows if r.get("pr") == key), None) or \
                next((r for r in rows if r.get("item") == p["title"] and not r.get("pr")), None)
            if row is None:
                row = {c: "" for c in LEDGER_COLUMNS}
                rows.append(row)
                added += 1
            else:
                updated += 1
            merged_at = parse_ts(p.get("mergedAt"))
            state = {"OPEN": "open", "MERGED": "merged", "CLOSED": "closed"}[p["state"]]
            # GitHub owns these columns.
            row.update(pr=key, type=pr_type(p["title"]), opened=local(created),
                       lines=str(p["additions"] + p["deletions"]), state=state, merged=local(merged_at),
                       hours=str(round((merged_at - created).total_seconds() / 3600, 1)) if merged_at else "")
            # These only fill gaps, so the picks run's values and hand edits survive.
            row["item"] = row.get("item") or p["title"]
            row["listed"] = row.get("listed") or local(created, "%Y-%m-%d")
            row["source"] = row.get("source") or infer_source(p.get("body", "")) or "unknown"
            if not row.get("reason") and (state == "closed" or p.get("reviewDecision") == "CHANGES_REQUESTED"):
                row["reason"] = maintainer_reason(repo, p["number"]) or ("closed with no comment from Kye" if state == "closed" else "")
    rows.sort(key=lambda r: (r.get("listed", ""), r.get("opened", ""), r.get("pr", "")))
    write_ledger(path, rows)
    return added, updated


def ledger_stats(rows: list[dict], days: int | None, repo: str | None) -> str:
    if days:
        start = (dt.date.today() - dt.timedelta(days=days)).isoformat()
        rows = [r for r in rows if (r.get("listed") or "") >= start]
    with_pr = [r for r in rows if r.get("pr") and (not repo or r["pr"].startswith(repo + "#"))]

    def table(title: str, key, order: list[str] | None = None) -> list[str]:
        groups: dict[str, list[dict]] = collections.defaultdict(list)
        for r in with_pr:
            groups[key(r)].append(r)
        out = [f"| {title} | PRs | merged | open | closed | median hours to merge |", "| --- | --- | --- | --- | --- | --- |"]
        rank = {name: i for i, name in enumerate(order or [])}
        for name, group in sorted(groups.items(), key=lambda kv: (rank.get(kv[0], len(rank)), kv[0])):
            merged = [r for r in group if r["state"] == "merged"]
            hours = [float(r["hours"]) for r in merged if r.get("hours")]
            med = f"{statistics.median(hours):.1f}" if hours else ""
            out.append(f"| {name or '?'} | {len(group)} | {len(merged)} | "
                       f"{sum(r['state'] == 'open' for r in group)} | {sum(r['state'] == 'closed' for r in group)} | {med} |")
        return out

    lines = [f"{len(with_pr)} PRs, {sum(r['state'] == 'merged' for r in with_pr)} merged."]
    lines += [""] + table("Type", lambda r: r.get("type", ""))
    lines += [""] + table("Size (lines changed)", lambda r: size_bucket(int(r.get("lines") or 0)), [b for _, b in SIZE_BUCKETS])
    lines += [""] + table("Source", lambda r: ((r.get("source") or "unknown").split() or ["unknown"])[0])
    never = [r for r in rows if not r.get("pr")]
    lines += ["", f"Listed but never opened: {len(never)}."]
    closed = [r for r in with_pr if r["state"] == "closed" or r.get("reason")]
    if closed:
        lines += ["", "Declined or changes requested:"]
        lines += [f"- {r['pr']} {r['item']}: {r.get('reason') or 'no reason recorded'}" for r in closed]
    return "\n".join(lines)


# ---------------------------------------------------------------- scans

TEXT_EXT = {".py", ".md", ".mdx", ".txt", ".yaml", ".yml", ".json", ".toml", ".ipynb", ".cfg", ".ini"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache", ".ruff_cache", "build", "dist"}
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def iter_text_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if Path(name).suffix in TEXT_EXT:
                yield Path(dirpath) / name


def area_of(path: Path, tree: Path, docs: Path | None) -> str:
    if docs and docs in path.parents:
        return "docs"
    rel = path.relative_to(tree).parts
    return rel[0] if rel and rel[0] in ("swarms", "tests", "examples") else "other"


def roots(tree: Path, docs: Path | None) -> list[Path]:
    return [tree] + ([docs] if docs else [])


def scan_names(names: list[str], tree: Path, docs: Path | None, max_hits: int = 15) -> dict:
    wanted = set(names)
    result = {n: {"total": 0, "areas": collections.Counter(), "hits": []} for n in names}
    for root in roots(tree, docs):
        for path in iter_text_files(root):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not wanted & set(WORD.findall(text)):
                continue
            area = area_of(path, tree, docs)
            base = docs if area == "docs" else tree
            for i, line in enumerate(text.splitlines(), 1):
                for name in wanted & set(WORD.findall(line)):
                    count = sum(1 for w in WORD.findall(line) if w == name)
                    entry = result[name]
                    entry["total"] += count
                    entry["areas"][area] += count
                    if len(entry["hits"]) < max_hits:
                        entry["hits"].append(f"{'docs/' if area == 'docs' else ''}{path.relative_to(base).as_posix()}:{i}: {line.strip()[:120]}")
    for entry in result.values():
        entry["areas"] = dict(entry["areas"])
    return result


def token_counts(tree: Path, docs: Path | None) -> collections.Counter:
    counts: collections.Counter = collections.Counter()
    for root in roots(tree, docs):
        for path in iter_text_files(root):
            try:
                counts.update(WORD.findall(path.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
    return counts


def definitions(paths: list[Path], tree: Path) -> list[dict]:
    """Module-level functions, classes and constants, methods, and self.attributes assigned in classes."""
    found = []
    for root in paths:
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for path in files:
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            try:
                module = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            rel = path.relative_to(tree).as_posix()

            def add(node, kind, name, owner=""):
                found.append({
                    "name": name, "kind": kind, "owner": owner, "file": rel, "line": node.lineno,
                    "lines": (getattr(node, "end_lineno", node.lineno) or node.lineno) - node.lineno + 1,
                    "decorated": bool(getattr(node, "decorator_list", [])),
                })

            for node in module.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add(node, "function", node.name)
                elif isinstance(node, ast.ClassDef):
                    add(node, "class", node.name)
                    for sub in node.body:
                        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            add(sub, "method", sub.name, node.name)
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Attribute) and isinstance(sub.ctx, ast.Store) \
                                and isinstance(sub.value, ast.Name) and sub.value.id == "self":
                            add(sub, "attribute", sub.attr, node.name)
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id.isupper():
                            add(node, "constant", target.id)
    return found


def find_unused(paths: list[Path], tree: Path, docs: Path | None) -> list[dict]:
    defs = [d for d in definitions(paths, tree) if not (d["name"].startswith("__") and d["name"].endswith("__"))
            and not d["name"].startswith("test_")]
    counts = token_counts(tree, docs)
    sites = collections.Counter(d["name"] for d in defs)
    out = []
    seen = set()
    for d in defs:
        # Every occurrence of the name is a definition or an assignment: nothing reads it.
        if counts[d["name"]] <= sites[d["name"]] and (d["name"], d["file"], d["line"]) not in seen:
            seen.add((d["name"], d["file"], d["line"]))
            d["public"] = not d["name"].startswith("_")
            out.append(d)
    out.sort(key=lambda d: (d["decorated"], d["public"], -d["lines"]))
    return out


# ---------------------------------------------------------------- competition


def competition(repo: str, terms: list[str], removed: str | None, allow: set[int]) -> list[dict]:
    seen: dict[int, dict] = {}
    for term in terms:
        for p in gh("pr", "list", "--repo", repo, "--state", "all", "--search", term, "--limit", "50", "--json",
                    "number,title,state,author,additions,deletions,url,updatedAt,createdAt") or []:
            if p["number"] in allow:
                continue
            entry = seen.setdefault(p["number"], {**p, "author": p["author"]["login"], "terms": []})
            entry["terms"].append(term)
    if removed:
        pattern = re.compile(removed)
        for entry in seen.values():
            try:
                diff = gh("pr", "diff", str(entry["number"]), "--repo", repo, json_out=False)
                entry["removes_same"] = any(
                    line.startswith("-") and not line.startswith("---") and pattern.search(line)
                    for line in diff.splitlines()
                )
            except GhError as e:
                entry["removes_same"] = None
                entry["error"] = str(e)
    return sorted(seen.values(), key=lambda e: -e["number"])


# ---------------------------------------------------------------- verification

PINNED_ENV = {
    "SWARMS_TELEMETRY_ON": "false",  # telemetry is on when unset
    "LITELLM_LOCAL_MODEL_COST_MAP": "True",
    "PYTHON_DOTENV_DISABLED": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
}


def pinned_env(tree: Path) -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if key.endswith("_API_KEY"):
            env[key] = ""
    env.update({"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": ""})
    env.update(PINNED_ENV)
    # Replace, not prepend: the main clone's editable install must not win.
    env["PYTHONPATH"] = str(tree)
    return env


def which_swarms(tree: Path, python: Path) -> Path:
    probe = "import os, swarms; print(os.path.realpath(swarms.__file__))"
    p = subprocess.run([str(python), "-c", probe], cwd=tree, env=pinned_env(tree),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    if p.returncode != 0:
        raise SystemExit(f"FAIL import swarms in {tree}:\n{p.stderr[-2000:]}")
    return Path(p.stdout.strip().splitlines()[-1]).resolve()


def resolve_command(cmd: list[str], python: Path) -> list[str]:
    if not cmd:
        raise SystemExit("Give the command after --, for example: -- pytest tests/structs/test_agent.py -q")
    if cmd[0] in ("python", "python3", "py"):
        return [str(python), *cmd[1:]]
    if cmd[0] in ("pytest", "black", "ruff"):
        return [str(python), "-m", *cmd]
    found = shutil.which(cmd[0])  # Windows runs a .cmd shim such as npx only by its full path
    return [found, *cmd[1:]] if found else cmd


def run_pinned(tree: Path, cmd: list[str], python: Path, log: Path | None = None) -> int:
    tree = tree.resolve()
    origin = which_swarms(tree, python)
    if tree not in origin.parents:
        raise SystemExit(f"FAIL swarms imports from {origin}, not from the tree under test {tree}")
    print(f"swarms from {origin}", flush=True)
    full = resolve_command(cmd, python)
    p = subprocess.run(full, cwd=tree, env=pinned_env(tree), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    output = p.stdout + p.stderr
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(f"$ {' '.join(full)}\n# cwd {tree}\n# swarms from {origin}\n{output}\n# exit {p.returncode}\n", encoding="utf-8")
    sys.stdout.write(output[-6000:])
    print(f"exit {p.returncode}")
    return p.returncode


# ---------------------------------------------------------------- git (worktrees only, never the main checkout)


def git(clone: Path, *args, check: bool = True) -> str:
    p = subprocess.run(["git", "-C", str(clone), *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        raise SystemExit(f"FAIL git {' '.join(map(str, args))} in {clone}: {p.stderr.strip()}")
    return p.stdout.strip()


def read_remotes(clone: Path) -> dict[str, str]:
    """Remote URLs from .git/config, read as a file so no git command runs in the main clone."""
    gitdir = clone / ".git"
    if gitdir.is_file():
        m = re.search(r"gitdir:\s*(.+)", gitdir.read_text(encoding="utf-8"))
        gitdir = Path(m.group(1).strip()) if m else gitdir
        common = gitdir / "commondir"
        if common.exists():
            gitdir = (gitdir / common.read_text(encoding="utf-8").strip()).resolve()
    config = gitdir / "config"
    remotes, current = {}, None
    if not config.exists():
        return remotes
    for line in config.read_text(encoding="utf-8").splitlines():
        m = re.match(r'\s*\[remote "([^"]+)"\]', line)
        if m:
            current = m.group(1)
        elif line.strip().startswith("["):
            current = None
        elif current and line.strip().startswith("url"):
            remotes[current] = line.split("=", 1)[1].strip()
    return remotes


def upstream_remote(clone: Path, repo: str) -> str:
    for name, url in read_remotes(clone).items():
        if repo.lower() in url.lower() and USER.lower() not in url.lower():
            return name
    raise SystemExit(f"FAIL no remote for {repo} in {clone}")


def checkout(run: Path, items: list[tuple[str, str]], base_too: bool = True) -> list[dict]:
    """Detached worktrees under run/ for PR heads (and their merge bases) or plain refs.

    items are (repo, ref) where ref is 'pr:<n>', a branch on the upstream repo, or a SHA.
    One fetch per clone, so parallel agents never fight over fetch locks.
    """
    run = run.resolve()
    run.mkdir(parents=True, exist_ok=True)
    by_repo: dict[str, list[str]] = collections.defaultdict(list)
    for repo, ref in items:
        by_repo[repo].append(ref)
    made = []
    for repo, refs in by_repo.items():
        clone = clone_for(repo)
        remote = upstream_remote(clone, repo)
        base = DEFAULT_BRANCH[repo]
        specs = [f"+refs/heads/{base}:refs/remotes/{remote}/{base}"]
        facts = {}
        for ref in refs:
            if ref.startswith("pr:"):
                n = ref[3:]
                path = run / f"{SHORT[repo]}-{n}.json"
                if path.exists():
                    facts[ref] = json.loads(path.read_text(encoding="utf-8"))
                else:
                    facts[ref] = gh("pr", "view", n, "--repo", repo, "--json", VIEW_FIELDS)
                    path.write_text(json.dumps(facts[ref], indent=1), encoding="utf-8")
                specs.append(f"refs/pull/{n}/head")  # objects only; no ref left behind
                if facts[ref]["baseRefName"] != base:
                    b = facts[ref]["baseRefName"]
                    specs.append(f"+refs/heads/{b}:refs/remotes/{remote}/{b}")
            elif not re.fullmatch(r"[0-9a-f]{7,40}", ref):
                specs.append(f"+refs/heads/{ref}:refs/remotes/{remote}/{ref}")
        git(clone, "fetch", "--quiet", remote, *dict.fromkeys(specs))
        for ref in refs:
            if ref.startswith("pr:"):
                n = ref[3:]
                head = facts[ref]["headRefOid"]
                wt = run / f"wt-{SHORT[repo]}-{n}"
                git(clone, "worktree", "add", "--detach", "--quiet", wt, head)
                entry = {"repo": repo, "ref": ref, "head": str(wt), "head_sha": head}
                if base_too:
                    # Queries run in the new worktree: the main clone only ever sees fetch and worktree.
                    mb = git(wt, "merge-base", "HEAD", f"{remote}/{facts[ref]['baseRefName']}")
                    bwt = run / f"base-{SHORT[repo]}-{n}"
                    git(clone, "worktree", "add", "--detach", "--quiet", bwt, mb)
                    entry.update(base=str(bwt), base_sha=mb)
            else:
                wt = run / f"wt-{SHORT[repo]}-{re.sub(r'[^A-Za-z0-9._-]', '-', ref)}"
                start = ref if re.fullmatch(r"[0-9a-f]{7,40}", ref) else f"{remote}/{ref}"
                git(clone, "worktree", "add", "--detach", "--quiet", wt, start)
                entry = {"repo": repo, "ref": ref, "head": str(wt), "head_sha": git(wt, "rev-parse", "HEAD")}
            made.append(entry)
    return made


def cleanup(run: Path) -> list[str]:
    run = run.resolve()
    removed, problems = [], []
    for clone in (swarms_clone(), docs_clone()):
        if not clone.exists():
            continue
        listing = git(clone, "worktree", "list", "--porcelain", check=False)
        for line in listing.splitlines():
            if line.startswith("worktree "):
                path = Path(line[9:]).resolve()
                if path == run or run in path.parents:
                    out = subprocess.run(["git", "-C", str(clone), "worktree", "remove", "--force", str(path)],
                                         capture_output=True, text=True)
                    (removed if out.returncode == 0 else problems).append(str(path))
    shutil.rmtree(run, ignore_errors=True)
    for clone in (swarms_clone(), docs_clone()):
        if clone.exists():
            for line in git(clone, "worktree", "list", "--porcelain", check=False).splitlines():
                if line.startswith("worktree ") and (run == Path(line[9:]).resolve() or run in Path(line[9:]).resolve().parents):
                    problems.append(f"still listed: {line[9:]}")
    if run.exists():
        problems.append(f"{run} still exists")
    return problems or [f"removed {len(removed)} worktrees and {run}"]


# ---------------------------------------------------------------- publish

PLACEHOLDER = re.compile(r"<(?!https?://|!--)(?:[A-Z]|model|url|link|number|date|sha|n|m|[^<>\n]*\s[^<>\n]*)>")
REF = re.compile(r"\{\{(\w+)\.(url|number)\}\}")


def load_manifest(task: Path) -> dict:
    path = task / "publish.json"
    if not path.exists():
        raise SystemExit(f"FAIL no publish.json in {task}")
    m = json.loads(path.read_text(encoding="utf-8"))
    ids = []
    for pr in m.get("prs") or []:
        for key in ("id", "repo", "head", "sha", "title", "body"):
            if not pr.get(key):
                raise SystemExit(f"FAIL publish.json: a PR is missing '{key}'")
        if ":" not in pr["head"]:
            raise SystemExit(f"FAIL publish.json: head must be owner:branch, got {pr['head']}")
        pr.setdefault("base", DEFAULT_BRANCH.get(pr["repo"], "main"))
        pr.setdefault("label", pr["repo"] == SWARMS)
        pr.setdefault("drift", "fail")
        ids.append(pr["id"])
    if not ids or len(ids) != len(set(ids)):
        raise SystemExit("FAIL publish.json needs at least one PR, with unique ids")
    return m


def approved_files(m: dict) -> list[str]:
    files = ["publish.json"]  # where it posts and how it's announced are part of what Khalil approved
    for pr in m["prs"]:
        files += [pr["title"], pr["body"]] + ([pr["relabel_body"]] if pr.get("relabel_body") else [])
    return list(dict.fromkeys(files))


def texts(pr: dict) -> list[str]:
    """Every file that can end up on GitHub for this PR: title, body, and the relabel body."""
    return [pr["title"], pr["body"]] + ([pr["relabel_body"]] if pr.get("relabel_body") else [])


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(text: str, posted: dict[str, dict], pending: str = "(linked in a moment)") -> str:
    def sub(match):
        ref = posted.get(match.group(1))
        if not ref:
            return pending
        return str(ref["number"] if match.group(2) == "number" else ref["url"])
    return REF.sub(sub, text)


def publish_checks(task: Path, m: dict, on: str | None) -> list[str]:
    lines: list[str] = []

    def say(status: str, text: str):
        lines.append(f"{status} {text}")

    if on and dt.date.today().isoformat() != on:
        say("FAIL", f"today is {dt.date.today()}, but this publish is for {on}; a missed T3 run moves to next week")
    owners = {pr["head"].split(":")[0] for pr in m["prs"]}
    try:
        login = gh("api", "user", "--jq", ".login", json_out=False).strip()
        say("PASS" if login in owners else "FAIL", f"gh logged in as {login}")
    except GhError as e:
        say("FAIL", f"gh auth: {e}")
    approved = task / "approved.sha256"
    approved_at = dt.datetime.fromtimestamp(approved.stat().st_mtime, dt.timezone.utc) if approved.exists() else now_utc()
    ids = {pr["id"] for pr in m["prs"]}
    order = [pr["id"] for pr in m["prs"]]
    for i, pr in enumerate(m["prs"]):
        title = (task / pr["title"]).read_text(encoding="utf-8") if (task / pr["title"]).exists() else ""
        later = sorted({ref for ref, _ in REF.findall(title)} & set(order[i:]))
        if later:
            say("FAIL", f"[{pr['id']}] {pr['title']} names {', '.join(later)}, which posts after it; "
                        "titles aren't edited after posting, so reorder publish.json")
    for pr in m["prs"]:
        for name in texts(pr):
            text = (task / name).read_text(encoding="utf-8") if (task / name).exists() else ""
            unknown = sorted({ref for ref, _ in REF.findall(text)} - ids)
            if unknown:
                say("FAIL", f"[{pr['id']}] {name} names unknown PR ids: {', '.join(unknown)}")
    if not approved.exists():
        say("FAIL", "no approved.sha256: run `publish approve` after Khalil approves the text")
    else:
        want = dict(line.split("  ", 1)[::-1] for line in approved.read_text(encoding="utf-8").splitlines() if "  " in line)
        bad = [f for f in approved_files(m) if f not in want or not (task / f).exists() or sha256(task / f) != want[f]]
        say("FAIL" if bad else "PASS", f"approved text changed or missing: {', '.join(bad)}" if bad else "approved text and publish.json unchanged")
    for pr in m["prs"]:
        repo, (owner, branch) = pr["repo"], pr["head"].split(":", 1)
        fork = f"{owner}/{repo.split('/')[1]}"
        tag = f"[{pr['id']}]"
        for name in texts(pr):
            text = (task / name).read_text(encoding="utf-8") if (task / name).exists() else ""
            holes = sorted(set(PLACEHOLDER.findall(text)))
            if holes:
                say("FAIL", f"{tag} {name} still has placeholders: {' '.join(holes)}")
            if name != pr["title"] and ROBOT_LINE not in text:
                say("FAIL", f"{tag} {name} has no '{ROBOT_LINE}' line; the repo requires AI disclosure")
        try:
            live = gh("api", f"repos/{fork}/git/ref/heads/{branch}", "--jq", ".object.sha", json_out=False).strip()
        except GhError as e:
            live = f"missing ({str(e)[:80]})"
        say("PASS" if live == pr["sha"] else "FAIL", f"{tag} {fork}:{branch} is at {live[:8]}, expected {pr['sha'][:8]}")
        try:
            existing = [p for p in gh("pr", "list", "--repo", repo, "--state", "all", "--head", branch, "--json",
                                      "number,url,headRepositoryOwner") or []
                        if p["headRepositoryOwner"]["login"].lower() == owner.lower()]
            say("FAIL" if existing else "PASS", f"{tag} PR already exists: {existing[0]['url']}" if existing else f"{tag} no PR yet for {branch}")
        except GhError as e:
            say("FAIL", f"{tag} could not list PRs for {branch}: {e}")
        try:
            cmp = gh("api", f"repos/{repo}/compare/{pr['base']}...{pr['sha']}")
            say("INFO", f"{tag} ahead {cmp['ahead_by']}, behind {cmp['behind_by']} of {pr['base']}")
            if pr.get("commits") and cmp["ahead_by"] != pr["commits"]:
                say("FAIL", f"{tag} expected {pr['commits']} commit(s) ahead of {pr['base']}, found {cmp['ahead_by']}")
            mine = {f["filename"] for f in cmp.get("files") or []}
            if cmp["behind_by"]:
                since = gh("api", f"repos/{repo}/compare/{cmp['merge_base_commit']['sha']}...{pr['base']}")
                touched = sorted(mine & {f["filename"] for f in since.get("files") or []})
                if touched:
                    level = "FAIL" if pr["drift"] == "fail" else "WARN"
                    say(level, f"{tag} {pr['base']} changed {', '.join(touched)} since the branch point; rebase first")
                else:
                    say("PASS", f"{tag} nothing on {pr['base']} touched this PR's files since the branch point")
        except GhError as e:
            say("FAIL", f"{tag} compare failed: {e}")
        comp = pr.get("competition") or {}
        if comp.get("terms"):
            try:
                rows = [r for r in competition(repo, comp["terms"], comp.get("removed"), set(comp.get("allow") or []))
                        if r["author"].lower() != owner.lower()]
                blocking = []
                for r in rows:
                    if comp.get("removed") and r.get("removes_same") is None:
                        blocking.append((r, "its diff could not be read"))
                    elif comp.get("removed") and r.get("removes_same"):
                        blocking.append((r, "it removes the same lines"))
                    elif not comp.get("removed") and r["state"] != "CLOSED" and parse_ts(r["createdAt"]) > approved_at:
                        blocking.append((r, "it was opened after you approved, so nobody has judged it"))
                    else:
                        say("INFO", f"{tag} #{r['number']} by {r['author']} mentions {', '.join(r['terms'])} but doesn't compete")
                for r, why in blocking:
                    say("FAIL", f"{tag} #{r['number']} by {r['author']} ({r['state'].lower()}): {why} {r['url']}")
                if not blocking:
                    say("PASS", f"{tag} no competing PR")
            except GhError as e:
                say("FAIL", f"{tag} competition check failed: {e}")
        for check in pr.get("base_counts") or []:
            text = raw_file(repo, check["path"], pr["base"])
            have = text.count(check["needle"]) if text is not None else 0
            ok = have == check["count"]
            say("PASS" if ok else "FAIL", f"{tag} {check['path']} has {have} of '{check['needle']}' on {pr['base']}, expected {check['count']}")
    return lines


def wait_for_label(url: str, seconds: int) -> bool:
    deadline = time.monotonic() + seconds
    while True:
        try:
            labels = gh("pr", "view", url, "--json", "labels")["labels"]
            if any(label["name"] == AI_LABEL for label in labels):
                return True
        except GhError:
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(20)


def create_pr(pr: dict, title: str, body_file: Path) -> str:
    try:
        return gh("pr", "create", "--repo", pr["repo"], "--base", pr["base"], "--head", pr["head"],
                  "--title", title, "--body-file", body_file, json_out=False, tries=1).strip().splitlines()[-1]
    except GhError as e:
        if "rate limit" not in str(e).lower():
            raise
        # GraphQL is used up; REST has its own budget.
        data = gh("api", f"repos/{pr['repo']}/pulls", "-f", f"title={title}", "-f", f"head={pr['head']}",
                  "-f", f"base={pr['base']}", "-F", f"body=@{body_file}", tries=1)
        return data["html_url"]


def publish_post(task: Path, m: dict, label_wait: int) -> int:
    posted: dict[str, dict] = {}
    scratch = Path(tempfile.mkdtemp(prefix="swarms-publish-"))
    for pr in m["prs"]:
        title = render((task / pr["title"]).read_text(encoding="utf-8").strip(), posted)
        if "(linked in a moment)" in title:  # publish check refuses this order; kept as a guard
            if posted:
                record_post(m, posted)
            print(f"RESULT PARTIAL: [{pr['id']}] title refers to a PR posted after it; reorder publish.json")
            return 3
        body_file = scratch / f"{pr['id']}.md"
        body_file.write_text(render((task / pr["body"]).read_text(encoding="utf-8"), posted), encoding="utf-8")
        try:
            url = create_pr(pr, title, body_file)
        except GhError as e:
            done = ", ".join(p["url"] for p in posted.values()) or "nothing"
            left = ", ".join(p["id"] for p in m["prs"] if p["id"] not in posted)
            if posted:
                record_post(m, posted)
            print(f"RESULT PARTIAL: [{pr['id']}] gh pr create failed ({e}); already posted: {done}; "
                  f"not posted: {left}. Don't rerun: the checks refuse a PR that exists.")
            return 3
        posted[pr["id"]] = {"url": url, "number": int(url.rstrip("/").split("/")[-1]), "title": title}
        print(f"OPENED {pr['id']} {url}", flush=True)
    # Bodies that named a PR posted after them get the real link now.
    unfinished = []
    for pr in m["prs"]:
        template = (task / pr["body"]).read_text(encoding="utf-8")
        if any(ref not in posted or list(posted).index(ref) > list(posted).index(pr["id"]) for ref, _ in REF.findall(template)):
            body_file = scratch / f"{pr['id']}.final.md"
            body_file.write_text(render(template, posted), encoding="utf-8")
            try:
                gh("pr", "edit", posted[pr["id"]]["url"], "--body-file", body_file, json_out=False)
                print(f"LINKED {pr['id']} body now names the other PRs")
            except GhError as e:
                keep = task / f"{pr['id']}.linked.md"
                keep.write_text(body_file.read_text(encoding="utf-8"), encoding="utf-8")
                print(f"WARN [{pr['id']}] could not fill the links: {e}")
                unfinished.append(f"gh pr edit {posted[pr['id']]['url']} --body-file {keep}")
    for pr in m["prs"]:
        if not pr["label"]:
            continue
        url = posted[pr["id"]]["url"]
        if wait_for_label(url, label_wait):
            print(f"LABEL [{pr['id']}] {AI_LABEL} present")
        elif pr.get("relabel_body"):
            body_file = scratch / f"{pr['id']}.relabel.md"
            body_file.write_text(render((task / pr["relabel_body"]).read_text(encoding="utf-8"), posted), encoding="utf-8")
            try:
                gh("pr", "edit", url, "--body-file", body_file, json_out=False)
                got = wait_for_label(url, label_wait)
                print(f"LABEL [{pr['id']}] {AI_LABEL} {'present after the wording edit' if got else 'still missing after the wording edit'}")
            except GhError as e:
                print(f"WARN [{pr['id']}] relabel edit failed: {e}")
        else:
            print(f"WARN [{pr['id']}] {AI_LABEL} missing and no relabel_body to re-run the labeler")
    shutil.rmtree(scratch, ignore_errors=True)
    record_post(m, posted)
    urls = " ".join(p["url"] for p in posted.values())
    if unfinished:
        print(f"RESULT PARTIAL: posted {urls}, but a body still says '(linked in a moment)'. "
              f"Fix it with the approved text, links filled: {'; '.join(unfinished)}")
    else:
        print(f"RESULT posted {urls}")
    lead = posted[m["prs"][0]["id"]]
    if m.get("security"):
        print("DISCORD #management or product channel only: this is a security PR")
    else:
        print("DISCORD")
    print(lead["title"])
    print(lead["url"])
    return 3 if unfinished else 0


def record_post(m: dict, posted: dict[str, dict]) -> None:
    """The ledger row for the lead PR, written as soon as it exists."""
    path = ledger_path()
    rows = read_ledger(path)
    first = m["prs"][0]
    lead = posted[first["id"]]
    ledger_upsert(rows, item=m.get("item") or lead["title"], pr=f"{first['repo']}#{lead['number']}",
                  brief=m.get("brief"), source=m.get("source"), type=pr_type(lead["title"]),
                  est_lines=m.get("est_lines"), listed=m.get("listed"), state="open",
                  opened=local(now_utc()))
    try:
        write_ledger(path, rows)
        print(f"LEDGER {path}")
    except OSError as e:
        print(f"WARN ledger not written: {e}")


# ---------------------------------------------------------------- transcripts

CODEX_EXIT = re.compile(r'"exit_code"\s*:\s*(-?\d+)')


def summarize_claude(path: Path) -> dict:
    tools, errors, stamps, first = collections.Counter(), collections.Counter(), [], ""
    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("timestamp"):
            stamps.append(d["timestamp"])
        msg = d.get("message") or {}
        content = msg.get("content")
        if d.get("type") == "user":
            if isinstance(content, str) and not first and not content.startswith("<"):
                first = content
            for b in content if isinstance(content, list) else []:
                if b.get("type") == "text" and not first and not b.get("text", "").startswith("<"):
                    first = b["text"]
                if b.get("type") == "tool_result" and b.get("is_error"):
                    text = b.get("content")
                    text = text if isinstance(text, str) else json.dumps(text)
                    errors[clean_cell(text)[:120]] += 1
        elif d.get("type") == "assistant":
            for b in content if isinstance(content, list) else []:
                if b.get("type") == "tool_use":
                    tools[b.get("name", "?")] += 1
    return {"tools": tools, "errors": errors, "stamps": stamps, "first": first}


def summarize_codex(path: Path) -> dict:
    tools, errors, stamps, first, cwd = collections.Counter(), collections.Counter(), [], "", ""
    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("timestamp"):
            stamps.append(d["timestamp"])
        p = d.get("payload") or {}
        if d.get("type") == "session_meta":
            cwd = p.get("cwd", "")
        if d.get("type") != "response_item":
            continue
        kind = p.get("type")
        if kind in ("function_call", "custom_tool_call"):
            tools[p.get("name", "?")] += 1
        elif kind in ("function_call_output", "custom_tool_call_output"):
            out = p.get("output")
            text = out if isinstance(out, str) else " ".join(o.get("text", "") for o in out or [] if isinstance(o, dict))
            # Codex wraps each command's result as JSON with an exit_code; a script error says "Script failed".
            if text.startswith("Script failed"):
                errors[clean_cell(text)[:120]] += 1
            for m in CODEX_EXIT.finditer(text):
                if m.group(1) != "0":
                    rest = text[m.end():]
                    at = rest.find('"output":"')
                    errors[clean_cell(f"exit {m.group(1)}: " + (rest[at + 10:at + 130] if at >= 0 else rest[:120]))] += 1
        elif kind == "message" and p.get("role") == "user" and not first:
            for c in p.get("content") or []:
                t = c.get("text", "") if isinstance(c, dict) else ""
                if t and not t.startswith("<") and "AGENTS.md" not in t[:200]:
                    first = t
                    break
    return {"tools": tools, "errors": errors, "stamps": stamps, "first": first, "cwd": cwd}


def transcripts(days: int, match: str, extra: list[str] = ()) -> list[dict]:
    """This machine's sessions, plus any other machine's saved with --json and passed in extra."""
    cutoff = time.time() - days * 86400
    out = []
    claude = Path.home() / ".claude" / "projects"
    for path in claude.glob("*/*.jsonl") if claude.exists() else []:
        if path.stat().st_mtime >= cutoff and match.lower() in path.parent.name.lower():
            out.append({"harness": "claude", "path": path, **summarize_claude(path)})
    codex = Path.home() / ".codex" / "sessions"
    for path in codex.rglob("*.jsonl") if codex.exists() else []:
        if path.stat().st_mtime >= cutoff:
            s = summarize_codex(path)
            if match.lower() in s.get("cwd", "").lower():
                out.append({"harness": "codex", "path": path, **s})
    for s in out:
        stamps = sorted(t for t in (parse_ts(x) for x in s.pop("stamps")) if t)
        s["start"] = local(stamps[0]) if stamps else ""
        # Active time: gaps over 10 minutes are a person away, not the agent working.
        gaps = [(b - a).total_seconds() for a, b in zip(stamps, stamps[1:])]
        s["minutes"] = round(sum(g for g in gaps if g <= 600) / 60)
        s["tool_calls"] = sum(s["tools"].values())
        s["error_count"] = sum(s["errors"].values())
        s["machine"] = platform.node().split(".")[0] or "this machine"
    for f in extra:
        for s in json.loads(Path(f).read_text(encoding="utf-8")):
            s.update(tools=collections.Counter(s["tools"]), errors=collections.Counter(s["errors"]))
            out.append(s)
    for s in out:  # a pasted key must not reach the report or another machine
        s["first"] = redact(clean_cell(s["first"]))[:300]
        s["errors"] = collections.Counter({redact(k): v for k, v in s["errors"].items()})
    out.sort(key=lambda s: (-s["error_count"], -s["minutes"]))
    return out


def transcripts_json(rows: list[dict]) -> str:
    return json.dumps([{**s, "path": str(s["path"]), "tools": dict(s["tools"]), "errors": dict(s["errors"])}
                       for s in rows], indent=1)


# ---------------------------------------------------------------- commands


def cmd_today(a):
    start, end = day_range(parse_day(a.date))
    print(f"{start}..{end}")


def cmd_discord(a):
    groups = prs_on_day(parse_day(a.date))
    message = discord_message(groups)
    counts = ", ".join(f"{REPO_LABEL[r]}: {len(p)}" for r, p in groups.items())
    if not message:
        print(f"No PRs opened on {parse_day(a.date)}. ({counts})")
        return 0
    if a.out:
        Path(a.out).write_text(message + "\n", encoding="utf-8")
    print(message)
    over = " OVER THE LIMIT, shorten titles or split" if len(message) >= 2000 else ""
    print(f"\n# {len(message)} characters.{over} {counts}", file=sys.stderr)
    return 0


def cmd_prs_today(a):
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    groups = prs_on_day(parse_day(a.date))
    for repo, prs in groups.items():
        for p in prs:
            facts = gh("pr", "view", str(p["number"]), "--repo", repo, "--json", VIEW_FIELDS)
            path = out / f"{SHORT[repo]}-{p['number']}.json"
            path.write_text(json.dumps(facts, indent=1), encoding="utf-8")
            print(path)
    if not any(groups.values()):
        print(f"No PRs opened on {parse_day(a.date)}.")


def cmd_checkout(a):
    items = []
    for target in a.targets:
        repo = DOCS if target.startswith("docs#") else SWARMS
        ref = target.split("#", 1)[1] if "#" in target else target
        items.append((repo, f"pr:{ref}" if ref.isdigit() else ref))
    if not items:
        for path in sorted(Path(a.run).glob("*.json")):
            short, _, n = path.stem.rpartition("-")
            if not n.isdigit() or short not in SHORT.values():
                continue
            repo = DOCS if short == SHORT[DOCS] else SWARMS
            items.append((repo, f"pr:{n}"))
    print(json.dumps(checkout(Path(a.run), items, base_too=not a.no_base), indent=1))


def cmd_cleanup(a):
    for line in cleanup(Path(a.run)):
        print(line)


def cmd_status(a):
    data = collect_status()
    out = Path(a.out) if a.out else tasks_dir() / "pr-status" / f"{dt.date.today()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"# {data.get('generated', '')}: {len(data['prs'])} open PRs -> {out}")
    for e in data["errors"]:
        print(f"ERROR {e}")
    shared: dict[str, set] = {}
    for p in data["prs"]:
        shared.setdefault(p["repo"], set(p["ci"]["failing_also_on_base"]))
        shared[p["repo"]] &= set(p["ci"]["failing_also_on_base"])
    for repo, names in shared.items():
        if names:
            print(f"{repo}: {', '.join(sorted(names))} fail on {DEFAULT_BRANCH.get(repo, 'the default branch')} too, on every PR")
    for p in data["prs"]:
        extra = sorted(set(p["ci"]["failing_also_on_base"]) - shared.get(p["repo"], set()))
        flags = p["signals"] + ([f"also failing on the base: {', '.join(extra)}"] if extra else [])
        print(f"{p['repo']}#{p['number']} [{p['hint']}{', ready' if p['ready'] else ''}] {p['title'][:70]} :: {'; '.join(flags) or 'nothing to act on'}")
    for m in data["merged_24h"]:
        print(f"merged in the last 24h: {m['pr']} {m['title'][:70]}")
    return 1 if data["errors"] and not data["prs"] else 0


def cmd_ledger(a):
    path = Path(a.ledger) if a.ledger else ledger_path()
    if a.action == "sync":
        added, updated = ledger_sync(path, dt.date.fromisoformat(a.since) if a.since else None)
        print(f"{path}: {added} rows added, {updated} updated")
    elif a.action == "add":
        rows = read_ledger(path)
        row = ledger_upsert(rows, listed=a.listed or dt.date.today().isoformat(), item=a.item, source=a.source,
                            type=a.type or pr_type(a.item or ""), est_lines=a.est, pr=a.pr, brief=a.brief,
                            state="listed" if not a.pr else None)
        write_ledger(path, rows)
        print("\t".join(row.get(c, "") for c in LEDGER_COLUMNS))
    elif a.action == "stats":
        print(ledger_stats(read_ledger(path), a.days, {"swarms": SWARMS, "docs": DOCS}.get(a.repo)))


def cmd_scan(a):
    tree, docs = Path(a.tree).resolve(), Path(a.docs).resolve() if a.docs else None
    for name, entry in scan_names(a.names, tree, docs).items():
        areas = ", ".join(f"{k} {v}" for k, v in sorted(entry["areas"].items())) or "none"
        print(f"{name}: {entry['total']} ({areas})")
        for hit in entry["hits"]:
            print(f"  {hit}")


def cmd_unused(a):
    tree, docs = Path(a.tree).resolve(), Path(a.docs).resolve() if a.docs else None
    found = find_unused([(tree / p).resolve() for p in a.paths], tree, docs)
    print(f"# {len(found)} names that nothing reads (static count over {tree.name}"
          f"{' and ' + docs.name if docs else ''}; getattr and string dispatch are invisible to it)")
    for d in found[: a.limit]:
        owner = f"{d['owner']}." if d["owner"] else ""
        notes = ", ".join(x for x in ("public" if d["public"] else "private", "decorated" if d["decorated"] else "") if x)
        print(f"{d['kind']:9} {owner}{d['name']}  {d['file']}:{d['line']}  ({d['lines']} lines, {notes})")


def cmd_competition(a):
    repo = DOCS if a.repo == "docs" else SWARMS
    rows = competition(repo, a.terms, a.removed, set(a.allow or []))
    if not rows:
        print("none")
    for r in rows:
        same = {True: "removes the same lines", False: "doesn't remove these lines", None: "diff unread"}
        tail = f", {same[r['removes_same']]}" if "removes_same" in r else ""
        print(f"#{r['number']} {r['state'].lower()} by {r['author']} (+{r['additions']}/-{r['deletions']}, "
              f"updated {r['updatedAt'][:10]}) {r['title'][:80]}{tail} <{r['url']}>")


def cmd_snapshot(a):
    dest = Path(a.dest).resolve()
    marker = dest / ".swarms-snapshot"
    if dest.exists():
        if not marker.exists():
            raise SystemExit(f"FAIL {dest} exists and isn't a snapshot; pick another --dest")
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    marker.write_text(local(now_utc()), encoding="utf-8")
    for repo in REPO_LABEL:
        target = dest / SHORT[repo]
        p = subprocess.run(["git", "clone", "--quiet", "--depth", "1", f"https://github.com/{repo}.git", str(target)],
                           capture_output=True, text=True)
        if p.returncode != 0:
            raise SystemExit(f"FAIL clone {repo}: {p.stderr.strip()}")
        print(f"{repo} {git(target, 'rev-parse', '--short', 'HEAD')} {target}")


def cmd_run(a):
    python = Path(a.python) if a.python else venv_python()
    return run_pinned(Path(a.tree), a.cmd, python, Path(a.log) if a.log else None)


def cmd_prove(a):
    python = Path(a.python) if a.python else venv_python()
    base, head = Path(a.base).resolve(), Path(a.head).resolve()
    evidence = Path(a.evidence).resolve() if a.evidence else None
    for rel in a.copy or []:
        src, dst = head / rel, base / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"copied {rel} from head into base")
    print("== base")
    base_rc = run_pinned(base, list(a.cmd), python, evidence / "base.log" if evidence else None)
    print("== head")
    head_rc = run_pinned(head, list(a.cmd), python, evidence / "head.log" if evidence else None)
    if base_rc != 0 and head_rc == 0:
        print(f"PROOF red on base (exit {base_rc}), green on head")
        return 0
    print(f"NOT PROVEN base exit {base_rc}, head exit {head_rc}")
    return 1


def cmd_doctor(a):
    fails = 0

    def say(status, text):
        nonlocal fails
        fails += status == "FAIL"
        print(f"{status} {text}")

    try:
        login = gh("api", "user", "--jq", ".login", json_out=False).strip()
        say("PASS" if login == USER else "FAIL", f"gh logged in as {login}")
        limits = gh("api", "rate_limit")["resources"]
        for name in ("core", "graphql"):
            left = limits[name]["remaining"]
            say("PASS" if left > 200 else "WARN", f"gh {name} rate limit: {left} left")
    except GhError as e:
        say("FAIL", f"gh: {e}")
    for repo in REPO_LABEL:
        clone = clone_for(repo)
        if not clone.exists():
            say("FAIL", f"{repo}: no clone at {clone} (set {'SWARMS_REPO' if repo == SWARMS else 'SWARMS_DOCS_REPO'})")
            continue
        remotes = read_remotes(clone)
        up = [n for n, u in remotes.items() if repo.lower() in u.lower() and USER.lower() not in u.lower()]
        say("PASS" if up else "FAIL", f"{repo}: clone {clone}, remotes {', '.join(f'{n}={redact(u)}' for n, u in remotes.items())}")
    py = venv_python()
    if py.exists():
        p = subprocess.run([str(py), "--version"], capture_output=True, text=True)
        say("PASS", f"venv {py} ({(p.stdout or p.stderr).strip()}); CI runs 3.10 to 3.12")
    else:
        say("FAIL", f"no venv python at {py}")
    t = tasks_dir()
    say("PASS" if t.exists() and os.access(t, os.W_OK) else "FAIL", f"tasks folder {t}")
    say("PASS" if ledger_path().exists() else "WARN", f"ledger {ledger_path()}")
    say("PASS" if shutil.which("npx") else "WARN", "npx for the docs checks (mint)")
    say("PASS" if (SKILLS_DIR / "unslop" / "SKILL.md").exists() else "WARN", "unslop installed next to swarms-tools")
    return 1 if fails else 0


def cmd_publish(a):
    task = Path(a.task).resolve()
    if a.action == "init":
        if (task / "publish.json").exists():
            raise SystemExit(f"FAIL {task}/publish.json exists already")
        task.mkdir(parents=True, exist_ok=True)
        prs = []
        for repo, branch in ((SWARMS, a.branch), (DOCS, a.docs_branch)):
            if not branch:
                continue
            fork = f"{USER}/{repo.split('/')[1]}"
            sha = gh("api", f"repos/{fork}/git/ref/heads/{branch}", "--jq", ".object.sha", json_out=False).strip()
            pid = "framework" if repo == SWARMS else "docs"
            prs.append({"id": pid, "repo": repo, "head": f"{USER}:{branch}", "sha": sha,
                        "title": "pr_title.txt" if pid == "framework" else "docs_title.txt",
                        "body": "pr_body.md" if pid == "framework" else "docs_body.md",
                        "relabel_body": "pr_body_relabel.md" if pid == "framework" else None,
                        "competition": {"terms": [], "removed": None, "allow": []}})
        manifest = {"item": a.item or "", "brief": a.brief or "", "source": a.source or "", "est_lines": a.est or "",
                    "security": False, "prs": prs}
        (task / "publish.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {task / 'publish.json'}; fill in competition terms, then write the text files it names")
        return 0
    m = load_manifest(task)
    if a.action == "approve":
        missing = [f for f in approved_files(m) if not (task / f).exists()]
        if missing:
            raise SystemExit(f"FAIL missing {', '.join(missing)}")
        lines = [f"{sha256(task / f)}  {f}" for f in approved_files(m)]
        (task / "approved.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 0
    lines = publish_checks(task, m, a.on)
    print("\n".join(lines), flush=True)
    if any(line.startswith("FAIL") for line in lines):
        print("RESULT checks failed, nothing posted")
        return 1
    if a.action == "check":
        print("RESULT checks passed, nothing posted (check only)")
        return 0
    return publish_post(task, m, a.label_wait)


def cmd_lint(a):
    total = 0
    for name in a.files:
        text = sys.stdin.read() if name == "-" else Path(name).read_text(encoding="utf-8")
        found = lint_text(text, discord=a.discord)
        for line, msg in found:
            print(f"{name}:{line}: {msg}")
        total += len(found)
        if a.discord:
            print(f"{name}: {len(text)} characters")
    return 1 if total else 0


def cmd_transcripts(a):
    rows = transcripts(a.days, a.match, a.add or [])
    if a.json:
        data = transcripts_json(rows[: a.limit])
        if a.json == "-":
            print(data)
        else:
            Path(a.json).write_text(data, encoding="utf-8")
            print(f"wrote {min(len(rows), a.limit)} sessions to {a.json}")
        return
    machines = sorted({s["machine"] for s in rows})
    print(f"# {len(rows)} sessions in the last {a.days} days whose project matches '{a.match}', "
          f"from {', '.join(machines) or 'no machine'}, worst first")
    for s in rows[: a.limit]:
        top = ", ".join(f"{k} {v}" for k, v in s["tools"].most_common(4))
        print(f"\n{s['machine']} {s['harness']} {s['start']} {s['minutes']} active min, "
              f"{s['tool_calls']} tool calls, {s['error_count']} errors")
        print(f"  {s['path']}")
        print(f"  asked: {clean_cell(s['first'])[:160]}")
        print(f"  tools: {top}")
        for text, n in s["errors"].most_common(3):
            print(f"  error x{n}: {text}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="swarms.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("today", help="print the local-midnight range gh search needs")
    p.add_argument("--date", help="today, yesterday or YYYY-MM-DD")
    p.set_defaults(func=cmd_today)

    p = sub.add_parser("discord", help="the Discord list of PRs opened on a day")
    p.add_argument("--date")
    p.add_argument("--out")
    p.set_defaults(func=cmd_discord)

    p = sub.add_parser("prs-today", help="save facts JSON for each PR opened on a day")
    p.add_argument("--date")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_prs_today)

    p = sub.add_parser("checkout", help="detached worktrees for PR heads and merge bases, under --run")
    p.add_argument("--run", required=True)
    p.add_argument("--no-base", action="store_true")
    p.add_argument("targets", nargs="*", help="3166, docs#400, master or a SHA; default: every facts JSON in --run")
    p.set_defaults(func=cmd_checkout)

    p = sub.add_parser("cleanup", help="remove every worktree under --run, then the folder")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_cleanup)

    p = sub.add_parser("status", help="facts, signals and a verdict hint for every open PR")
    p.add_argument("--out")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("ledger", help="the outcomes ledger: sync, add or stats")
    p.add_argument("action", choices=["sync", "add", "stats"])
    p.add_argument("--ledger")
    p.add_argument("--since", help="sync: first day to include (backfill)")
    p.add_argument("--days", type=int, help="stats: only rows listed in the last N days")
    p.add_argument("--repo", choices=["swarms", "docs", "all"], default="swarms")
    for flag in ("--item", "--source", "--type", "--est", "--pr", "--brief", "--listed"):
        p.add_argument(flag)
    p.set_defaults(func=cmd_ledger)

    p = sub.add_parser("scan", help="where identifiers appear: swarms, tests, examples, docs")
    p.add_argument("names", nargs="+")
    p.add_argument("--tree", required=True)
    p.add_argument("--docs")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("unused", help="functions, classes, methods, constants and attributes that nothing reads")
    p.add_argument("paths", nargs="+", help="paths inside --tree, such as swarms/structs")
    p.add_argument("--tree", required=True)
    p.add_argument("--docs")
    p.add_argument("--limit", type=int, default=60)
    p.set_defaults(func=cmd_unused)

    p = sub.add_parser("competition", help="PRs that mention these terms, and whether they remove the same lines")
    p.add_argument("terms", nargs="+")
    p.add_argument("--repo", choices=["swarms", "docs"], default="swarms")
    p.add_argument("--removed", help="regex for lines your PR removes")
    p.add_argument("--allow", type=int, nargs="*")
    p.set_defaults(func=cmd_competition)

    p = sub.add_parser("snapshot", help="fresh shallow clones of both repos' default branches")
    p.add_argument("--dest", required=True)
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("run", help="run a command against a tree with the pinned offline environment")
    p.add_argument("--tree", required=True)
    p.add_argument("--python")
    p.add_argument("--log")
    p.add_argument("cmd", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("prove", help="run one command on base and head; proof is red on base, green on head")
    p.add_argument("--base", required=True)
    p.add_argument("--head", required=True)
    p.add_argument("--copy", nargs="*", help="files to copy from head into base first, such as the new test")
    p.add_argument("--evidence")
    p.add_argument("--python")
    p.add_argument("cmd", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_prove)

    p = sub.add_parser("doctor", help="read-only checks: gh, clones, venv, tasks folder")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("publish", help="init, approve, check or post a task folder's PRs")
    p.add_argument("action", choices=["init", "approve", "check", "post"])
    p.add_argument("task")
    p.add_argument("--on", help="post only on this date (YYYY-MM-DD)")
    p.add_argument("--label-wait", type=int, default=120)
    p.add_argument("--branch")
    p.add_argument("--docs-branch")
    for flag in ("--item", "--brief", "--source", "--est"):
        p.add_argument(flag)
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("lint", help="em dashes, curly quotes, unslop vocabulary; --discord adds the 2,000 limit")
    p.add_argument("files", nargs="+", help="files, or - for stdin")
    p.add_argument("--discord", action="store_true")
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser("transcripts", help="Claude and Codex sessions from the last N days, worst first")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--match", default="swarms")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--json", metavar="FILE", help="save the sessions as JSON for another machine's --add; - prints it")
    p.add_argument("--add", nargs="+", metavar="FILE", help="sessions another machine saved with --json")
    p.set_defaults(func=cmd_transcripts)

    return parser


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    if getattr(a, "cmd", None) and a.cmd[:1] == ["--"]:
        a.cmd = a.cmd[1:]
    try:
        return a.func(a) or 0
    except GhError as e:
        print(f"FAIL gh: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    for stream in (sys.stdin, sys.stdout):  # Windows defaults to its code page
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
