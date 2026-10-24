# Paper 学习进度

> 掌握度：⚪0 未见 · 🔵1 读过 · 🟢2 能讲 · 🟠3 能推导 · 🔴4 能写代码（只凭证据升级）
> 图谱：打开关系图谱，搜索框填 `path:50-Papers` 只看技术树；颜色 = level（灰→蓝→绿→橙→红），紫色 = 论文。

## 总览

```dataviewjs
const cs = dv.pages('"50-Papers/concepts"').where(p => p.type === "paper-concept");
const icon = ["⚪", "🔵", "🟢", "🟠", "🔴"];
const names = ["未见", "读过", "能讲", "能推导", "能写代码"];
const n = cs.length;
const counts = [0, 1, 2, 3, 4].map(l => cs.where(p => (p.level ?? 0) === l).length);
const score = cs.array().reduce((s, p) => s + (p.level ?? 0), 0);
const pct = n ? Math.round(score / (n * 4) * 100) : 0;
const bar = "█".repeat(Math.round(pct / 5)) + "░".repeat(20 - Math.round(pct / 5));
dv.paragraph(`**总掌握度** ${bar} ${pct}%（${n} 个概念，满分 = 全部能写代码）`);
dv.table(["等级", "数量"], counts.map((c, l) => [`${icon[l]} ${l} ${names[l]}`, c]));
```

## 技术树（按深度，0 = 最底层地基）

```dataviewjs
const cs = dv.pages('"50-Papers/concepts"').where(p => p.type === "paper-concept");
const icon = ["⚪", "🔵", "🟢", "🟠", "🔴"];
const maxD = Math.max(...cs.array().map(p => p.depth ?? 0));
const rows = [];
for (let d = 0; d <= maxD; d++) {
  const layer = cs.where(p => (p.depth ?? 0) === d).sort(p => p.file.name);
  if (layer.length === 0) continue;
  const done = layer.where(p => (p.level ?? 0) >= 2).length;
  rows.push([d, `${done}/${layer.length}`, layer.map(p => `${icon[p.level ?? 0]} ${p.file.link}`).join(" · ")]);
}
dv.table(["深度", "≥能讲", "概念"], rows);
```

## 下一批候选（level ≤ 1 且前置全部 ≥ 2，按深度）

```dataviewjs
const cs = dv.pages('"50-Papers/concepts"').where(p => p.type === "paper-concept");
const lvl = l => { const pg = dv.page(l.path ?? String(l).replace(/^\[\[|\]\]$/g, "")); return pg ? (pg.level ?? 0) : 0; };
const ready = cs
  .where(p => (p.level ?? 0) <= 1)
  .where(p => (p.prereqs ?? []).every(l => lvl(l) >= 2))
  .sort(p => p.depth ?? 0);
dv.table(["概念", "深度", "当前", "类型", "地基资源"],
  ready.map(p => [p.file.link, p.depth, p.level ?? 0, p.kind === "paper" ? "📄 论文" : "📘 微课", p.resource]));
```

## 论文

```dataviewjs
const ps = dv.pages('"50-Papers/papers"').where(p => p.type === "paper").sort(p => p.started, "desc");
const cs = dv.pages('"50-Papers/concepts"').where(p => p.type === "paper-concept");
dv.table(["论文", "主/支线", "状态", "当前会话", "复现", "相关概念 ≥能讲"],
  ps.map(p => {
    const rel = cs.where(c => (c.papers ?? []).some(l => (l.path ?? String(l)).includes(p.file.name)));
    const ok = rel.where(c => (c.level ?? 0) >= 2).length;
    return [p.file.link, p.track === "main" ? "主线" : "支线", p.status, p.session, p.repro, `${ok}/${rel.length}`];
  }));
```

## 最近证据

```dataviewjs
const cs = dv.pages('"50-Papers/concepts"').where(p => p.type === "paper-concept");
const ev = [];
const day = d => d?.toFormat ? d.toFormat("yyyy-MM-dd") : String(d ?? "");  // Dataview 会把日期字符串解析成 DateTime
for (const p of cs) for (const e of (p.evidence ?? [])) ev.push([day(e.date), p.file.link, e.session ?? "", [e.quiz ?? e.code, e.note].filter(Boolean).join(" · ")]);
ev.sort((a, b) => b[0].localeCompare(a[0]));
if (ev.length === 0) dv.paragraph("还没有证据记录。做完诊断测验并同步后这里会出现。");
else dv.table(["日期", "概念", "会话", "证据"], ev.slice(0, 20));
```
