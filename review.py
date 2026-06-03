#!/usr/bin/env python3
"""
Obsidian Brain 复习脚本
用法：
  python review.py start              # 开始今日复习
  python review.py import words.txt   # 批量导入单词（每行一个）
  python review.py stats              # 查看掌握度统计
  python review.py add <word>         # 快速添加单个单词
"""

import sys
import os
import glob
from datetime import date, timedelta
import frontmatter

# ── 配置 ──────────────────────────────────────────────
VAULT = os.path.dirname(os.path.abspath(__file__))
WORDS_DIR = os.path.join(VAULT, "10-Words")
CONCEPTS_DIR = os.path.join(VAULT, "20-Concepts")
# ─────────────────────────────────────────────────────

# mastery 字符串 → SM-2 评分映射
MASTERY_TO_SCORE = {
    "again": 1,
    "hard": 2,
    "good": 3,
    "easy": 4,
    "perfect": 5,
}

SCORE_TO_MASTERY = {v: k for k, v in MASTERY_TO_SCORE.items()}

def compute_next(interval: float, ease: float, score: int):
    """简化 SM-2：返回 (next_interval, next_ease)"""
    if score <= 1:  # again
        next_interval = 1
        next_ease = max(1.3, ease - 0.2)
    elif score == 2:  # hard
        next_interval = max(1, round(interval * 1.2))
        next_ease = max(1.3, ease - 0.15)
    elif score == 3:  # good
        next_interval = max(1, round(interval * ease))
        next_ease = ease
    elif score == 4:  # easy
        next_interval = max(1, round(interval * ease * 1.3))
        next_ease = ease + 0.1
    else:  # perfect
        next_interval = max(1, round(interval * ease * 1.5))
        next_ease = ease + 0.15
    return next_interval, round(next_ease, 2)


def load_due_notes():
    """加载所有 due <= 今天 的笔记，按 interval 升序"""
    today = date.today()
    notes = []
    for folder in [WORDS_DIR, CONCEPTS_DIR]:
        for path in glob.glob(os.path.join(folder, "*.md")):
            post = frontmatter.load(path)
            due_str = post.get("due", "")
            if not due_str:
                continue
            try:
                due = date.fromisoformat(str(due_str))
            except ValueError:
                continue
            if due <= today:
                notes.append((path, post))
    notes.sort(key=lambda x: x[1].get("interval", 1))
    return notes


def review_note(path, post):
    """交互式复习单条笔记，返回是否继续"""
    note_type = post.get("type", "word")
    title = os.path.splitext(os.path.basename(path))[0]

    print("\n" + "─" * 50)

    if note_type == "word":
        # 闪卡模式：显示单词，让用户回答
        print(f"📖 单词：{post.get('word', title)}")
        phonetic = post.get("phonetic", "")
        if phonetic:
            print(f"   音标：{phonetic}")
        input("   按 Enter 显示答案...")
        answer = post.get("answer") or post.get("meaning", "（未填写）")
        example = post.get("example", "")
        print(f"   释义：{answer}")
        if example:
            print(f"   例句：{example}")
    else:
        # 开放模式：显示概念名，用户自由描述后自评
        print(f"🧠 概念：{title}")
        input("   请在脑中描述这个概念，准备好后按 Enter...")
        answer = post.get("answer", "（未填写标准答案）")
        print(f"   参考答案：{answer}")

    print()
    print("  评分：again(a) / hard(h) / good(g) / easy(e) / perfect(p) / 跳过(s) / 退出(q)")

    while True:
        choice = input("  你的评分：").strip().lower()
        if choice in ("q", "quit"):
            return False
        if choice in ("s", "skip"):
            return True
        rating_map = {"a": "again", "h": "hard", "g": "good", "e": "easy", "p": "perfect"}
        if choice in rating_map:
            mastery = rating_map[choice]
            break
        # 也接受全名
        if choice in MASTERY_TO_SCORE:
            mastery = choice
            break
        print("  请输入有效选项")

    # 计算下次间隔
    score = MASTERY_TO_SCORE[mastery]
    interval = float(post.get("interval", 1))
    ease = float(post.get("ease", 2.5))
    next_interval, next_ease = compute_next(interval, ease, score)
    next_due = date.today() + timedelta(days=next_interval)

    # 更新 frontmatter
    post["mastery"] = mastery
    post["interval"] = next_interval
    post["ease"] = next_ease
    post["due"] = str(next_due)
    post["last-review"] = str(date.today())
    post["reviews"] = int(post.get("reviews", 0)) + 1

    with open(path, "w", encoding="utf-8") as f:
        frontmatter.dump(post, f)

    print(f"  ✓ 已记录：{mastery}，下次复习 {next_due}（{next_interval}天后）")
    return True


