#!/usr/bin/env python3
"""
整理 sync/ 目录：把散落在顶层的 day_*.json / session_*.json 归档进"月份/周"文件夹。

用法：
  python3 organize_sync.py              # 正常归档
  python3 organize_sync.py --dry-run    # 只打印将要移动的文件，不实际移动

归档规则：
  - 月份文件夹：按文件日期，如 2026-08/
  - 周文件夹：按月内周数编号（1-7号=第1周, 8-14=第2周, 15-21=第3周,
    22-28=第4周, 29号以后=第5周），如 第1周/
  - cloze_cache.json 保留在顶层（build_review.py 固定读 sync/cloze_cache.json）
  - 移动完成后清理空文件夹

注意：build_review.py / sync_session.py 仍会在 sync/ 顶层写新文件，
此脚本只负责归档，不改变脚本行为。可定期运行。
"""

import os
import re
import glob
import shutil
import argparse
from datetime import date

SYNC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sync")
PATTERN = re.compile(r"^(day|session)_(\d{4}-\d{2}-\d{2})\.json$")


def week_of_month(day: int) -> str:
    """按月内周数编号：1-7号=第1周, 8-14=第2周, ... 29号以后=第5周。"""
    return f"第{(day - 1) // 7 + 1}周"


def main():
    ap = argparse.ArgumentParser(description="整理 sync/ 目录，归档到 月份/周 文件夹")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不移动文件")
    args = ap.parse_args()

    # 1. 收集所有散落的 day/session 文件（顶层 + 已归档的子目录都找）
    moved = []
    for path in sorted(glob.glob(os.path.join(SYNC_DIR, "**", "*.json"), recursive=True)):
        name = os.path.basename(path)
        m = PATTERN.match(name)
        if not m:
            continue  # cloze_cache.json 等非 day/session 文件不动
        dt = date.fromisoformat(m.group(2))
        dest_dir = os.path.join(SYNC_DIR, dt.strftime("%Y-%m"), week_of_month(dt.day))
        dest = os.path.join(dest_dir, name)
        if os.path.abspath(path) == os.path.abspath(dest):
            continue  # 已在正确位置
        moved.append((path, dest))

    if not moved:
        print("sync/ 无需整理（没有散落的 day/session 文件）")
        return

    if args.dry_run:
        print(f"[dry-run] 将移动 {len(moved)} 个文件：")
        for src, dst in moved:
            print(f"  {os.path.relpath(src, SYNC_DIR)}  →  {os.path.relpath(dst, SYNC_DIR)}")
        return

    # 2. 移动
    for src, dst in moved:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)

    # 3. 清理移动后留下的空文件夹
    removed = []
    for root, dirs, files in os.walk(SYNC_DIR, topdown=False):
        if root == SYNC_DIR:
            continue
        if not os.listdir(root):
            removed.append(os.path.relpath(root, SYNC_DIR))
            os.rmdir(root)

    print(f"已归档 {len(moved)} 个文件：")
    for src, dst in moved:
        print(f"  {os.path.relpath(dst, SYNC_DIR)}")
    if removed:
        print(f"已清理空文件夹: {removed}")


if __name__ == "__main__":
    main()
