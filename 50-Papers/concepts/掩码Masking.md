---
type: paper-concept
level: 0
depth: 7
prereqs:
- '[[自回归生成]]'
- '[[softmax]]'
papers:
- '[[Attention Is All You Need]]'
kind: paper
resource: 本论文 §3.2.3
evidence: []
tags:
- paper-concept
- level/0
---

# 掩码Masking

把不允许看的位置（如未来的词）在 softmax 前设为 -∞，使其权重为 0。

## 地基资源
- 本论文 §3.2.3

## 我的理解
（学完后用自己的话写）

## 证据记录
（测验 / 推导 / 代码跑通，由会话同步写入 frontmatter.evidence）
