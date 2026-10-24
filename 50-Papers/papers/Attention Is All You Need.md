---
type: paper
title: Attention Is All You Need
authors: Vaswani et al. (Google Brain / Google Research)
year: 2017
arxiv: "1706.03762"
track: main
role: 地图（起点）
status: in-progress
session: S0
repro: toy
folder: /Users/sun/Desktop/learning/文献/paper read/2026-10-24_attention/
started: 2026-10-24
finished: ""
tags: [paper]
---

# Attention Is All You Need

**一句话**：不用循环、不用卷积，只靠注意力做序列转换的 Transformer；今天所有大语言模型的骨架。

**本地材料**（不进 vault）：`文献/paper read/2026-10-24_attention/`
- `01_导读.md` 逐段中文导读（"§节 ¶段"对照 PDF）
- `02_结构拆解.md` 章节地图 / 公式表 / 图表表 / 依赖树 / 复现档位
- `S0_诊断与地图.html` 诊断测验

## 依赖的概念
本论文拆出的全部概念见 [[dashboard]]；顶点是 [[Transformer]]。

## 会话记录
| 会话 | 日期 | 内容 | 产出 | 证据 |
|---|---|---|---|---|
| S0 | 2026-10-24 | 抓原文、导读、结构拆解、依赖树、诊断 | 01/02 md、S0 html、首批 10 词 | 待交回诊断 JSON |

## 会话计划（暂定，诊断后调整）
- S1 缩放点积注意力（Figure 2 左）：Q/K/V、点积、缩放、softmax、加权求和
- S2 多头注意力 + 掩码（Figure 2 右）：形状流转 512→8×64→512
- S3 编码器/解码器整体 + 位置编码 + Table 1（为什么能并行）
- S4 训练（Adam、学习率预热、Dropout、标签平滑）+ Table 3 消融
- 地基补齐后：玩具复现（序列反转 Transformer，MPS）

## 总结
（读完后用自己的话写）
