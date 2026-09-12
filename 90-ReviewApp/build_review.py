#!/usr/bin/env python3
"""
90-ReviewApp 每日背词构建脚本（含 Cloze 挖空造句题）

用法：
  python3 build_review.py                       # 正常生成：sync/day_YYYY-MM-DD.json + review.html
  python3 build_review.py --mock                # 用内置假例句，不调用 DeepSeek API（离线演示/测试）
  python3 build_review.py --output out.html     # 只把 HTML 写到指定文件，不覆盖 review.html
  python3 build_review.py --no-day-json         # 不写 day JSON
  python3 build_review.py --date 2026-07-22 --cursor 0 --no-shuffle --seed 0   # 复现历史某天（回归测试）
  python3 build_review.py --dry-run             # 只打印将要做什么，不写任何文件

流程：
  1. 扫描 10-Words/*.md 词库（frontmatter 作数据源，不改动笔记内容）
  2. 到期复习词 = reviews>0 且 due<=今天；新词 = 按字母序从 cursor 起的 25 个从未学过的词
     （cursor 只在同步确认后由同步脚本推进，本脚本不推进，避免漏词/重复）
  3. 生成 sync/day_YYYY-MM-DD.json 当日词表
  4. Cloze 例句：默认走本地 llama-server（Qwen3.5-2B，config.local.json 的
     cloze_backend 控制，默认 "local"）；本地生成失败（连不上/重试耗尽）→
     自动 fallback 到 DeepSeek API（需 deepseek_api_key）；两者都失败 →
     静默跳过该词，对应挖空卡片在浏览器端自动跳过，不阻塞背词。
     缓存 sync/cloze_cache.json，key=word，新写入的条目带 source 字段
     （"local-qwen35-2b" / "deepseek"），标记来源方便以后对比质量。
     本地模型只是可替换的内容生成组件：它挂了要能退回 API/缓存，不能让
     背词流程瘫掉；同时它不参与 SM-2 调度决策，只负责把选中的词包装成
     挖空题。
  5. 渲染 template.html → review.html

只依赖 frontmatter；API 调用用标准库 urllib。
"""

import os
import re
import sys
import json
import glob
import random
import argparse
import urllib.request
import urllib.error
from datetime import date, timedelta

import frontmatter

APP_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT = os.path.dirname(APP_DIR)          # Brain/（vault 根）
WORDS_DIR = os.path.join(VAULT, "10-Words")
SYNC_DIR = os.path.join(APP_DIR, "sync")
CONFIG_PATH = os.path.join(APP_DIR, "config.local.json")
CACHE_PATH = os.path.join(SYNC_DIR, "cloze_cache.json")
TEMPLATE_PATH = os.path.join(APP_DIR, "template.html")
HTML_PATH = os.path.join(APP_DIR, "review.html")

DEFAULT_CLOZE_PROB_NEW = 0.15
DEFAULT_DAILY_MAX = 30


# ─────────────────────────────────────────────────────────────
# SM-2（与 review.py 的 compute_next 完全一致，供参考/校验）
# ─────────────────────────────────────────────────────────────
def compute_next(interval: float, ease: float, score: int):
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


# ─────────────────────────────────────────────────────────────
# 词库读取
# ─────────────────────────────────────────────────────────────
def load_words():
    """返回按字母序排列的全部词条 dict（字段与 day JSON 一致）。"""
    words = []
    for path in glob.glob(os.path.join(WORDS_DIR, "*.md")):
        post = frontmatter.load(path)
        word = str(post.get("word") or os.path.splitext(os.path.basename(path))[0]).strip()
        words.append({
            "id": word,
            "path": os.path.relpath(path, VAULT),
            "word": word,
            "phonetic": str(post.get("phonetic", "") or ""),
            "meaning": str(post.get("meaning", "") or ""),
            "shortMeaning": short_meaning(str(post.get("meaning", "") or "")),
            "example": str(post.get("example", "") or ""),
            "tip": "",
            "mastery": str(post.get("mastery", "new") or "new"),
            "due": str(post.get("due", "") or ""),
            "interval": float(post.get("interval", 1) or 1),
            "ease": float(post.get("ease", 2.5) or 2.5),
            "reviews": int(post.get("reviews", 0) or 0),
        })
    words.sort(key=lambda w: w["word"].lower())
    return words


