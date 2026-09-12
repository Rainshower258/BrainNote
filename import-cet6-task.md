# CET6 词库导入 — CC 任务书

## 任务目标

从 qwerty-learner 下载 CET6 JSON 词库，写一个转换脚本，直接生成带完整 frontmatter 的 `.md` 文件到 `10-Words/`。

---

## 第一步：下载词库

```bash
cd ~/Brain
curl -o cet6.json "https://raw.githubusercontent.com/RealKai42/qwerty-learner/master/public/dicts/CET6_T.json"
```

下载后确认格式，打印前两条：

```bash
python3 -c "import json; data=json.load(open('cet6.json')); print(json.dumps(data[:2], ensure_ascii=False, indent=2))"
```

确认字段名（预期是 `name` / `trans` / `usphone` / `ukphone`），如果字段名不同，后续脚本对应调整。

---

## 第二步：新建 `import_cet6.py`

放在 vault 根目录（`~/Brain/import_cet6.py`）：

```python
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

    # answer 取第一条，去掉词性标注（vt. / n. / adj. 等）
    first = trans[0].strip()
    import re
    first_clean = re.sub(r'^[a-z]+\.[\s]', '', first).strip()
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

            with open(path, "wb") as f:
                frontmatter.dump(post, f)
            created += 1

        except Exception as e:
            errors += 1
            print(f"  ⚠️  {item.get('name', '?')} 处理失败：{e}")

    print(f"\n✅ 完成：新建 {created} 条 / 跳过已有 {skipped} 条 / 错误 {errors} 条")
    print(f"   文件位置：{WORDS_DIR}")


if __name__ == "__main__":
    main()
```

---

## 第三步：先小批测试

```bash
cd ~/Brain

# 先跑 10 个验证格式
python import_cet6.py --limit 10

# 检查生成的文件
cat "10-Words/abandon.md"   # 或者看第一个生成的文件

# 确认 frontmatter 字段正确后，全量导入
python import_cet6.py
```

---

## 第四步：验证

```bash
# 查看导入数量
python review.py stats

# 确认 API 能读到
curl http://localhost:8765/api/stats | python3 -m json.tool
```

期望结果：`distribution.new` 显示导入的单词总数（CET6 约 2000-2500 词）。

---

## 注意事项

- `answer` 字段自动从 `trans` 第一条提取，去掉词性标注后取第一个分号前的内容。实际复习时如果觉得不准可以在 Obsidian 里手动微调。
- `meaning` 字段保留完整释义（含词性），用于笔记页展示。
- `example` 字段留空——qwerty-learner 词库没有例句。如果后续想自动补例句，可以用 Ollama qwen3:14b 批量生成（另起任务）。
- 脚本支持 `--skip` 参数，方便分批导入或出错后断点续跑。
- 已存在的文件自动跳过，重复跑脚本安全。
