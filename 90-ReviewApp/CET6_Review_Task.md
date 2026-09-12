# CET6 背词系统 — 任务书

## 项目概述

基于 Obsidian「脑记」(BrainNote) vault 里已有的六级词库（`10-Words/*.md`，共 2345 条），
做一个每日交互式 HTML 背词工具。不改动现有 Obsidian 笔记结构，只读取 frontmatter 作为词库，
复习结果通过导出 JSON 的方式同步回对应 `.md` 文件。

不依赖服务器、不依赖网络，纯本地单文件 HTML，双击即可在浏览器打开。

---

## 数据源

- 词库目录：`10-Words/*.md`（frontmatter 字段：`word` / `phonetic` / `meaning` / `answer` / `example` / `mastery` / `due` / `interval` / `ease` / `reviews` / `last-review`）
- 原复习逻辑参考：`review.py`（`compute_next()` = SM-2 简化版，与 Kotlin 端 `Sm2Algorithm.kt` 逻辑一致）
- **不使用** `BrainNote_kt` 安卓项目目录，那是另一个独立的开发中 App，与本任务无关

---

## 每日流程

1. 扫描 `10-Words/*.md`，计算：
   - 到期复习词：`due <= today`
   - 新词：`mastery == "new"` 或 `reviews == 0`
2. 取全部到期复习词 + 按字母序取 25 个新词（游标记录在 `progress.json`，每天从上次结束的位置继续，不重复）
3. 生成当日词表 JSON（`sync/day_YYYY-MM-DD.json`），供 HTML 读取
4. 生成/覆盖当日 HTML（`review.html`），内嵌当日词表数据
5. 用户在浏览器中完成背词，结束后点击"导出进度"，下载 `session-YYYY-MM-DD.json` 到 `sync/` 目录
6. 下次对话时，我读取该 session 文件，按 SM-2 更新对应 `.md` 的 frontmatter（`mastery` / `due` / `interval` / `ease` / `reviews` / `last-review`），并推进 `progress.json` 游标，生成下一天的 HTML

---

## 练习形式（每个词按顺序过一遍）

1. **遮词卡片**：先看音标 + 词性，点击/按空格翻转看释义、例句、记忆提示
2. **看英选中**：显示单词，四选一选中文释义
3. **看中选英**：显示中文释义，四选一选英文单词
4. **拼写练习**：显示释义 + 音标，手动输入拼写，实时校验

四关全部答对才算这个词"过关"；任一环节答错，该词会在**本次会话内**重新排队（加入后面几张的位置），
增加当次出现频率，直到答对为止。

---

## SM-2 评分与错词加权

- 会话中，每个词最终只产出**一个"当日总评分"**（again/hard/good/easy/perfect），规则：
  - 4 关全部一次通过 → easy 或 perfect（视速度/无错次数）
  - 有 1-2 次错误 → good 或 hard
  - 反复出错（≥3次）→ again
- 评分对应 `review.py` 里的 `compute_next(interval, ease, score)`，一比一复用同一套公式：
  - again(1)：interval=1，ease -= 0.20
  - hard(2)：interval=prev×1.2，ease -= 0.15
  - good(3)：interval=prev×ease，ease 不变
  - easy(4)：interval=prev×ease×1.3，ease += 0.10
  - perfect(5)：interval=prev×ease×1.5，ease += 0.15
  - ease 下限 1.3
- 错词由于本次评分更低，`interval` 更短、下次 `due` 更近 —— 这就是"自动提高权重、更频繁出现"的机制，
  不需要额外的独立权重字段，直接复用 SM-2 本身的特性。

---

## 数量规则

- 新词：每天目标 25 个
- 复习词：当天到期的全部计入优先级（按 due 升序，最过期的优先）
- **每日总量上限 30**（`progress.json` 的 `dailyMaxWords`，默认 30，可调）：
  - 复习词数 < 30：复习词全部保留，新词数 = `min(25, 30 - 复习词数)`
  - 复习词数 >= 30：只取最过期的 30 个复习词，**当天不引入新词**（纯复习日）；
    剩余复习词 `due` 不变，不需要额外状态记录——它们本来就还是"到期"的，下次生成时自然会被重新纳入候选，排在更晚才学的复习词前面（因为仍按 due 升序取），不会丢词、也不会被无限期推迟
- 两者合并后随机打散顺序（复习词不集中在开头或结尾）
- 该规则已实现在 `build_review.py` 的 `compute_daily()` 里（`--daily-max` 可临时覆盖）

---

## 目录结构

```
90-ReviewApp/
├── CET6_Review_Task.md      # 本任务书
├── review.html              # 当日交互页面（每天重新生成覆盖）
├── progress.json            # 学习游标：记录已引入到哪个新词、总进度统计
└── sync/
    ├── day_2026-07-22.json      # 当日词表快照（生成时写入）
    └── session_2026-07-22.json  # 用户导出的当日复习结果（浏览器下载后需放入此目录）
```

---

## 对接 Obsidian 同步

