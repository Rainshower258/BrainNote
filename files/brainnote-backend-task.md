# BrainNote 前后端联动 — CC 任务书

## 任务目标

给已有的 `BrainNote.html` 前端接上真实后端，读取 Obsidian vault 里的 `.md` 笔记，替换掉 HTML 里的所有 mock 数据。

---

## 项目结构（目标）

```
Brain/                          ← vault 根目录（review.py 已在此）
├── review.py                   ← 已有，保留不动
├── server.py                   ← 新建：FastAPI 后端
├── BrainNote.html              ← 修改：替换 mock 数据为 API 调用
├── 10-Words/
├── 20-Concepts/
├── 30-Reviews/
└── 00-Templates/
```

---

## 第一步：安装依赖

```bash
pip install fastapi uvicorn python-frontmatter python-multipart
```

---

## 第二步：新建 `server.py`

实现以下 5 个接口：

### `GET /api/due`
返回今日待复习笔记列表（due <= 今天），按 interval 升序。

响应格式：
```json
{
  "count": 5,
  "cards": [
    {
      "id": "abandon",
      "type": "word",
      "word": "abandon",
      "phonetic": "/əˈbændən/",
      "word_type": "v. 动词",
      "answer": "放弃；抛弃",
      "example": "He abandoned the project halfway.",
      "tip": "",
      "mastery": "new",
      "interval": 1,
      "reviews": 0
    }
  ]
}
```

`tip` 字段对应笔记正文里「联想/记忆」那一行，解析不到就返回空字符串。

concept 类型的卡片：`word` 字段填文件标题，`phonetic` 和 `word_type` 返回空字符串。

### `POST /api/rate`
接收评分，更新 frontmatter。

请求体：
```json
{
  "id": "abandon",
  "type": "word",
  "rating": "good"
}
```

rating 取值：`again / hard / good / easy / perfect`

更新逻辑复用 `review.py` 里的 `compute_next()` 函数（直接 import）。

响应：
```json
{"ok": true, "next_due": "2026-06-04", "next_interval": 2}
```

### `GET /api/stats`
返回掌握度分布和 streak。

响应格式：
```json
{
  "total": 223,
  "distribution": {
    "new": 14, "again": 3, "hard": 9,
    "good": 42, "easy": 67, "perfect": 88
  },
  "due_today": 5,
  "streak": 7,
  "heatmap": {
    "2026-06-01": 8,
    "2026-06-02": 5
  }
}
```

`streak` 计算方式：从今天往前数，连续有复习记录（last-review 字段）的天数。

`heatmap`：过去 26 周内，每天复习的笔记数量（以 last-review 日期统计）。

### `GET /api/today-date`
返回今日日期字符串，供前端显示。

```json
{
  "weekday_cn": "周二",
  "date_cn": "6月2日",
  "weekday_en": "TUESDAY"
}
```

### `POST /api/import`
接收纯文本单词列表（每行一个），批量创建笔记。

请求体：`Content-Type: text/plain`，body 就是单词列表。

复用 `review.py` 里的 `cmd_import()` 逻辑。

响应：
```json
{"created": 10, "skipped": 2}
```

### CORS 配置

允许 `*` origin（本地开发用）：

```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
```

### 静态文件服务

直接用 FastAPI 托管 `BrainNote.html`：

```python
from fastapi.responses import FileResponse
@app.get("/")
def index():
    return FileResponse("BrainNote.html")
```

启动命令：
```bash
cd ~/Brain
uvicorn server:app --reload --port 8765
# 访问 http://localhost:8765
```

---

## 第三步：修改 `BrainNote.html`

### 3.1 替换 DATA 区块

找到 `/* ===================== DATA ===================== */` 区块，把静态 `WORDS` / `MASTERY` 数组全部删掉，改成：

```javascript
/* ===================== DATA ===================== */
const API = 'http://localhost:8765/api';
let WORDS = [];   // 从 /api/due 动态加载
const RATES = [
  {k:"again",cn:"重来",cls:"r-again"},
  {k:"hard",cn:"困难",cls:"r-hard"},
  {k:"good",cn:"良好",cls:"r-good"},
  {k:"easy",cn:"简单",cls:"r-easy"},
  {k:"perfect",cn:"完美",cls:"r-perfect"}
];
```

### 3.2 启动时加载数据

在 `/* ===================== INIT ===================== */` 区块替换为：

