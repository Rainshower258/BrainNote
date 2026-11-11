# 单词读音（2026-11-11）

每日构建自动准备当天单词的读音。先复用本地缓存，缺失时依次尝试：

1. Cambridge 词典中与词头、首义项词性匹配的英音/美音录音。
2. Free Dictionary API 提供的词典音源；仅接受精确词条，多读音时核对词卡音标。当前网络下其部分音频下载会返回 502，失败时继续回退。
3. MiMo `mimo-v2.5-tts`，固定英文音色 `Mia`，只朗读单词；提示词带首义项词性及已有音标参考。

词卡同时列出多种词性时，按首义项选音，不将名词读音套给动词。音频来源、词性、音标、时长、获取时间保存在本机索引，方便逐词核对。词典缺失时，生成读音仍有模型出错的可能；不能用“成功返回音频”或语音转写结果作为发音完全正确的证明。

## 播放方式

- 每次打开或刷新默认静音，点击“开启读音”后播放。
- 遮词卡片、看英选中：入卡播放一次；翻面不重复播。
- 看中选英、拼写：提交答案后播放一次，答错也播；答前禁止重播，不提前提示答案。
- 答后等待读音结束再切卡，播放失败或浏览器拒绝播放不影响答题。
- 需要时可以手动重播；切卡、关闭读音、页面转入后台时停止旧音频。
- 挖空题不自动朗读目标词，避免泄露答案。

## 本地存储

音频位于 `90-ReviewApp/.audio_cache/`，已加入 Git 忽略。生成的 `review.html` 只包含相对文件路径，不嵌入音频数据或密钥。HTML 和普通背词记录可以继续提交到 GitHub，音频及本机索引不会上传。离开本机或只复制 HTML 时不会自带声音。

每词各关共用一个文件；缓存身份包含词头、首义项词性、音标和合成模型/音色版本。新词、复习词统一按是否命中缓存处理。

使用 ffmpeg 解码并转为单声道、24 kHz、32 kbps MP3；拒绝不可解码或时长异常的响应。默认音频缓存上限 **100 MiB（配置单位 MB，按 1024×1024 字节计算）**。新页面成功写出后，超限才淘汰最久未用的音频，保护当前词表引用；不每天清空历史音频。当前词表只有最多 30 个短音频，远低于上限。

## 配置与命令

依赖现有 Python `python-frontmatter` 和系统 `ffmpeg`、`ffprobe`。`--dry-run` 不请求音源，`--mock` 完全离线且不构建音频。

私有配置 `config.local.json`（已 Git 忽略）：

```json
{
  "audio_enabled": true,
  "audio_cache_max_mb": 100,
  "mimo_api_key": "在本地填写，也可使用 MIMO_API_KEY 环境变量",
  "mimo_tts_model": "mimo-v2.5-tts",
  "mimo_tts_voice": "Mia"
}
```

- 日常仍运行 `python3 build_review.py --date YYYY-MM-DD`。
- `--no-audio`：本次跳过音频，保留普通背词功能。
- 在同一天补声音、保留 day JSON：`python3 build_review.py --date YYYY-MM-DD --no-day-json`。生成器会重新排列网页词序，但同一词集的已有浏览器进度仍可按词 ID 恢复。正在答题时不要重新生成页面。
- 已有可用音频直接复用；没有 MiMo key 时仍可以使用词典和缓存，缺音频不阻塞文字练习。

## 当前设备状态

用户 2026-11-11 确认以 Mac 为主要背词设备，TB-J716F 平板基本不用，VPS 隧道已停止；平板端自身配置没有改动。本次无需恢复隧道或给平板同步音频，也没有操作平板配置。

## 验证

`python3 -m unittest discover -s tests -v` 覆盖词性/音标与缓存身份、同形异音词选音、词典失败回退、缓存命中、超限淘汰与当前文件保护、离线模式和伪音频拒绝。

还使用独立的静音 Chrome 会话验证四关播放时机、错误恢复、等待播完、进度恢复、成绩导出与本地 MP3 解码。测试未导出学习成绩至 Downloads，也未播放可听声音。

参考：[Cambridge 词典](https://dictionary.cambridge.org/dictionary/english/record)、[Free Dictionary API](https://dictionaryapi.dev/)、[MiMo TTS API](https://mimo.mi.com/docs/en-US/api/audio/tts-post)。
