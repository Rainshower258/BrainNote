#!/usr/bin/env python3
"""
BrainNote FastAPI 后端
启动: cd ~/Brain && uvicorn server:app --reload --port 8765
"""

import sys
import os
import glob
import re
from datetime import date, timedelta
from collections import defaultdict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import frontmatter

# ── 配置 ──────────────────────────────────────────────
VAULT = os.path.dirname(os.path.abspath(__file__))
WORDS_DIR = os.path.join(VAULT, "10-Words")
CONCEPTS_DIR = os.path.join(VAULT, "20-Concepts")

# 把 vault 根目录加入 sys.path 以 import review.py 里的 compute_next
if VAULT not in sys.path:
    sys.path.insert(0, VAULT)
from review import compute_next

# mastery 字符串 → SM-2 评分映射
MASTERY_TO_SCORE = {
    "again": 1, "hard": 2, "good": 3, "easy": 4, "perfect": 5,
}

# ── FastAPI app ───────────────────────────────────────
app = FastAPI(title="BrainNote API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 工具函数 ──────────────────────────────────────────

def parse_tip(post) -> str:
    """从笔记正文解析「联想/记忆」字段"""
    content = post.content or ""
    # 匹配 **联想/记忆**： 或 **联想**： 后面的内容
    m = re.search(r'\*\*联想[/*记忆]*\*\*\s*[：:]\s*(.*)', content)
    if m:
        tip = m.group(1).strip()
        return tip if tip else ""
    return ""


def load_all_notes() -> list:
    """加载所有笔记，返回 (id, path, post) 列表"""
    notes = []
    for folder in [WORDS_DIR, CONCEPTS_DIR]:
        for path in glob.glob(os.path.join(folder, "*.md")):
            post = frontmatter.load(path)
            note_id = os.path.splitext(os.path.basename(path))[0]
            notes.append((note_id, path, post))
    return notes


def note_to_card(note_id: str, path: str, post) -> dict:
    """将一条笔记转换为前端 card 格式"""
    note_type = post.get("type", "word")
    card = {
        "id": note_id,
        "type": note_type,
        "mastery": post.get("mastery", "new"),
        "interval": post.get("interval", 1),
        "reviews": post.get("reviews", 0),
        "tip": parse_tip(post),
    }
    if note_type == "word":
        card["word"] = post.get("word", note_id)
        card["phonetic"] = post.get("phonetic", "")
        card["word_type"] = ""  # 由用户在 Obsidian 中自由填写
        card["answer"] = post.get("answer") or post.get("meaning", "")
        card["example"] = post.get("example", "")
    else:
        card["word"] = note_id  # concept 用文件标题
        card["phonetic"] = ""
        card["word_type"] = ""
        card["answer"] = post.get("answer", "")
        card["example"] = ""
    return card


# ── API 接口 ──────────────────────────────────────────

@app.get("/api/due")
def api_due():
    """返回今日待复习笔记列表"""
    today = date.today()
    due_cards = []
    for note_id, path, post in load_all_notes():
        due_str = post.get("due", "")
        if not due_str:
            continue
        try:
            due = date.fromisoformat(str(due_str))
        except ValueError:
            continue
        if due <= today:
            due_cards.append((note_id, path, post))

    due_cards.sort(key=lambda x: x[2].get("interval", 1))
    cards = [note_to_card(nid, p, post) for nid, p, post in due_cards]
    return {"count": len(cards), "cards": cards}


@app.post("/api/rate")
async def api_rate(req: Request):
    """接收评分，更新 frontmatter"""
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)

    note_id = body.get("id")
    note_type = body.get("type", "word")
    rating = body.get("rating")

    if not note_id:
        return JSONResponse({"error": "missing field: id"}, status_code=400)
    if not rating:
        return JSONResponse({"error": "missing field: rating"}, status_code=400)

    if rating not in MASTERY_TO_SCORE:
        return JSONResponse({"error": f"invalid rating: {rating}"}, status_code=400)

    # 找到对应笔记文件
    folder = WORDS_DIR if note_type == "word" else CONCEPTS_DIR
    path = os.path.join(folder, f"{note_id}.md")
    if not os.path.exists(path):
        return JSONResponse({"error": f"note not found: {note_id}"}, status_code=404)

    post = frontmatter.load(path)
    score = MASTERY_TO_SCORE[rating]
    interval = float(post.get("interval", 1))
    ease = float(post.get("ease", 2.5))
    next_interval, next_ease = compute_next(interval, ease, score)
    next_due = date.today() + timedelta(days=next_interval)

    post["mastery"] = rating
    post["interval"] = next_interval
    post["ease"] = next_ease
    post["due"] = str(next_due)
    post["last-review"] = str(date.today())
    post["reviews"] = int(post.get("reviews", 0)) + 1

    with open(path, "w", encoding="utf-8") as f:
        frontmatter.dump(post, f)

    return {"ok": True, "next_due": str(next_due), "next_interval": next_interval}


