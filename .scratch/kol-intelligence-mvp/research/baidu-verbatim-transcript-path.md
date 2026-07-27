# 百度视频逐字稿路径核验

**核验日期：** 2026-07-19
**范围：** 外部能力只核验百度第一方公开文档；未调用需鉴权接口，也未实测识别质量。另只读检查了用户已有的 Word 逐字稿，用来确认当前产物确实包含未经摘要替代的连续口语转写；不把它的 Word 样式或排版当作目标格式。
**需求定义：** 最终产物可以是“纪要 + 完整逐字稿”，也可以继续交付 Word；硬要求是完整逐字稿真实存在、与 AI 摘要清楚分区，不能被摘要替代。这里的“逐字稿”是服务商直接返回的 ASR 转写，不经过 AI 摘要、提纲生成、篇章规整或语气词删除。它不等于经人工校对后“逐字不差”的法律级文本。

## 结论

1. **百度网盘 AI 视频笔记里的“文稿笔记”不能单独充当逐字稿。** 官方接口把它归入“AI 智能笔记”，返回示例已经按章节重组，加入“本节内容主要介绍”“核心价值”“基于上述指标”等概括性表达、加粗判断和项目符号。官方没有承诺它逐句忠实于音频。因此，即使模板名叫“文稿笔记”，也不能满足“最终必须包含完整逐字稿”的验收条件；它可以作为独立纪要与真正的转写并存。
2. **Ticket 02 的主路径应改为百度语音技术的“音频文件转写 API”。** 它直接返回完整 `result` 和带 `begin_time` / `end_time` 的分段 `detailed_result`；可显式设置 `smooth_text=0`、`filter_sensitive=0`，避免文本顺滑、口语过滤和敏感词替换。中文视频优先试 `pid=80006`。
3. **百度网盘 AI 纪要的 `media_insight` 可以作为第二候选/质量对照。** 官方把 `transcription`、`ai_neat` 和 `ai_outline` 分成独立结果；示例展示 `ai_neat_enable=false`、`ai_outline_enable=false` 时仍有转写 JSON 和 SRT 下载链接。不过该页没有暴露关闭 ASR 文本顺滑的参数，所以若目标是尽量保留原始口语，证据弱于专用语音转写 API。
4. **HTTP API 路径本身不需要 OpenCLI 或浏览器，但它不能在公开参数中直接引用个人百度网盘私有文件。** `media_insight` 只接受可直接下载的 `media_url`，没有 `fsid`、个人网盘 path 或“从当前百度账号选择文件”的参数。如果要求零搬运地复用已经在个人网盘中的文件，应走百度网盘消费者页面自身的转写功能；如果要求确定性 API，则仍需提供外部可下载 URL。
5. **Word、JSON、SRT 都只是容器，内容完整性才是验收对象。** 建议保留原始响应 JSON 作为机器证据，同时把完整转写确定性渲染成 Word 供用户使用；SRT、Markdown、纪要和下游投资判断都是并列或派生产物。任何纠错、去口头禅或摘要都不能覆盖完整转写。

## 1. 为什么“文稿笔记”不是本需求中的逐字稿

