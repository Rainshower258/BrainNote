# Cloze 端侧生成 — 部署说明与已知限制

> 目的：几个月后回来能直接看懂，不用重新摸索。遇到"怎么又变慢了/又崩了"先来查这份。

## 一句话总结

挖空题生成默认走本地 llama-server（Qwen3.5-2B），失败自动 fallback 到 DeepSeek API 或已有缓存。
两台机器分工：**平板 = 生产/全量**，**Mac = prompt 迭代/质量实验**。代码在 `build_review.py`
（`call_local` / `call_deepseek` / `build_cloze_map`），配置在 `config.local.json`
（`cloze_backend` 字段切换，不走 git）。

## 两台机器的角色

| | 平板 (TB-J716F) | Mac (M5 MacBook Air) |
|---|---|---|
| 用途 | 日常 30 词生成、2345 词全量重生成 | prompt 改动、模型选型这类要盯着结果调的实验 |
| 特点 | 高吞吐、没人等，插电挂着跑 | 低延迟、小批量，人在等结果 |
| 硬件 | 骁龙870，纯 CPU 推理 | Apple Silicon，Metal GPU 加速 |
| 实测速度 | decode ~13-24 tok/s（视 build 而定，见下） | decode ~73 tok/s |
| llama-server build | 官方 pkg 包（`pkg install llama-cpp`，Termux） | Homebrew（`brew install llama.cpp`） |

两边模型文件必须是**同一个 GGUF**（已用 md5 核对一致：`6899b2510c7b0c480730d48c3117bd32`），
放在各自的 `~/models/qwen3.5-2b-q4_k_m.gguf`。prompt 模板在 `build_review.py` 里，两边跑的是
同一份 git 同步的代码，天然一致——**不要为了"效果不一样"去怀疑模板，先确认两边代码版本一致**
（`git log -1`），模板本身没有单独的版本管理。

## 为什么这么分工

一开始想在平板上把生成速度榨到最优（编译优化、并行 slot 等），后来发现这个方向本身没抓手：
100 词批量在平板上要 7-8 分钟，这是"人在等"场景下的痛点；但真实需求里，人在等的只有日常
30 词（几分钟可接受）和 prompt 调试（几个词，MacBook 秒回）。100 词/2345 词全量重生成从来
不需要人守着，扔平板上插电跑，跑多久都无所谓。分开之后，平板不需要为速度继续优化，Mac
也不需要迁就平板的 CPU 限制。**如果以后又想"让平板更快"，先问一句：这个场景到底需不需要人等。**

## llama-server 启动命令

### 平板（生产，`~/.termux/boot/06-llama-server.sh`，开机自启）

```bash
llama-server -m ~/models/qwen3.5-2b-q4_k_m.gguf -t 4 -c 2048 --port 8901 --reasoning off
```

| 参数 | 值 | 为什么 |
|---|---|---|
| `-t` | `4` | 骁龙870是4大核(A77)+4小核(A55)。默认(`-1`/`8`)会连小核一起用，实测 decode 直接腰斩(17.9→9.5 tok/s，跌47%)，纯粹拖后腿。**不要试图用满8线程"提高吞吐"** |
| `-c` | `2048` | 单轮生成一两句话，不需要更大上下文；调大只会白占内存 |
| `--reasoning off` | 关闭 | Qwen3.5 默认走 thinking 模式，会把整个 token 预算烧在 `<think>` 块上，产不出正文（实测烧完100 token还没出正文）。**这个模型系列必须显式关，别的模型不一定需要** |
| build | pkg 版 | 见下面"已知限制"第一条，不要换成自己编译的 dotprod 版 |

### Mac（迭代实验，手动按需启动，不常驻）

```bash
llama-server -m ~/models/qwen3.5-2b-q4_k_m.gguf -c 2048 --port 8901 --reasoning off
```

不用管 `-t`（Apple Silicon 没有平板那种大小核拖后腿问题，Homebrew 装的默认配置直接够用）。
用完可以直接杀掉，不需要像平板那样开机自启——这是交互式用的，不是常驻服务。

## 代码里的 backend 切换（`build_review.py` + `config.local.json`）

```json
{
  "cloze_backend": "local",
  "local_base_url": "http://127.0.0.1:8901",
  "local_model_tag": "local-qwen35-2b",
  "local_timeout_sec": 20
}
```

- `cloze_backend: "local"`（默认）：先试本地 `call_local()`，连不上或重试 3 次都没通过校验 →
  自动 fallback 到 `call_deepseek()`（需要 `deepseek_api_key`）→ 还是不行才静默跳过该词
- `cloze_backend: "deepseek"`：跳过本地，直接走原来的 DeepSeek 路径（应急用，比如本地服务
  长期起不来又懒得修的时候）
- **本地模型是可替换的内容生成组件，不是系统的一部分**：它不参与 SM-2 调度（那是
  `sync_session.py` 的事），只负责把选中的词包装成挖空句子；它挂了要能退回 API/缓存，
  不能让背词流程瘫掉——这条约束已经在 fallback 链路里体现了，不要在别的地方加本地模型的
  调用点

`sync/cloze_cache.json` 里新写入的条目会带 `source` 字段（`"local-qwen35-2b"` 或
`"deepseek"`）；老条目（DeepSeek 时代生成的）没有这个字段，不用补，靠"有没有 source 字段"
就能分辨新旧。想批量对比质量或重新生成，按 `source` 字段筛就行。

