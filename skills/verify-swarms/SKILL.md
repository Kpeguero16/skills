---
name: verify-swarms
description: How to run swarms code offline and prove a change, red on the base and green on the branch, for kyegomez/swarms and swarms-framework-docs. Use when you need to run swarms, prove a fix or a deletion, check someone's PR, or the user says "verify".
---

# Verify swarms

Proof for a swarms change is a check you ran in this session that fails on the base and passes on the branch. For a deletion it's the search that shows nothing uses the code, plus the module's tests giving the same results before and after. Reading the diff isn't proof.

`$T` below is `../swarms-tools/scripts/swarms.py`, next to this skill's folder. Use `py -3` for `python3` on Windows.

## Launch

swarms is a library, so launching means trees to run against and a pinned environment.

1. `python3 $T doctor`. Fix any `FAIL` first.
2. Make an empty run folder outside every clone, such as `run=$(python3 -c "import os, tempfile; print(os.path.realpath(tempfile.mkdtemp()))")`. It works on Windows too, with `python` and your shell's syntax.
3. Make the trees:
   - Someone's PR: `python3 $T checkout --run "$run" 3166` gives `wt-swarms-3166` at the PR head and `base-swarms-3166` at its merge base. Use `docs#400` for a docs PR.
   - Your own branch in a T3 worktree: that worktree is the head. `python3 $T checkout --run "$run" --no-base master` gives the base.
4. The venv in the swarms clone has master's dependencies. If the change edits `pyproject.toml` or the requirements, make a venv under `$run`, install into it, and pass its python with `--python`. Otherwise say the run used the old versions.
5. The venv is Python 3.14 and CI runs 3.10 to 3.12. Say so when the behavior could depend on the version.

## Doctor

`python3 $T run --tree <tree> -- python -c "import swarms"` prints `swarms from <path>`, and the path must be inside the tree. The main clone's venv has an editable install, so without the pinned `PYTHONPATH` every run tests the main clone instead. `run` and `prove` refuse to continue when this happens.

`run` also sets `SWARMS_TELEMETRY_ON=false` (telemetry is on when it's unset), blanks every `*_API_KEY`, and turns off `.env` loading. Never import swarms any other way.

## Drive

- Tests: `python3 $T run --tree <tree> --log <file> -- pytest tests/<path> -q -p no:cacheprovider`.
- A repro script lives outside the tree, in `$run/scratch/`: `-- python $run/scratch/repro.py`.
- Red and green in one step:

  ```bash
  python3 $T prove --base <base tree> --head <head tree> --copy tests/<new test> \
    --evidence <dir> -- pytest tests/<new test> -q -p no:cacheprovider
  ```

  `--copy` puts the branch's new or changed test into the base tree first. `PROOF` means it failed on the base and passed on the head. `NOT PROVEN` means it didn't, and the PR isn't proven.
- A deletion: `python3 $T scan <name> --tree <base tree> --docs <docs tree>` lists every mention in swarms, tests, examples and the docs. Then run the module's tests on both trees and compare the pass and fail sets. They must match, and some tests already fail on master. "No internal callers" isn't enough for public API with docs and tests: Kye kept `Agent.run_batched` for that reason.
- Format and lint the changed files: `-- black --check --line-length 70 <files>` and `-- ruff check <files>`.
- Stay offline. Mock the model or use recorded responses. When only a live model call could prove something, say what's unproven.

### Docs

- In the docs tree: `npx -y mint@4.2.970 validate` and `npx -y mint@4.2.970 broken-links`. `validate` sometimes fails with ENOENT on a `src/_props/...` file while another mint run is going; rerun it before calling it a failure.
- The proof is that the page matches the code. Read the source it documents in a swarms tree at `upstream/master`, and run the page's examples through `run` with the model mocked. A docs PR's red on the base is the old page's claims failing against the new code.

### CI on a PR

A failing job counts against a PR only when the same job passes on master. `python3 $T status` compares job names. To compare the tests inside a job, take the PR job's log and the same job's latest master run (`gh run list --repo kyegomez/swarms --workflow <name> --branch master`, then `gh api repos/kyegomez/swarms/actions/jobs/<id>/logs`), and diff the sorted FAILED and ERROR lines. When a job fails before any test runs (lint, build, install), compare the error itself.

## Evidence

For each claim, keep the command, the tree it ran in, the `swarms from` line and the result. `--log` and `--evidence` save all four. Keep a PR's evidence in its task folder, `tasks/<slug>/evidence/`, so cleanup can't delete it. Report numbers ("tests/tools: 177 passed, 4 failed, the same tests as on master"), never "tests pass".

## Cleanup

`python3 $T cleanup --run "$run"` removes every worktree under the run folder, then the folder. Run it after a failure too, and check that it printed no `still listed` line. It never touches other worktrees, stale ones included, because other sessions own them.
