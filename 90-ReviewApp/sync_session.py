#!/usr/bin/env python3
"""
同步用户导出的 session JSON 回 Obsidian 笔记（SM-2）。

用法：
  python3 sync_session.py                          # 同步 sync/ 里最新的 session_*.json
  python3 sync_session.py --file path/to/session.json   # 指定文件
  python3 sync_session.py --dry-run                # 只打印将要做的修改，不写任何文件

对每条结果：
  1. 读取 path 指向的 .md（相对 vault 根）
  2. 用结果里的 score 走一遍 SM-2（compute_next，与 review.py 一比一）
  3. 写回 frontmatter：mastery / interval / ease / due / reviews(+1) / last-review
  4. 正文不动，只重写 frontmatter 块
同时推进 progress.json：cursor_index += 新引入的词数，标记对应 history 条目已同步。
挖空题对错（results[].cloze，若存在）单独统计，不影响 SM-2，记入 progress.json 的 history 条目。
"""

import os
import sys
import json
import glob
import argparse
from datetime import date, timedelta

import frontmatter

APP_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT = os.path.dirname(APP_DIR)          # Brain/（vault 根）
SYNC_DIR = os.path.join(APP_DIR, "sync")
PROGRESS_PATH = os.path.join(APP_DIR, "progress.json")

# 复用 review.py 的 SM-2 公式，保证两边一致
sys.path.insert(0, VAULT)
from review import compute_next  # noqa: E402


def latest_session():
    files = sorted(glob.glob(os.path.join(SYNC_DIR, "session_*.json")))
    return files[-1] if files else None


def load_progress():
    if not os.path.exists(PROGRESS_PATH):
        return {"history": [], "cursor_index": 0}
    with open(PROGRESS_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_progress(progress):
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser(description="同步 session JSON 回 Obsidian（SM-2）")
    ap.add_argument("--file", help="session 文件路径（默认 sync/ 里最新的）")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    args = ap.parse_args()

    path = args.file or latest_session()
    if not path:
        print("✗ 未找到 session 文件（sync/session_*.json）")
        return
    with open(path, encoding="utf-8") as f:
        session = json.load(f)
    study_date = session.get("date", str(date.today()))
    try:
        ref_date = date.fromisoformat(study_date)
    except ValueError:
        ref_date = date.today()

    results = session.get("results", [])
    print(f"同步文件：{os.path.basename(path)}  日期={study_date}  共 {len(results)} 条\n")

    progress = load_progress()
    new_count = 0
    new_words_synced = []
    review_words = []
    cloze_ok = 0
    cloze_try = 0
    updated = 0
    skipped = 0

    # 计算全字母序位置表：word -> S-位置（游标按此推进；S-位置与是否已同步无关，跨天稳定）
    from build_review import load_words
    s_pos = {w["word"]: i for i, w in enumerate(sorted(load_words(), key=lambda x: x["word"].lower()))}

    for r in results:
        rel = r.get("path", "")
        full = os.path.join(VAULT, rel)
        score = int(r.get("score", 3))
        mastery = r.get("mastery", {1: "again", 2: "hard", 3: "good", 4: "easy", 5: "perfect"}.get(score, "good"))
        if not os.path.exists(full):
            print(f"  ✗ 跳过（文件不存在）：{rel}")
            skipped += 1
            continue

        post = frontmatter.load(full)
        # 幂等保护：该词当天的 last-review 已等于 session 日期 → 说明已同步过，跳过
        if post.get("last-review") == ref_date.isoformat():
            print(f"  ⏭ 跳过（{rel} 当天已同步过）：{r['word']}")
            skipped += 1
            continue
        old_interval = float(post.get("interval", 1) or 1)
        old_ease = float(post.get("ease", 2.5) or 2.5)
        old_reviews = int(post.get("reviews", 0) or 0)
        was_new = (post.get("mastery") == "new" or old_reviews == 0)

        new_interval, new_ease = compute_next(old_interval, old_ease, score)
        new_due = ref_date + timedelta(days=new_interval)
        new_reviews = old_reviews + 1

        if not args.dry_run:
            post["mastery"] = mastery
            post["interval"] = new_interval
            post["ease"] = new_ease
            post["due"] = new_due.isoformat()
            post["reviews"] = new_reviews
            post["last-review"] = ref_date.isoformat()
            with open(full, "w", encoding="utf-8") as f:
                frontmatter.dump(post, f)

        if was_new:
            new_count += 1
            new_words_synced.append(r["word"])
        else:
            review_words.append(r["word"])
        tag = "🆕新" if was_new else "🔁复习"
        print(f"  {tag} {r['word']:14s} score={score} {mastery:7s} "
              f"interval {old_interval:>4}→{new_interval:>4}  ease {old_ease:.2f}→{new_ease:.2f}  "
              f"due {new_due}  reviews {old_reviews}→{new_reviews}")
        updated += 1

        # 挖空题单独统计（旧 HTML 导出的没有此字段）
        cloze = r.get("cloze")
        if cloze and cloze.get("triggered"):
            cloze_try += 1
            if cloze.get("correct"):
                cloze_ok += 1

    # —— 推进 progress.json ——
    if not args.dry_run:
        old_cursor = int(progress.get("cursor_index", 0))
        if new_words_synced:
            poss = [s_pos.get(w) for w in new_words_synced]
            poss = [p for p in poss if p is not None]
            if poss:
                cursor = max(poss) + 1  # 本次消耗的最大 S-位置 +1，跨天稳定
            else:
                cursor = old_cursor
        else:
            cursor = old_cursor
        progress["cursor_index"] = cursor
        progress["last_session_date"] = study_date
        progress["last_synced_date"] = study_date
        progress["cursor_note"] = (
            f"已引入的新词累计到第 {cursor} 个（下标 0-{cursor - 1} 已用），"
            f"下次从下标 {cursor} 开始取下 25 个"
        )

        # 标记/新增 history 条目
        review_ids = sorted(set(review_words))
        new_words_count = new_count
        review_words_count = len(review_words)
        matched = [
            h for h in progress["history"]
            if (h.get("date") == study_date)
            or (h.get("new_words_count") == new_words_count and h.get("synced") is False)
        ]
        if matched:
            h = matched[0]
            h["synced"] = True
            h["synced_on"] = study_date
            h.setdefault("cloze", {})
            h["cloze"]["attempted"] = cloze_try
            h["cloze"]["correct"] = cloze_ok
        else:
            progress["history"].append({
                "date": study_date,
                "new_words_count": new_words_count,
                "review_words_count": review_words_count,
                "review_word_ids": review_ids,
                "synced": True,
                "cloze": {"attempted": cloze_try, "correct": cloze_ok},
            })
        save_progress(progress)

    print(f"\n共更新 {updated} 条，跳过 {skipped} 条；本次引入新词 {new_count} 个。"
          f"挖空题：{cloze_ok}/{cloze_try} 答对")
    if not args.dry_run:
        print(f"progress.json：cursor_index {old_cursor} → {progress['cursor_index']}"
              f"，last_synced_date = {study_date}")


if __name__ == "__main__":
    main()