```javascript
/* ===================== INIT ===================== */
async function init() {
  // 加载日期
  try {
    const d = await fetch(`${API}/today-date`).then(r => r.json());
    document.getElementById('todayDate').innerHTML =
      `${d.weekday_cn}<br>${d.date_cn}<small>${d.weekday_en}</small>`;
  } catch(e) {}

  // 加载统计
  await loadStats();
}

async function loadStats() {
  try {
    const s = await fetch(`${API}/stats`).then(r => r.json());
    // streak
    document.getElementById('streakNum').textContent = s.streak;
    document.querySelectorAll('.streak-copy-num').forEach(el => el.textContent = s.streak);
    // due count
    document.getElementById('dueCount').textContent = s.due_today;
    // mastery badges
    const MASTERY = [
      {cls:'b-new',   lbl:'新词',  key:'new'},
      {cls:'b-again', lbl:'重来',  key:'again'},
      {cls:'b-hard',  lbl:'困难',  key:'hard'},
      {cls:'b-good',  lbl:'良好',  key:'good'},
      {cls:'b-easy',  lbl:'简单',  key:'easy'},
      {cls:'b-perfect',lbl:'完美', key:'perfect'},
    ];
    document.getElementById('badgeRow').innerHTML = MASTERY.map(m =>
      `<div class="badge ${m.cls}"><span class="bnum">${s.distribution[m.key]||0}</span><span class="blbl">${m.lbl}</span></div>`
    ).join('');
    // heatmap（传入真实数据）
    buildHeatmap(false, s.heatmap);
  } catch(e) {
    console.error('stats load failed', e);
  }
}

init();
```

### 3.3 修改 `startReview()`

```javascript
async function startReview() {
  // 加载今日待复习
  const res = await fetch(`${API}/due`).then(r => r.json());
  WORDS = res.cards;
  if (WORDS.length === 0) {
    alert('今日无待复习！');
    return;
  }
  idx = 0; setFlip(false); renderCard();
  Object.keys(tally).forEach(k => tally[k] = 0);
  startTime = Date.now();
  show('review');
}
```

### 3.4 修改 `rate()` 函数

在 `tally[k]++` 之后，加上 API 调用：

```javascript
// 提交评分到后端
const card = WORDS[idx];
fetch(`${API}/rate`, {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({id: card.id, type: card.type, rating: k})
}).catch(e => console.error('rate failed', e));
```

### 3.5 修改 `buildHeatmap()` 签名

原来是 `buildHeatmap(todayFilled)`，改为接受真实数据：

```javascript
function buildHeatmap(todayFilled, realData = {}) {
  // ...原有逻辑不变...
  // 替换 lvl 计算部分：
  let lvl = 0;
  if (!isFuture) {
    const dateStr = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    const count = realData[dateStr] || 0;
    if (isToday && todayFilled) lvl = 4;
    else if (count >= 20) lvl = 4;
    else if (count >= 10) lvl = 3;
    else if (count >= 5)  lvl = 2;
    else if (count >= 1)  lvl = 1;
    else lvl = 0;
  }
  // today class 也改一下：
  let cls = 'heat-cell' + (lvl ? ` l${lvl}` : '') +
    (isToday ? ' today' : '') + (isFuture ? ' future' : '');
}
```

### 3.6 完成页更新后刷新统计

在 `finish()` 函数末尾加：

```javascript
// 刷新 dashboard 统计（回到首页时数据是最新的）
loadStats();
```

---

## 第四步：验证清单

```bash
# 1. 启动服务
cd ~/Brain && uvicorn server:app --reload --port 8765

# 2. 测试接口
curl http://localhost:8765/api/stats
curl http://localhost:8765/api/due
curl -X POST http://localhost:8765/api/rate \
  -H "Content-Type: application/json" \
  -d '{"id":"abandon","type":"word","rating":"good"}'
curl http://localhost:8765/api/today-date

# 3. 打开浏览器
open http://localhost:8765

# 4. 验证
# - Dashboard 显示真实 streak、due 数量、掌握度分布
# - 点"开始复习"加载真实待复习单词
# - 评分后对应 .md 文件的 frontmatter 已更新（mastery/due/interval）
# - 完成复习后 Dashboard 数据刷新
```

---

## 注意事项

- `server.py` 里的 `VAULT` 路径自动取 `server.py` 所在目录，确保文件放在 vault 根目录。
- `tip` 字段解析：读取笔记正文，找「联想/记忆」或「联想」标题后的第一行非空文本。
- `streak` 计算：只统计 `last-review` 字段，新笔记（未复习过）不计入。
- 热力图用真实 `heatmap` 数据后，`buildHeatmap` 里的伪随机逻辑可以完全删掉。
