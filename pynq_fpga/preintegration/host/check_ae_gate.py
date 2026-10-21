"""Refuse task 7/8 production integration until all A-E handoffs pass."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


TASKS = "ABCDE"
PASS_RE = re.compile(r"(?im)^\s*(?:status|状态|结论)\s*[:：]\s*PASS\b")
SKIP_RE = re.compile(r"(?i)(?:safety|安全关键)[^\r\n]{0,40}\bSKIP\b")


def inspect_handoffs(nightly: Path) -> list[str]:
    errors: list[str] = []
    for task in TASKS:
        matches = sorted(nightly.glob(f"night_20260918_{task}.md"))
        if len(matches) != 1:
            errors.append(f"{task}: expected one handoff, found {len(matches)}")
            continue
        text = matches[0].read_text(encoding="utf-8")
        if not PASS_RE.search(text):
            # Keep console output ASCII so Windows PowerShell 5 does not
            # corrupt the gate reason even when its active code page is not UTF-8.
            errors.append(f"{task}: no explicit PASS status")
        if SKIP_RE.search(text):
            errors.append(f"{task}: safety-critical SKIP present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("nightly", type=Path)
    args = parser.parse_args()
    errors = inspect_handoffs(args.nightly)
    if errors:
        print("AE_INTEGRATION_GATE_BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("AE_INTEGRATION_GATE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