@app.get("/api/stats")
def api_stats():
    """返回掌握度分布、streak、heatmap"""
    all_notes = load_all_notes()
    today = date.today()

    # 分布
    distribution = {"new": 0, "again": 0, "hard": 0, "good": 0, "easy": 0, "perfect": 0}
    due_today = 0
    review_dates = set()

    for nid, path, post in all_notes:
        m = post.get("mastery", "new")
        if m in distribution:
            distribution[m] += 1
        # 今日待复习
        due_str = post.get("due", "")
        if due_str:
            try:
                if date.fromisoformat(str(due_str)) <= today:
                    due_today += 1
            except ValueError:
                pass
        # 收集所有复习日期
        lr = post.get("last-review", "")
        if lr:
            try:
                review_dates.add(date.fromisoformat(str(lr)))
            except ValueError:
                pass

    # streak：从今天往前数，连续有复习记录的天数
    streak = 0
    d = today
    while d in review_dates:
        streak += 1
        d = d - timedelta(days=1)

    # heatmap：过去 26 周内每天复习的笔记数量
    heatmap = defaultdict(int)
    week_ago_26 = today - timedelta(weeks=26)
    for nid, path, post in all_notes:
        lr = post.get("last-review", "")
        if not lr:
            continue
        try:
            lr_date = date.fromisoformat(str(lr))
        except ValueError:
            continue
        if week_ago_26 <= lr_date <= today:
            heatmap[str(lr_date)] += 1

    return {
        "total": len(all_notes),
        "distribution": distribution,
        "due_today": due_today,
        "streak": streak,
        "heatmap": dict(heatmap),
    }


@app.get("/api/today-date")
def api_today_date():
    """返回今日日期字符串"""
    today = date.today()
    weekdays_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekdays_en = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
    wd = today.weekday()  # 0=Monday
    return {
        "weekday_cn": weekdays_cn[wd],
        "date_cn": f"{today.month}月{today.day}日",
        "weekday_en": weekdays_en[wd],
    }


@app.post("/api/import")
async def api_import(req: Request):
    """批量导入单词（每行一个）"""
    body = await req.body()
    text = body.decode("utf-8")
    words = [line.strip() for line in text.splitlines() if line.strip()]

    today_str = str(date.today())
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
            due=today_str,
            interval=1,
            ease=2.5,
            reviews=0,
            word=word,
            phonetic="",
            meaning="",
            example="",
            answer="",
        )
        post["last-review"] = ""  # hyphenated key, not kwargs-compatible
        with open(path, "w", encoding="utf-8") as f:
            frontmatter.dump(post, f)
        created += 1

    return {"created": created, "skipped": skipped}


# ── 静态文件服务 ──────────────────────────────────────

@app.get("/")
def index():
    html_path = os.path.join(VAULT, "BrainNote.html")
    if not os.path.exists(html_path):
        return JSONResponse({"error": "index not found"}, status_code=404)
    return FileResponse(html_path)