def cmd_start():
    """开始今日复习"""
    notes = load_due_notes()
    if not notes:
        print("✅ 今日无待复习笔记！")
        return

    print(f"📚 今日待复习：{len(notes)} 条")
    reviewed = 0
    for path, post in notes:
        if not review_note(path, post):
            break
        reviewed += 1

    print(f"\n📊 本次复习完成：{reviewed}/{len(notes)} 条")


def cmd_import(filepath):
    """批量导入单词文件（每行一个单词）"""
    if not os.path.exists(filepath):
        print(f"文件不存在：{filepath}")
        return

    with open(filepath, encoding="utf-8") as f:
        words = [line.strip() for line in f if line.strip()]

    today = str(date.today())
    created = 0
    skipped = 0

    for word in words:
        filename = word.lower().replace(" ", "-") + ".md"
        path = os.path.join(WORDS_DIR, filename)
        if os.path.exists(path):
            skipped += 1
            continue

        post = frontmatter.Post(
            f"## {word}\n\n**音标**：\n\n**释义**：\n\n**例句**：\n\n**联想/记忆**：",
            type="word",
            tags=["英语"],
            mastery="new",
            due=today,
            interval=1,
            ease=2.5,
            reviews=0,
            word=word,
            phonetic="",
            meaning="",
            example="",
            answer="",
        )
        post["last-review"] = ""
        with open(path, "w", encoding="utf-8") as f:
            frontmatter.dump(post, f)
        created += 1

    print(f"✓ 导入完成：新建 {created} 条，跳过已有 {skipped} 条")


def cmd_stats():
    """显示掌握度统计"""
    all_notes = []
    for folder in [WORDS_DIR, CONCEPTS_DIR]:
        for path in glob.glob(os.path.join(folder, "*.md")):
            post = frontmatter.load(path)
            all_notes.append(post)

    if not all_notes:
        print("vault 中暂无笔记")
        return

    states = ["new", "again", "hard", "good", "easy", "perfect"]
    emoji = {"new": "🆕", "again": "❌", "hard": "😬", "good": "👍", "easy": "😊", "perfect": "⭐"}
    print(f"\n📊 掌握度统计（共 {len(all_notes)} 条）\n")
    for s in states:
        count = sum(1 for p in all_notes if p.get("mastery") == s)
        bar = "█" * count
        print(f"  {emoji[s]} {s:8s} {count:3d}  {bar}")

    today = date.today()
    due_count = sum(
        1 for p in all_notes
        if p.get("due") and date.fromisoformat(str(p["due"])) <= today
    )
    print(f"\n  📅 今日待复习：{due_count} 条")


def cmd_add(word):
    """快速添加单个单词"""
    filename = word.lower().replace(" ", "-") + ".md"
    path = os.path.join(WORDS_DIR, filename)
    if os.path.exists(path):
        print(f"已存在：{filename}")
        return

    today = str(date.today())
    post = frontmatter.Post(
        f"## {word}\n\n**音标**：\n\n**释义**：\n\n**例句**：\n\n**联想/记忆**：",
        type="word",
        tags=["英语"],
        mastery="new",
        due=today,
        interval=1,
        ease=2.5,
        reviews=0,
        word=word,
        phonetic="",
        meaning="",
        example="",
        answer="",
    )
    post["last-review"] = ""
    with open(path, "w", encoding="utf-8") as f:
        frontmatter.dump(post, f)
    print(f"✓ 已添加：{path}")
    print(f"  用 Obsidian 打开笔记补全音标、释义、例句、answer 字段后即可复习")


# ── 入口 ─────────────────────────────────────────────
if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "start":
        cmd_start()
    elif args[0] == "stats":
        cmd_stats()
    elif args[0] == "import" and len(args) >= 2:
        cmd_import(args[1])
    elif args[0] == "add" and len(args) >= 2:
        cmd_add(" ".join(args[1:]))
    else:
        print(__doc__)
