#!/usr/bin/env python3
"""Template for swarms-picks source i): find a bug by running a pure function on generated inputs.

Copy this file out of the skills folder, fill in the two marked functions, and run the copy from
outside the tree, through the pinned offline environment:

    python3 swarms.py run --tree <snapshot>/swarms -- python <copy> [seed] [seconds]

A finding prints the shortest input that broke the promise, so it replays as one line. The exit code
is 1 when anything was found, which lets swarms.py prove use the same file: red on master, green on
the fix. Standard library only, and no model calls.
"""
import json
import random
import sys
import time


def case(rng: random.Random) -> tuple[str, object]:
    """FILL IN. Return (label, input) for one generated case. The label groups findings by shape."""
    value = {rng.choice("abc"): rng.choice([1, "x", None, [rng.random()]]) for _ in range(rng.randint(0, 3))}
    return "object", value


def broken(value: object) -> str | None:
    """FILL IN. Call the function under test. Return None when the promise in its docstring holds,
    or one line saying what it returned instead. An exception counts as broken too."""
    back = json.loads(json.dumps(value))
    return None if back == value else f"came back as {back!r}"


def main() -> int:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0
    rng = random.Random(seed)
    found: dict[str, tuple[int, str, str]] = {}
    cases, stop = 0, time.time() + seconds
    while time.time() < stop:
        label, value = case(rng)
        cases += 1
        try:
            reason = broken(value)
        except Exception as e:
            reason = f"raised {type(e).__name__}: {str(e)[:120]}"
        if reason:
            count, text, why = found.get(label, (0, None, ""))
            if text is None or len(repr(value)) < len(text):
                text, why = repr(value), reason
            found[label] = (count + 1, text, why)
    for label, (count, text, reason) in sorted(found.items()):
        print(f"FOUND [{label}] broke {count} times. Shortest input:\n  {text}\n  {reason}")
    print(f"{'FAIL' if found else 'PASS'} {len(found)} kinds of input broke the promise in {cases} cases, seed {seed}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