- `session_*.json` 结构：`[{word, path, score, wrongCount, exercises: {flip, en2cn, cn2en, spelling}}]`
- 同步时对每条记录：
  1. 读取 `path` 指向的 `.md` 文件
  2. 用 `score` 走一遍 SM-2 公式得到新的 `interval` / `ease` / `due`
  3. 写回 frontmatter：`mastery` / `interval` / `ease` / `due` / `reviews`(+1) / `last-review`(=今天)
  4. 正文内容不动，只重写 frontmatter 块
- 这样背词进度和 Obsidian 里 `review.py` 手动复习是同一套数据，两边不会脱节

---

## 不需要实现的部分

- 服务器 / 数据库（纯本地文件 + 浏览器）
- 用户账号体系
- 语音朗读（本版本暂不做 TTS，后续可加）
- 例句为空时的自动生成（当前例句字段大多为空，暂时留空展示，不阻塞背词流程）

---

## 验收标准（Day 1 原型）

1. 打开 `review.html` 能看到 26 张卡片（25 新词 + 1 到期复习词 abandon）
2. 四种练习形式都能正常交互，错误会导致该词重新排队
3. 全部完成后显示总结页（正确率、错词列表、用时）
4. 点击"导出进度"能下载出结构正确的 JSON 文件
5. 我能读取该 JSON，正确算出下一次 SM-2 参数并写回对应 `.md` frontmatter

---

## 现状说明（写给 Claude Code 的背景，2026-08-02）

Day 1 原型（`review.html`，25 新词 abnormal~accumulate + 1 复习词 abandon）已经生成并验证过前端逻辑（四关顺序、错词重排、SM-2 评分映射、导出 JSON），但**从未同步回 Obsidian**：

- `progress.json` 里 `history[0].synced` 仍是 `false`
- `cursor_index` 停在 25，Day 2 的新词从未生成
- 用户今天（8/2，距 7/22 已过 11 天）是重新打开同一份 `review.html` 又背了一遍第一天的内容，不是在推进新进度

**Claude Code 接手时需要注意：**

1. 不要假设"每天生成一批"是严格按自然日推进的——用户可能隔几天才用一次。取 due 复习词时永远用 `due <= 当天真实日期` 现算，不要依赖 `progress.json` 里的历史日期做推算。
2. 新词游标（`cursor_index`）只在**确认 sync 完成**后才推进，避免用户没同步就重复生成、或漏词。
3. 今天这次重做的 session，如果用户导出了 JSON，按正常同步流程处理（第一次真正 sync），`cursor_index` 才第一次推进到 25。

---

## 新增功能：挖空造句题（Cloze）

### 目的

在遮词卡片 / 看英选中 / 看中选英 / 拼写 之外，增加第五种练习形式：给该单词生成一句**双语例句**（英文句子 + 中文翻译），英文句子里把该单词挖空，用户填空作答。比死记硬背的四关更接近真实语境记忆。

### 触发规则

- **错词 / 到期复习词**：只要本次会话中这个词出现过一次错误（任意一关答错触发过 `requeueWithError`），或者它本来就是 `isReview === true` 的到期复习词，那么它在**四关全部通过后**，必定额外插入一次挖空题（触发概率 100%）。
- **新词（本次会话首次学习、从未错过）**：以较低概率额外触发一次挖空题，默认概率 **15%**，做成配置项（比如 `progress.json` 或单独 config 里的 `clozeProbabilityNewWord`），方便后续调整。
- 挖空题本身不计入该词的 `wrongCount`（不影响 SM-2 评分），单独统计对错，用于日后可能的功能扩展，但不参与当前评分公式。

### 插入位置规则

- **不允许打断同一个词的"四关一组"内部顺序**（翻转 → 看英选中 → 看中选英 → 拼写必须连续完成）。
- 挖空题作为独立卡片，只能插入在**不同词的四关组之间**，即某个词四关全部做完之后，下一个词四关开始之前的位置。
- 具体做法：在原有 `finalizeWord()` 判定要不要触发挖空题后，如果触发，把一张 `{type: 'cloze', word: ...}` 的卡片插入到 `queue` 的最前面（下一张就是它），而不是又混进某个词自己的四步 stage 数组里。

### 内容生成：DeepSeek API