“创建视频 AI 笔记任务”接口说明，它会“自动解析视频内容并生成 AI 智能笔记”，而不是承诺返回原始语音识别结果。输入是公网可下载的视频直链，支持 mp4、mov、flv、mpeg、avi、mkv、wmv，视频至少 15 秒且画面中要有人物发言；接口为付费功能、使用 API Key，每用户每分钟只支持调用一次。
官方来源：[创建视频 AI 笔记任务](https://cloud.baidu.com/doc/qianfan-api/s/ymojidhhw)

查询接口把 `tpl_no=1` 命名为“文稿笔记”，但成功示例不是逐句文本：它包含人工文章式章节标题、加粗结论、项目符号和比较表，并出现“本节内容主要介绍”“核心价值在于”“基于上述指标”等概括性句式。这个示例足以证明该产物可能经过结构化和总结；官方也没有提供“关闭总结/规整”的开关或逐句 ASR 字段。
官方来源：[查询视频 AI 笔记任务](https://cloud.baidu.com/doc/qianfan-api/s/Hmojifdwo)

因此，Ticket 02 不应只凭“同名文稿 `.doc`”或 `tpl_no=1` 判断“逐字稿已取得”。Word 完全可以继续作为最终交付容器，但必须验证其正文确实包含完整、顺序一致的转写；文件名和产品模板名都不能替代内容契约。

## 2. 首选：音频文件转写 API（AASR）

百度语音技术的当前官方文档把该能力描述为“大批量的音频文件异步转写为文字”，通常在 12 小时内返回。请求与结果查询都是 HTTP API：

- 创建：`POST https://aip.baidubce.com/rpc/2.0/aasr/v1/create`
- 查询：`POST https://aip.baidubce.com/rpc/2.0/aasr/v1/query`

官方结果结构包括：

- `task_result.result`：完整转写结果；
- `task_result.detailed_result[].res`：分段文本；
- `begin_time` / `end_time`：每段起止时间，单位毫秒；
- `speaker_id`：仅 `pid=8953` 话者分离模型返回；
- `words_info`：官方标记为“预留参数，暂不启用”，因此标准接口不能承诺字粒度时间戳。

官方来源：[音频文件转写 API](https://cloud.baidu.com/doc/SPEECH/s/Klbxern8v)

为满足“不做 AI 二次整理”，首轮请求应明确记录以下参数，而不是依赖默认值：

```json
{
  "speech_url": "<public-download-url>",
  "format": "m4a",
  "pid": 80006,
  "rate": 16000,
  "smooth_text": 0,
  "filter_sensitive": 0
}
```

其中 `smooth_text=0` 表示不开启文本顺滑，`filter_sensitive=0` 表示不开启敏感词过滤。官方对极速版进一步解释，“文本顺滑”包含标点优化、数字格式优化和口语过滤；所以逐字稿路径必须关闭它。
官方来源：[音频文件转写 API](https://cloud.baidu.com/doc/SPEECH/s/Klbxern8v)、[音频文件转写极速版 API（邀测）](https://cloud.baidu.com/doc/SPEECH/s/Clhohwkbv)

### 标准 AASR 的输入与权限边界

| 项目 | 官方约束 |
| --- | --- |
| 鉴权 | `access_token`，由 API Key + Secret Key 获取；千帆 API 参考页也提供 Bearer API Key 调用形式 |
| 输入 | 公网可访问的音频 URL，URL 长度不超过 2048 字节 |
| 文件大小 | 不超过 500 MB |
| 格式 | mp3、wav、pcm、m4a、amr |
| 音频参数 | 单声道、16-bit；采样率固定 16000 Hz |
| 中文模型 | `80006` 为中文音视频字幕模型；`80001` 为中文近场；`8953` 为话者分离 |
| 返回时效 | 异步，官方表述为一般 12 小时内 |
| 查询批量 | 单次最多查询 200 个 task ID |
| 时长上限 | 当前标准接口文档未写明独立时长上限；不能自行推断为“一小时” |
| 计费/开通 | 按调用时长计费，支持预付时长包和后付费；余额/额度不足会暂停服务 |

官方来源：[音频文件转写 API](https://cloud.baidu.com/doc/SPEECH/s/Klbxern8v)、[千帆音频文件转写-提交任务](https://cloud.baidu.com/doc/qianfan-api/s/ym7wpcama)、[千帆音频文件转写-查询结果](https://cloud.baidu.com/doc/qianfan-api/s/tm84h4sot)、[语音识别价格](https://cloud.baidu.com/doc/SPEECH/s/Tldjm0i4c)

标准 AASR 不接受 mp4，因此本地只需从已有压缩视频提取 16 kHz、单声道、16-bit 的 m4a/wav/mp3，再上传到能生成公网下载 URL 的对象存储。对“只要逐字稿”的需求，这比把整段视频上传百度网盘更小、更直接。音频提取和 SRT 渲染均可本地确定性完成，不需要浏览器。

## 3. 次选：`media_insight` 的仅转写模式

百度网盘 AI 纪要 API 的创建参数把三个动作分开：基础转写、`ai_outline_enable`（AI 纪要）和 `ai_neat_enable`（篇章规整）。查询响应同样把结果分为：

- `transcription.transcription_script`：转写 JSON 下载链接；
- `transcription.transcription_srt`：字幕 SRT 下载链接；
- `ai_neat`：篇章规整结果；
- `ai_outline`：AI 纪要结果。

官方成功示例显示 `ai_neat_enable=false`、`ai_outline_enable=false`、`translation_enable=false`，同时 `transcription.status=300` 且返回 JSON/SRT 链接。这说明可以只做转写，不生成二次纪要。

建议请求显式写：

```json
{
  "media_url": "<public-download-url>",
  "language": "zh",
  "task_key": "<stable-source-id>",
  "ai_outline_enable": false,
  "ai_neat_enable": false
}
```

官方来源：[百度网盘 AI 纪要](https://cloud.baidu.com/doc/qianfan/s/rmir3o1bi)

限制：该页只要求 `media_url` 是音视频的公网直接下载链接，列出了中英日韩及部分方言；没有写文件大小、时长、格式上限，也没有公开 `smooth_text`/口语过滤开关。未写明的限制必须在小样本 spike 中实测，不能当作“无限制”。由于逐字稿要求强调保留原始口语，建议把此接口用于与 AASR 比质或在确实需要服务商原生 SRT 时使用，不作为默认主链路。

### 个人百度网盘文件并不是可直接传入的资源 ID

当前创建接口的公开请求结构只有 `media_url`，定义为“音视频外部下载链接 URL”；没有 `fsid`、个人网盘路径或百度网盘 OAuth 身份字段。由此只能确认它能拉取一个直接下载 URL，不能确认它会自动访问调用者“我的网盘”中的私有文件。个人网盘的播放页、文件列表页或普通分享页也不等于文件直链。
官方来源：[创建 AI 纪要任务](https://cloud.baidu.com/doc/qianfan-api/s/amoidh95l)、[百度网盘 AI 纪要](https://cloud.baidu.com/doc/qianfan/s/rmir3o1bi)

百度网盘开放平台可以另外通过 `fsid` 查询 `dlink`，但百度第一方答疑说明下载还需要携带 `access_token` 和指定 User-Agent。`media_insight` 没有提供自定义下载请求头的字段；把短期网盘凭证直接拼进 URL 还会带来过期、日志泄露和兼容性风险。因此“网盘 Open API 生成 dlink，再喂给 media_insight”只能作为隔离 spike 验证，不能当成已被官方支持的主方案。
第一方参考：[百度开发者中心文件下载示例](https://developer.baidu.com/question/detail.html?id=179)、[百度智能云关于 dlink 下载要求的答疑](https://cloud.baidu.com/ask/141)

## 4. 不作为默认方案：音频文件转写极速版

极速版能直接接收常见音视频格式，支持 `enable_subtitle=2` 返回字粒度时间戳，并可设 `smooth_text=0`。但官方明确标注为“邀测”，需申请测试；每个音视频最多 1 小时且整体不超过 500 MB，目前模型固定为 `dev_pid=80006`。长于一小时的视频必须切段，并处理拼接时间轴。因此它只有在权限已获批且确实需要字粒度时间戳时才优于标准 AASR。
官方来源：[音频文件转写极速版 API（邀测）](https://cloud.baidu.com/doc/SPEECH/s/Clhohwkbv)

## 5. 本地 Word 参考产物与推荐交付格式

已只读核对现有文件：

`/Users/bytedance/Downloads/小草/original_doc/20260628 大师班专场(晚18：00开播)-compressed.doc`

`file` 将其识别为 `Microsoft Word 2007+`；用 macOS `textutil` 只读导出文本后，可见正文是连续口语转写，保留“嗯嗯嗯”“呃”、重复和自我修正等口语痕迹，没有被结构化摘要替代。研究笔记不复制其正文内容。这个检查只证明当前产物符合“尽量不压缩原始信息”的内容方向；它的 Word 样式、标题和段落形态都不是必须复刻的 golden format。

官方 AASR 不直接导出 Word，但其 `result` 和 `detailed_result` 足以在本地确定性生成 Word：

1. 按 `begin_time` 排序全部分段；
2. 不删除、不重写 `res`，生成连续正文；
3. 可选加入段级时间戳和说话人标签；
4. 若同时提供纪要，把“AI 纪要”和“完整逐字稿”做成两个明确标题下的独立区域，完整逐字稿不能省略；
5. 推荐新产物使用标准 `.docx` 后缀；原始 JSON/SRT 作为旁路证据和可重建源，不要求用户把它们当最终阅读格式。

因此，**最终继续交付 Word 是可行且合适的**。但“生成了 Word”不是验收完成；还要校验每个原始 ASR 分段都按顺序进入 Word，并对开头/中段/结尾做原音抽检。

## 6. 浏览器与 OpenCLI 判断

这三组百度能力都有正式 HTTP endpoint、鉴权字段、任务 ID 和机器可读结果，但公开 API 与个人百度网盘消费者账号是两条不同的输入边界。因此：

- **不应先安装 OpenCLI。** 它无法提高 ASR 内容真实性，只会把账号会话、DOM 变化、下载命名和异步页面状态引入主链路。
- **若优先复用已经在个人百度网盘里的文件，浏览器页面路径有现实价值。** 它避免重新上传，但必须只把“完整文稿/转写”当证据输入；AI 纪要可以附带，不能替代逐字稿。Codex Chrome/Playwright 可先做一条真实文件的页面 spike。
- **若优先确定性和批处理，选择 API 路径。** 从本地视频抽音频并上传到能生成短期直链的对象存储，再调用 AASR；不要假设个人网盘文件路径可直接传给 `media_insight`。
- **两条路径不能静默互相回退。** 每次运行要记录究竟使用消费者页面还是 API，以及最终逐字稿来自哪一个任务。

## 7. 对 Ticket 02 的建议（本轮不修改 Ticket）

建议在实施前重写 Ticket 02 的核心合同：

1. 把“完整逐字稿”设为必需 child；“AI 纪要”可保留为可选的独立 child，但不能替代或截断逐字稿。
2. 主链路改为：本地提取合规音频 → 上传公共对象存储 → 创建 AASR task → 退避轮询 → 保存原始响应 → 确定性生成最终 Word。若保留纪要，在 Word 中单列纪要区和完整逐字稿区。
3. 对每个来源至少保存：
   - 源视频 SHA-256、音频 SHA-256、音频参数和时长；
   - API、模型 PID、`smooth_text=0`、`filter_sensitive=0`、task ID；
   - 原始 `task_result.json`（建议作为不可变机器证据）；
   - 从 `detailed_result` 确定性生成的最终 `.docx`，以及可选 `.txt` / `.md` / `.srt`；
   - 内容抽检记录，而不是仅凭任务成功码验收。
4. 验收中明确禁止：`ai_note`、`ai_outline`、`ai_neat` 或 LLM 清稿结果覆盖完整 ASR，以及只凭文件名判断逐字稿。纪要并非禁止，但必须与完整逐字稿区分。
5. 用最短真实视频做 bounded spike：抽听开头/中段/结尾，核对专名、数字、买卖方向和否定词；再在第二个真实视频重复。
6. 若用户要求的是“逐字不差”而不是“未经总结的 ASR”，则必须增加人工校对/听校环节。百度官方文档只承诺语音识别转写，不承诺零错误。

## 推荐决策

**先不安装 OpenCLI，也不把 AI 视频笔记的“文稿笔记”单独当成逐字稿。** 如果目标是零搬运地处理用户个人网盘中已有的视频，先用 Codex Chrome/Playwright 对百度网盘页面的“完整文稿/转写”做一条真实文件 spike；如果目标是稳定批处理，则用 AASR 的 `pid=80006 + smooth_text=0 + filter_sensitive=0`，接受额外的音频直链上传。`media_insight` 只接受外部下载 URL，不是“直接消费我的网盘文件”的公开 API。无论走哪条路，纪要都可以附加，但只有完整逐字稿通过内容覆盖检查才算成功。
