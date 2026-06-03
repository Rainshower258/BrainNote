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