- **模型**：`deepseek-v4-flash`，非思考模式（no thinking，纯生成任务不需要推理），2026 年目前最便宜的可用模型，参考定价 cache-miss input $0.14/1M、output $0.28/1M（[DeepSeek 定价](https://deepseek.ai/pricing)）。
- 旧的模型别名 `deepseek-chat` / `deepseek-reasoner` 已在 2026-07-24 下线，务必用新模型名 `deepseek-v4-flash`，并在请求体里显式关闭 thinking（不要用会路由到 thinking 模式的旧别名）。
- **API Key 配置**：不要硬编码在 HTML/JS 里（会被打包进静态文件，不安全）。建议：
  - 在 `90-ReviewApp/` 下建一个 `.env` 或 `config.local.json`（加入 `.gitignore`，不要提交到 Obsidian 的 git 同步）
  - 由于最终产物是纯前端单文件 HTML（没有服务器），直接在浏览器里调 DeepSeek API 需要把 key 暴露给前端 JS——这是可接受的（本地单人使用，不发布），但仍建议 key 从本地配置文件读取后再注入到生成的 HTML 里（跟当前"当日词表 JSON 注入 HTML"的做法一致），不要把 key 提交进版本库
- **Prompt 设计建议**：
  - 输入：单词、词性、中文释义
  - 输出要求：一句包含该单词的英文例句（长度适中，CET6 难度，不要比单词本身更难的生僻搭配）+ 对应中文翻译；返回结构化 JSON（如 `{sentence_en, sentence_zh}`），前端把 `sentence_en` 里的目标单词替换成 `____` 展示，作答后与原词比对（忽略大小写、可能的时态变化需要判断——建议先只做原型不变形式，用户自己判断）
- **缓存**：同一个词同一天没必要重复调用生成新句子（省 token、避免网络延迟卡住背词节奏）。建议缓存到 `90-ReviewApp/sync/cloze_cache.json`，key 为 `word`，命中就复用，除非用户手动要求换一句。
- **失败兜底**：API 调用失败或超时（比如没联网）不能卡住背词流程——直接跳过这次挖空题机会，正常进入下一张卡，不重试、不报错弹窗打断体验。

### 验收标准（新增部分）

1. 复习词 / 本次答错过的词，四关做完后必出一道挖空题；新词按配置概率（默认 15%）随机触发
2. 挖空题不会出现在某个词自己四关序列内部，只出现在词与词之间
3. 挖空句子来自 DeepSeek `deepseek-v4-flash`，同词同日不重复调用（走缓存）
4. API 不可用时静默跳过，不阻塞背词流程
5. 挖空作答对错计入导出的 session JSON（独立字段，不影响 SM-2 评分）

---

## Cloze 实现说明（2026-08-02，已实现）

新增文件：`build_review.py`（每日构建脚本）、`template.html`（页面模板）、`config.local.json`（密钥，已 gitignore）、`sync/cloze_cache.json`（例句缓存）。

**重要架构决策：例句在"构建期"用 Python 生成，不在浏览器运行时调用 DeepSeek。**
原因：最终产物是双击打开的 `file://` 单文件 HTML——浏览器直接 fetch DeepSeek API 会被 CORS 拦截，
且 `file://` 也读不了本地 `sync/cloze_cache.json`。所以流程是：
`build_review.py` 读 `config.local.json` 的 key → 调 `deepseek-v4-flash`（非思考模式）→ 生成双语例句写入缓存 →
把 `{word: {sentence_en, sentence_zh}}` 连同当日词表一起注入生成的 `review.html`。浏览器只渲染，零网络依赖。

**与任务书原文的一处差异**：任务书建议"key 注入生成的 HTML"。本实现**不注入 key**（构建期已生成好例句，浏览器不需要 key），
更安全。key 只存在于 `config.local.json`（已加入 `.gitignore`）。

**用法：**
- `python3 build_review.py`：正常构建（算当天到期复习词 + 游标起的 25 新词 → 写 `sync/day_YYYY-MM-DD.json` → 生成 `review.html`）
- `python3 build_review.py --mock`：用内置假例句离线演示/测试，不调 API
- `python3 build_review.py --output X.html --no-day-json`：只输出到指定文件，不覆盖 `review.html` 也不写 day JSON
- `--dry-run` / `--date YYYY-MM-DD` / `--cursor N` / `--seed N` / `--no-shuffle` 供测试与复现

**行为：**
- 无 key / 调用失败 / 例句未含原形词 → 该词静默跳过挖空题（浏览器端也不会出挖空卡，不阻塞流程）
- 同词同日不重复调用：`sync/cloze_cache.json` 以 `word` 为 key，命中即复用
- 挖空题只插在词与词的四关之间（`finalizeWord` 里 `queue.unshift`），不打断四关；对错记入导出的 `results[].cloze`，
  不影响 SM-2 评分
- `template.html` 是模板源文件，`review.html` 是构建产物（用户正在用旧版学习时不要覆盖，等其导出后再构建）

**游标约定**：`build_review.py` **不推进** `progress.json` 的 `cursor_index`；只有同步脚本在确认用户导出并同步回笔记后才推进。

**游标语义（重要，2026-08-03 修正）**：`cursor_index` 是**全字母序的 S-位置**（全部词按 `word` 字母序排序后的稳定下标），**不是**"当前新词列表的下标"。示例：`abandon` 是 S-位置 0 的复习词；Day 1 新词 abnormal~accumulate 占 S-位置 1-25；Day 2 从 S-位置 26（accurate）起取，到 adore（S-位置 50）。同步脚本按"本次同步的新词的最大 S-位置 + 1"推进游标。因此即使词库因同步而缩减、词的 new 状态变化，游标也**永不漂移**，不重复、不漏词。**教训**：如果按"新词序号 + 新词数"推进，Day 1 同步后新词整体前移 25 位，会跳过 accurate~adore 整批词（曾踩过此坑）。