def short_meaning(meaning: str) -> str:
    """从完整释义提取短释义（用于选项/卡片展示）：
       只取第一个义项，去掉词性前缀（v. 等）和末尾的（adj.）等括号。"""
    m = (meaning or "").strip()
    m = re.split(r"\s*/\s*", m)[0]                      # 第一个义项（用 / 分隔多义项）
    m = re.sub(r"^[a-z]+\.\s*", "", m)                   # 去掉开头词性 "v. "
    m = re.sub(r"\s*[（(][^）)]*[）)]\s*$", "", m)       # 去掉末尾（adj.）
    m = re.split(r"[；;]", m)[0].strip()
    return m


def is_new(w):
    return w["mastery"] == "new" or w["reviews"] == 0


def compute_daily(words, today, cursor, new_per_day, daily_max=DEFAULT_DAILY_MAX):
    """返回 (review_words, new_words)。
    review = 学过的且 due<=今天，按 due 升序（最过期的优先）；
    new = 从全字母序列表的 S-位置 cursor 起，取接下来的 new_per_day 个"新词"
    （cursor 是"全字母序里的稳定位置"，与词是否已同步无关，因此跨天不重复、不漏词）。

    每日总量上限 daily_max（默认 30）：
      - 复习词数 >= daily_max：只取最过期的 daily_max 个复习词，当天不引入新词；
        剩余复习词 due 不变，明天/下次继续算作到期，自然排到后面（不丢词、不用额外状态）。
      - 复习词数 < daily_max：复习词全部保留，新词数 = min(new_per_day, daily_max - 复习词数)。
    """
    review = []
    for w in words:
        if w["reviews"] > 0 and w["due"]:
            try:
                if date.fromisoformat(w["due"]) <= today:
                    review.append(w)
            except ValueError:
                continue
    review.sort(key=lambda w: w["due"])  # 最过期（due 最早）的排在前面，优先被保留

    if len(review) >= daily_max:
        return review[:daily_max], []

    take_new = min(new_per_day, daily_max - len(review))
    new_words = []
    for s_pos, w in enumerate(sorted(words, key=lambda x: x["word"].lower())):
        if s_pos < cursor:
            continue
        if is_new(w):
            new_words.append(w)
            if len(new_words) == take_new:
                break
    return review, new_words


def day_entry(w, is_review):
    e = dict(w)
    e["isReview"] = bool(is_review)
    return e


