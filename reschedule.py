#!/usr/bin/env python3
"""
Reschedule all mastery:new notes by spreading their due dates evenly,
starting from tomorrow, with a configurable daily batch size.

Usage:
    python reschedule.py --daily 20    # 20 words per day (default)
    python reschedule.py --daily 15    # 15 words per day
"""

import argparse
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TARGET_DIRS = ["10-Words", "20-Concepts"]


def find_new_files(base: Path, dirs: list[str]) -> list[Path]:
    """Find all .md files with mastery: new in frontmatter, sorted by filename."""
    results = []
    for d in dirs:
        target = base / d
        if not target.is_dir():
            continue
        for f in sorted(target.glob("*.md"), key=lambda p: p.name):
            try:
                content = f.read_text(encoding="utf-8")
            except Exception:
                continue

            # Only check frontmatter (between first two --- lines)
            if not content.startswith("---"):
                continue
            second_sep = content.find("---", 3)
            if second_sep == -1:
                continue
            frontmatter = content[3:second_sep]

            # Check for mastery: new (exact match, ignoring surrounding whitespace)
            if re.search(r"^mastery:\s*new\s*$", frontmatter, re.MULTILINE):
                results.append(f)

    return results


def update_due(filepath: Path, new_due: date) -> bool:
    """Replace the due field in frontmatter with new_due. Returns True on success."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception:
        return False

    if not content.startswith("---"):
        return False

    second_sep = content.find("---", 3)
    if second_sep == -1:
        return False

    before = content[:3]
    frontmatter = content[3:second_sep]
    after = content[second_sep:]

    new_frontmatter, count = re.subn(
        r"^due:.*$",
        f"due: '{new_due.isoformat()}'",
        frontmatter,
        flags=re.MULTILINE,
    )

    if count == 0:
        # No due field found — insert one after mastery line
        new_frontmatter, count = re.subn(
            r"^(mastery:\s*new\s*)$",
            rf"\1\ndue: '{new_due.isoformat()}'",
            frontmatter,
            flags=re.MULTILINE,
        )

    if count == 0:
        return False

    new_content = before + new_frontmatter + after
    try:
        filepath.write_text(new_content, encoding="utf-8")
        return True
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Reschedule mastery:new notes with spread due dates"
    )
    parser.add_argument(
        "--daily",
        type=int,
        default=20,
        help="Number of words to schedule per day (default: 20)",
    )
    args = parser.parse_args()
    daily = args.daily

    if daily < 1:
        print("错误：--daily 必须 >= 1")
        return 1

    files = find_new_files(SCRIPT_DIR, TARGET_DIRS)

    if not files:
        print("没有找到 mastery: new 的笔记。")
        return 0

    today = date.today()
    updated = 0

    for i, filepath in enumerate(files):
        batch = i // daily
        new_due = today + timedelta(days=batch + 1)  # +1 = start from tomorrow
        if update_due(filepath, new_due):
            updated += 1

    # Calculate last batch's due date
    last_batch = (len(files) - 1) // daily if files else 0
    last_due = today + timedelta(days=last_batch + 1)

    print(
        f"共处理 {updated} 个词，每天 {daily} 个，"
        f"最后一批 due = {last_due.isoformat()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