`config.local.json` 不走 git（含 API key），两台机器各自维护一份，字段名保持一致。

## 已知限制（踩过的坑，别重踩）

1. **自己编译的 dotprod build（`~/llama.cpp/build-noomp/`）跟 Qwen3.5-2B 不兼容，长 prompt
   会让服务器直接崩溃（SIGSEGV，日志戛然而止无报错）。生产环境用 pkg 版，不要手滑换成
   noomp 版。** 崩溃只在"noomp build × Qwen3.5-2B × 长prompt"三者叠加时出现——noomp 单独配
   Qwen2.5-1.5B 没事，pkg 版配 Qwen3.5-2B 也没事。没深挖到底是 dotprod kernel 的哪个具体环节
   出问题，限时排查过（试了去掉 `+fp16` 只留 `+dotprod`、查 min-step 参数，都没解决，也没
   打算继续深挖），当前策略是绕开，不是修好了。三份 build 都还在（pkg / dotprod+OpenMP /
   dotprod+noOpenMP），留着对照用，生产只认 pkg。

2. **在 Android/Termux 上自己编译 llama.cpp，必须 `-DGGML_OPENMP=OFF`。** 默认编译会带
   OpenMP，实测拖累 pp 31%、tg 36%（pp: 73.0→50.5 tok/s，tg: 23.8→15.2 tok/s）——**关键是
   `OMP_NUM_THREADS` 环境变量根本调不动这个问题**，试过设 4、设 8、不设，三者几乎完全一样
   （tg 全部卡在 15.0-15.2），说明运行时线程数不是这个问题的杠杆，必须在编译期彻底关掉
   OpenMP 才有效。（这条只影响自己编译的场景；pkg 版本身就没有 OpenMP，不受影响。）

3. **`-t 8`（或不设，让它默认吃满所有核）会让 decode 腰斩**（17.9→9.5 tok/s，跌 47%），
   骁龙870的4个 A55 小核拖后腿——必须显式 `-t 4`。这条前面表格提过，这里再强调一次因为
   代价最惨。

4. **前缀缓存在 Qwen3.5-2B 上命中率明显偏低**（`cache_n` 稳态约 15，Qwen2.5-1.5B 上同样的
   prompt 设计能到 60-70+）。**排查清楚了根因，写下来是为了不要走弯路重新怀疑 prompt 结构
   或 tokenizer**：
   - 一开始怀疑是"目标词该放末尾"这个 prompt 设计本身失效了——**验证过不是**，直接对两个
     不同词的完整渲染 prompt 做 token 级 diff，真实的最长公共前缀是 68 个 token（覆盖了整段
     固定指令，跟设计预期完全一致）
   - 再怀疑是 tokenizer 的 BPE 合并边界问题——**也不是**
   - 真正原因：llama-server 自己的 context checkpoint 机制只在处理第一个请求时于 token 位置
     15 和 86 这两个偶然的 I/O 处理边界上保存了可复用的 checkpoint，第二个请求虽然真实重合到
     68，但只能复用离它最近且不超过它的 checkpoint（15），15 到 68 之间那部分本来能省的计算
     被浪费了
   - 试过修：查了 `--checkpoint-min-step`（默认 8192，改成 0）没用；确认了客户端请求本来就
     是一次性发送、非 chunked（`curl -v` 验证过 `Content-Length` 完整一次写入），所以"消除
     两阶段网络读取"这个方向根本没有可改的东西——问题在服务端任务队列调度，不在客户端
   - **结论：接受这个限制，不要再因为看到 cache_n 低就去改 prompt 结构或加分隔符**，那两个
     方向都已经证明是错的诊断

5. **两个 build（pkg vs 自编译）对同一个 prompt、同样的 seed、temperature=0 会给出完全不同
   的句子。这是预期行为，不是数值损坏。** 已经用 `llama-perplexity` 在同一语料上做过对照
   （pkg: PPL=13.6182±0.264，noomp: PPL=13.5966±0.263，差异 0.16%，在噪声范围内），确认两
   边 kernel 数值上都健康，只是 dotprod 的 SDOT 路径和通用 NEON 路径累加顺序不同，贪婪解码
   在 argmax 边界上把浮点尾差放大成完全不同的句子。**看到两个 build 输出不一样不用慌**，
   但也不要用"温度0+同seed логит应该完全一致"这种标准去验证 kernel 是否正确——这个标准
   对不同 kernel 实现本来就不成立。

6. **本地生成能通过精确原形校验，但校验不出词性用法错误**（比如实测过 "placebo" 这个名词
   被用成动词 "to placebo his pain"）。当前的校验只查"目标词的精确原形出现且仅出现一次 +
   长度/首尾格式"，不检查语法/搭配/语域是否地道。想要更严格的质量把关，得靠人工抽查或另外
   接一层评审（比如用 DeepSeek 当"可疑句筛选器"，之前讨论过设计但没做，需要的话从这个
   已知限制展开）。

## 回退到纯 DeepSeek API

改 `config.local.json`：

```json
{ "cloze_backend": "deepseek", ... }
```

或者更彻底一点：不装/不跑本地 llama-server，`call_local` 连不上会自动 fallback，效果一样
（区别只是 `cloze_backend: "local"` 每次都要先等一次本地超时才 fallback，`"deepseek"` 直接
跳过这个等待）。两条路都不需要改代码，`build_review.py` 不用动。