# ─────────────────────────────────────────────────────────────
# Cloze 例句：缓存 + DeepSeek API
# ─────────────────────────────────────────────────────────────
def load_cache():
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(cache):
    os.makedirs(SYNC_DIR, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def sentence_contains_word(sentence, word):
    return bool(re.search(r"\b" + re.escape(word) + r"\b", sentence, flags=re.IGNORECASE))


def call_deepseek(word, meaning, config):
    """调 DeepSeek 生成双语例句。成功返回 {sentence_en, sentence_zh}，失败返回 None。"""
    api_key = (config.get("deepseek_api_key") or "").strip()
    if not api_key:
        return None
    model = config.get("model", "deepseek-v4-flash")
    base_url = (config.get("base_url", "https://api.deepseek.com") or "").rstrip("/")
    timeout = float(config.get("timeout_sec", 30) or 30)

    pos = re.match(r"^([a-zA-Z]+\.)", meaning)
    pos_text = pos.group(1) if pos else ""

    prompt = (
        f"单词：{word}\n"
        f"词性：{pos_text}\n"
        f"中文释义：{meaning}\n\n"
        "请生成一句包含该单词的英文例句：\n"
        "- 难度适中，符合 CET6 水平，不要用比单词本身更难的生僻搭配\n"
        "- 句中必须使用该单词的【原形】：不变化时态/单复数/词性（动词可用不定式 to + 原形、或情态动词 can/must + 原形、或祈使句原形开头），严禁用第三人称单数/过去式/现在分词等变形\n"
        "- 长度 10-20 个词左右\n"
        "- 另附对应中文翻译\n\n"
        '只返回一个 JSON 对象，不要任何其他文字：{"sentence_en": "英文例句", "sentence_zh": "中文翻译"}'
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是英语教学助手，为用户给出的 CET6 词汇生成学习用双语例句。只输出 JSON，不输出其他内容。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        obj = json.loads(content)
        sent_en = (obj.get("sentence_en") or "").strip()
        sent_zh = (obj.get("sentence_zh") or "").strip()
    except (urllib.error.URLError, OSError, TimeoutError, KeyError, IndexError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"  [cloze] 跳过 {word}：API 调用失败（{type(exc).__name__}: {exc}）")
        return None
    if not sent_en or not sent_zh:
        print(f"  [cloze] 跳过 {word}：返回内容不完整")
        return None
    if not sentence_contains_word(sent_en, word):
        print(f"  [cloze] 跳过 {word}：例句未含原形（{sent_en!r}）")
        return None
    return {"sentence_en": sent_en, "sentence_zh": sent_zh}


def _word_variants(word):
    """派生极简变形表：复数/三单 -s、过去式/进行时 -ed/-ing、比较级 -er/-est。
    不接受跨词性派生（如 arbitrary -> arbitrarily）——挖空题答案键存的是
    原形，接受派生形式会导致学习者填的答案和答案键对不上。"""
    w = word.lower()
    variants = {w}
    vowels = "aeiou"

    def is_cvc(base):
        return (len(base) >= 3 and base[-1] not in "aeiouwxy"
                and base[-2] in vowels and base[-3] not in vowels)

    if w.endswith(("s", "x", "z", "ch", "sh")):
        variants.add(w + "es")
    elif w.endswith("y") and len(w) > 1 and w[-2] not in vowels:
        variants.add(w[:-1] + "ies")
    else:
        variants.add(w + "s")

    if w.endswith("e") and not w.endswith("ee"):
        variants.add(w + "d")
        variants.add(w[:-1] + "ing")
    elif w.endswith("y") and len(w) > 1 and w[-2] not in vowels:
        variants.add(w[:-1] + "ied")
        variants.add(w + "ing")
    elif is_cvc(w):
        variants.add(w + w[-1] + "ed")
        variants.add(w + w[-1] + "ing")
    else:
        variants.add(w + "ed")
        variants.add(w + "ing")

    if w.endswith("y") and len(w) > 1 and w[-2] not in vowels:
        variants.add(w[:-1] + "ier")
        variants.add(w[:-1] + "iest")
    elif is_cvc(w):
        variants.add(w + w[-1] + "er")
        variants.add(w + w[-1] + "est")
    else:
        variants.add(w + "er")
        variants.add(w + "est")

    return variants


def _sentence_form_ok(sentence, word):
    """目标词（或其屈折变形，不含跨词性派生）在句中恰好出现一次。"""
    variants = sorted(_word_variants(word), key=len, reverse=True)
    pattern = r"\b(" + "|".join(re.escape(v) for v in variants) + r")\b"
    return len(re.findall(pattern, sentence, flags=re.IGNORECASE)) == 1


LOCAL_SYS = "你是英语教学助手，为用户给出的 CET6 词汇生成学习用双语例句。只输出 JSON，不输出其他内容。"

LOCAL_INSTR = (
    "请生成一句包含该单词的英文例句：\n"
    "- 难度适中，符合 CET6 水平，不要用比单词本身更难的生僻搭配\n"
    "- 句中必须使用该单词的【精确原形】：一字不差，不能是改变词性得到的派生词"
    "（例如形容词变副词），也不能变时态/单复数\n"
    "- 长度 10-20 个词左右\n"
    "- 另附对应中文翻译\n\n"
    "Example:\n"
    "Target word: arbitrary\n"
    'WRONG: "The decision was made arbitrarily." (用了派生副词 "arbitrarily"，不允许)\n'
    'RIGHT: "The decision was arbitrary." (精确原形 "arbitrary")\n\n'
    '只返回一个 JSON 对象，不要任何其他文字：{"sentence_en": "英文例句", "sentence_zh": "中文翻译"}'
)

LOCAL_MAX_RETRIES = 3


def call_local(word, meaning, config):
    """调本地 llama-server 生成双语例句。成功返回 {sentence_en, sentence_zh}，
    失败（连不上 / 重试耗尽）返回 None，调用方负责 fallback 到 DeepSeek。"""
    base_url = (config.get("local_base_url") or "http://127.0.0.1:8901").rstrip("/")
    timeout = float(config.get("local_timeout_sec", 20) or 20)

    pos = re.match(r"^([a-zA-Z]+\.)", meaning)
    pos_text = pos.group(1) if pos else ""

    tail = f"单词：{word}\n词性：{pos_text}\n中文释义：{meaning}\n\n{LOCAL_INSTR}"
    prev_sentence = None

    for attempt in range(1, LOCAL_MAX_RETRIES + 1):
        user_content = tail
        if attempt > 1 and prev_sentence:
            user_content += (
                f'\n\n上一次生成的句子是："{prev_sentence}"，其中没有以精确原形 '
                f'"{word}" 出现。必须使用 "{word}" 这个精确形式。'
            )
        payload = {
            "messages": [
                {"role": "system", "content": LOCAL_SYS},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.6 + (attempt - 1) * 0.15,
            "max_tokens": 200,
        }
        req = urllib.request.Request(
            base_url + "/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            # 模型偶尔会在 JSON 前后夹带说明文字，取第一个花括号块
            m = re.search(r"\{.*\}", content, flags=re.DOTALL)
            obj = json.loads(m.group(0) if m else content)
            sent_en = (obj.get("sentence_en") or "").strip()
            sent_zh = (obj.get("sentence_zh") or "").strip()
        except (urllib.error.URLError, OSError, TimeoutError, KeyError, IndexError,
                json.JSONDecodeError, TypeError, ValueError, AttributeError) as exc:
            if isinstance(exc, (urllib.error.URLError, OSError, TimeoutError)):
                # 连不上本地服务：不用再重试，直接交给调用方 fallback
                print(f"  [cloze-local] {word}：本地服务不可用（{type(exc).__name__}: {exc}）")
                return None
            print(f"  [cloze-local] {word} 第{attempt}次：解析失败（{type(exc).__name__}: {exc}）")
            continue
        if not sent_en or not sent_zh:
            print(f"  [cloze-local] {word} 第{attempt}次：返回内容不完整")
            continue
        if not _sentence_form_ok(sent_en, word):
            print(f"  [cloze-local] {word} 第{attempt}次：例句未含精确原形（{sent_en!r}）")
            prev_sentence = sent_en
            continue
        return {"sentence_en": sent_en, "sentence_zh": sent_zh}

    print(f"  [cloze-local] {word}：重试{LOCAL_MAX_RETRIES}次仍未通过校验，fallback")
    return None


def mock_sentence(word, meaning):
    """离线测试用假例句：保证含原形词。"""
    return {
        "sentence_en": f"The professor asked the class to use the word \"{word}\" in a sentence of their own.",
        "sentence_zh": f"教授要求全班用单词 {word} 各造一句自己的句子。",
    }


def build_cloze_map(words, config, use_mock):
    """为当日所有词准备挖空数据。返回 {word: {sentence_en, sentence_zh}}。"""
    result = {}
    if use_mock:
        for w in words:
            result[w["word"]] = mock_sentence(w["word"], w["meaning"])
        return result

    cache = load_cache()
    dirty = False
    api_key = (config.get("deepseek_api_key") or "").strip()
    backend = (config.get("cloze_backend") or "local").strip().lower()
    local_tag = config.get("local_model_tag") or "local-qwen35-2b"

    for w in words:
        key = w["word"]
        if key in cache:
            result[key] = cache[key]
            continue

        sent = None
        source = None

        if backend == "local":
            sent = call_local(key, w["meaning"], config)
            source = local_tag
            if not sent and api_key:
                sent = call_deepseek(key, w["meaning"], config)
                source = "deepseek"
        elif backend == "deepseek":
            if api_key:
                sent = call_deepseek(key, w["meaning"], config)
                source = "deepseek"
        else:
            print(f"  [cloze] 未知 cloze_backend={backend!r}，跳过 {key}")

        if not sent:
            continue  # 本地+API 都失败/都没配置：result 不含该词 → 静默跳过
        entry = dict(sent, source=source)
        cache[key] = entry
        dirty = True
        result[key] = entry
        print(f"  [cloze] {key} ✓（{source}）")

    if dirty:
        save_cache(cache)
    return result


# ─────────────────────────────────────────────────────────────
# HTML 渲染
# ─────────────────────────────────────────────────────────────
def inject_json(value):
    """JSON 内嵌进 <script> 时把 </ 转义成 <\\/，避免意外闭合标签。"""
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def render_html(template, words, cloze_map, cloze_prob, today):
    html = template
    html = html.replace("@@WORDS@@", inject_json(words))
    html = html.replace("@@CLOZE@@", inject_json(cloze_map))
    html = html.replace("@@CLOZE_PROB@@", json.dumps(cloze_prob))
    html = html.replace("@@TITLE_DATE@@", today.isoformat())
    return html


# ─────────────────────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="生成每日背词 HTML（含 Cloze 挖空造句题）")
    ap.add_argument("--mock", action="store_true", help="用内置假例句，不调用 API")
    ap.add_argument("--output", metavar="PATH", help="HTML 写到指定路径（默认覆盖 review.html）")
    ap.add_argument("--no-day-json", action="store_true", help="不写 sync/day_*.json")
    ap.add_argument("--date", metavar="YYYY-MM-DD", help="指定'今天'（默认系统日期）")
    ap.add_argument("--cursor", type=int, help="覆盖新词游标（默认读 progress.json）")
    ap.add_argument("--new-per-day", type=int, help="覆盖每日新词数（默认读 progress.json）")
    ap.add_argument("--daily-max", type=int, help="覆盖每日总量上限（默认读 progress.json，缺省 30）")
    ap.add_argument("--seed", type=int, help="随机种子（测试用）")
    ap.add_argument("--no-shuffle", action="store_true", help="不随机打散复习+新词顺序")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    args = ap.parse_args()

    today = date.fromisoformat(args.date) if args.date else date.today()
    if args.seed is not None:
        random.seed(args.seed)

    # —— progress.json 配置 ——
    progress = {}
    progress_path = os.path.join(APP_DIR, "progress.json")
    if os.path.exists(progress_path):
        with open(progress_path, encoding="utf-8") as f:
            progress = json.load(f)
    cursor = args.cursor if args.cursor is not None else int(progress.get("cursor_index", 0))
    new_per_day = args.new_per_day if args.new_per_day is not None else int(progress.get("new_words_per_day", 25))
    daily_max = args.daily_max if args.daily_max is not None else int(progress.get("dailyMaxWords", DEFAULT_DAILY_MAX))
    cloze_prob = float(progress.get("clozeProbabilityNewWord", DEFAULT_CLOZE_PROB_NEW))

    # —— 词库 ——
    words = load_words()
    review, new_words = compute_daily(words, today, cursor, new_per_day, daily_max)
    day_words = review + new_words
    if not args.no_shuffle:
        random.shuffle(day_words)

    if not new_words and len(review) >= daily_max:
        print(f"[build] 复习词已达上限 {daily_max}，今天不引入新词（纯复习日）")
    print(f"[build] 日期={today}  游标={cursor}  上限={daily_max}  新词={len(new_words)}  复习={len(review)}  合计={len(day_words)}")
    print(f"[build] 新词范围: {new_words[0]['word'] if new_words else '-'} ~ {new_words[-1]['word'] if new_words else '-'}")
    print(f"[build] 复习词: {[w['word'] for w in review]}")

    if args.dry_run:
        print("[build] --dry-run，未写任何文件")
        return

    # —— 当日词表 JSON ——
    day_json = [day_entry(w, w["reviews"] > 0) for w in day_words]
    if not args.no_day_json:
        os.makedirs(SYNC_DIR, exist_ok=True)
        day_path = os.path.join(SYNC_DIR, f"day_{today.isoformat()}.json")
        with open(day_path, "w", encoding="utf-8") as f:
            json.dump(day_json, f, ensure_ascii=False, indent=2)
        print(f"[build] 已写 {day_path}")

    # —— Cloze 例句 ——
    config = load_config()
    cloze_map = build_cloze_map(day_words, config, args.mock)
    print(f"[build] 挖空数据: {len(cloze_map)}/{len(day_words)} 个词可用"
          + ("（mock）" if args.mock else ("（无 API key，浏览器将跳过挖空题）" if not (config.get('deepseek_api_key') or '').strip() else "")))

    # —— 渲染 HTML ——
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()
    html = render_html(template, day_json, cloze_map, cloze_prob, today)
    out_path = args.output or HTML_PATH
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[build] 已写 {out_path}")


if __name__ == "__main__":
    main()
