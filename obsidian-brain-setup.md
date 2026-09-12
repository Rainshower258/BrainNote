# Obsidian Brain System — CC 实施文档

## 任务概述

在本地 Obsidian vault 中搭建一套基于 SM-2 间隔重复的个人知识管理系统，包含：
1. vault 文件夹结构
2. Templater 模板文件
3. Dataview 看板笔记
4. Python 复习脚本 `review.py`

**vault 路径**：执行前先确认，运行 `find ~ -name "*.obsidian" -type d 2>/dev/null` 或询问用户。

---

## 第一步：确认环境

```bash
# 确认 vault 路径（让用户确认）
echo "请确认你的 vault 路径，例如 ~/Brain 或 ~/Documents/Brain"

# 安装 Python 依赖
pip install sm-2 python-frontmatter
```

---

## 第二步：创建文件夹结构

在 vault 根目录下创建以下文件夹（如已存在则跳过）：

```
00-Templates/
10-Words/
20-Concepts/
30-Reviews/
40-Journal/
```

```bash
VAULT="$HOME/Brain"   # 替换为实际路径
mkdir -p "$VAULT/00-Templates"
mkdir -p "$VAULT/10-Words"
mkdir -p "$VAULT/20-Concepts"
mkdir -p "$VAULT/30-Reviews"
mkdir -p "$VAULT/40-Journal"
```

---

## 第三步：写入 Templater 模板

### `00-Templates/word-template.md`

```markdown
---
type: word
tags: [英语]
mastery: new
due: <% tp.date.now("YYYY-MM-DD") %>
interval: 1
ease: 2.5
last-review: ""
reviews: 0
word: 
phonetic: 
meaning: 
example: 
answer: 
---

## <% tp.file.title %>

**音标**：

**释义**：

**例句**：

**联想/记忆**：
```

### `00-Templates/concept-template.md`

```markdown
---
type: concept
tags: []
mastery: new
due: <% tp.date.now("YYYY-MM-DD") %>
interval: 1
ease: 2.5
last-review: ""
reviews: 0
answer: 
---

## <% tp.file.title %>

**一句话定义**：

**展开**：

**关联笔记**：
```

---

## 第四步：写入 Dataview 看板

### `30-Reviews/dashboard.md`

````markdown
# 复习看板

## 今日待复习

```dataviewjs
const today = dv.date("today");
const due = dv.pages('"10-Words" OR "20-Concepts"')
  .where(p => p.due && dv.date(p.due) <= today)
  .sort(p => p.interval, 'asc');

dv.header(3, `待复习 ${due.length} 条`);
if (due.length === 0) {
  dv.paragraph("✅ 今日无待复习，继续保持！");
} else {
  dv.table(
    ["笔记", "类型", "掌握度", "间隔(天)", "到期"],
    due.map(p => [p.file.link, p.type, p.mastery, p.interval, p.due])
  );
}
```

## 掌握度分布

```dataviewjs
const all = dv.pages('"10-Words" OR "20-Concepts"');
const states = ["new", "again", "hard", "good", "easy", "perfect"];
const emoji = {"new":"🆕","again":"❌","hard":"😬","good":"👍","easy":"😊","perfect":"⭐"};
const rows = states.map(s => {
  const count = all.where(p => p.mastery === s).length;
  return [emoji[s] + " " + s, count];
});
dv.table(["状态", "数量"], rows);
dv.paragraph(`共 ${all.length} 条笔记`);
```

## 近期复习记录（最近7天新增）

```dataviewjs
const week = dv.date("today").minus({days: 7});
const recent = dv.pages('"10-Words" OR "20-Concepts"')
  .where(p => p["last-review"] && dv.date(p["last-review"]) >= week)
  .sort(p => p["last-review"], 'desc')
  .limit(20);
dv.table(
  ["笔记", "类型", "上次复习", "掌握度"],
  recent.map(p => [p.file.link, p.type, p["last-review"], p.mastery])
);
```
````

---

## 第五步：写入复习脚本

### `review.py`（放在 vault 根目录）

```python
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
    post["reviews"] = post.get("reviews", 0) + 1

    with open(path, "wb") as f:
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
            last_review="",
            reviews=0,
            word=word,
            phonetic="",
            meaning="",
            example="",
            answer="",
        )
        with open(path, "wb") as f:
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
        last_review="",
        reviews=0,
        word=word,
        phonetic="",
        meaning="",
        example="",
        answer="",
    )
    with open(path, "wb") as f:
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
        cmd_add(" ".join(args[2:]) if len(args) > 2 else args[1])
    else:
        print(__doc__)
```

---

## 第六步：验证

```bash
cd "$VAULT"
python review.py stats        # 应显示"vault 中暂无笔记"
python review.py add abandon  # 新建一条测试单词
python review.py stats        # 应显示 new: 1
python review.py start        # 测试复习流程
```

---

## 注意事项

- **vault 路径**：脚本第一行 `VAULT` 变量自动取脚本所在目录，`review.py` 必须放在 vault 根目录。
- **Templater 变量**：模板里的 `<% tp.date.now(...) %>` 语法依赖 Templater 插件，在 Obsidian 内用模板新建笔记时自动展开，CC 批量导入时不需要这个。
- **answer 字段**：word 类型笔记导入后需要在 Obsidian 里手动补全 `answer`（释义简写），CC 复习时用这个字段判题；concept 类型 `answer` 是参考答案，用户自评。
- **编码**：vault 路径不要含中文或空格，否则 glob 可能出问题。
