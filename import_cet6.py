#!/usr/bin/env python3
"""
CET6 词库导入脚本
用法：python import_cet6.py [--limit N] [--skip N]
  --limit N   只导入前 N 个单词（测试用，默认全量）
  --skip N    跳过前 N 个单词（分批导入用）
"""

import json
import os
import sys
import argparse
from datetime import date
import frontmatter

VAULT = os.path.dirname(os.path.abspath(__file__))
WORDS_DIR = os.path.join(VAULT, "10-Words")
JSON_FILE = os.path.join(VAULT, "cet6.json")


def clean_phonetic(p: str) -> str:
    """确保音标有斜杠包裹"""
    if not p:
        return ""
    p = p.strip()
    if p and not p.startswith("/"):
        p = f"/{p}/"
    return p


def clean_trans(trans) -> tuple[str, str]:
    """
    trans 字段可能是 list 或 str。
    返回 (answer简短版, meaning详细版)
    例：["vt. 放弃；遗弃", "n. 放任"] → answer="放弃；遗弃", meaning="vt. 放弃；遗弃 / n. 放任"
    """
    if isinstance(trans, str):
        trans = [trans]
    if not trans:
        return "", ""

    meaning = " / ".join(trans)

    # answer 取第一条，去掉词性标注
    first = trans[0].strip()
    import re
    # 去掉开头的: vt. / n. / adj. 等
    first_clean = re.sub(r'^[a-z]+\.[\s]', '', first).strip()
    # 去掉末尾的: (vt.) / (n.) / (adj.) 等
    first_clean = re.sub(r'\s*\([a-z]+\.\)\s*$', '', first_clean).strip()
    # 只取第一个分号前的内容作为简短 answer
    answer = first_clean.split("；")[0].split(";")[0].strip()

    return answer, meaning


def word_to_filename(word: str) -> str:
    return word.lower().replace(" ", "-").replace("/", "-") + ".md"


def build_body(word: str, meaning: str) -> str:
    return f"""## {word}

**音标**：

**释义**：{meaning}

**例句**：

**联想/记忆**：
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip", type=int, default=0)
    args = parser.parse_args()

    if not os.path.exists(JSON_FILE):
        print(f"❌ 找不到 {JSON_FILE}，请先下载词库")
        sys.exit(1)

    os.makedirs(WORDS_DIR, exist_ok=True)

    with open(JSON_FILE, encoding="utf-8") as f:
        data = json.load(f)

    # 兼容不同格式：list of dict 或 dict with 'words' key
    if isinstance(data, dict):
        data = data.get("words", data.get("content", []))

    total = len(data)
    data = data[args.skip:]
    if args.limit:
        data = data[:args.limit]

    today = str(date.today())
    created = 0
    skipped = 0
    errors = 0

    print(f"📚 词库共 {total} 个单词，本次处理 {len(data)} 个（skip={args.skip}）\n")

    for item in data:
        try:
            # 字段名适配（qwerty-learner 格式）
            word = item.get("name", item.get("word", "")).strip()
            if not word:
                continue

            usphone = clean_phonetic(item.get("usphone", item.get("us-phonetic", "")))
            ukphone = clean_phonetic(item.get("ukphone", item.get("uk-phonetic", "")))
            phonetic = usphone or ukphone  # 优先美音

            trans = item.get("trans", item.get("translation", item.get("definition", [])))
            answer, meaning = clean_trans(trans)

            filename = word_to_filename(word)
            path = os.path.join(WORDS_DIR, filename)

            if os.path.exists(path):
                skipped += 1
                continue

            post = frontmatter.Post(
                build_body(word, meaning),
                type="word",
                tags=["英语", "CET6"],
                mastery="new",
                due=today,
                interval=1,
                ease=2.5,
                **{"last-review": ""},
                reviews=0,
                word=word,
                phonetic=phonetic,
                meaning=meaning,
                example="",
                answer=answer,
            )

            with open(path, "w", encoding="utf-8") as f:
                frontmatter.dump(post, f)
            created += 1

        except Exception as e:
            errors += 1
            print(f"  ⚠️  {item.get('name', '?')} 处理失败：{e}")

    print(f"\n✅ 完成：新建 {created} 条 / 跳过已有 {skipped} 条 / 错误 {errors} 条")
    print(f"   文件位置：{WORDS_DIR}")


if __name__ == "__main__":
    main()
