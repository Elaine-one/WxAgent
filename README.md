<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/协议-iLink_Bot-green.svg" alt="Protocol">
  <img src="https://img.shields.io/badge/LLM-多厂商-orange.svg" alt="LLM">
  <img src="https://img.shields.io/badge/License-GPL_3.0-blue.svg" alt="License">
</p>

# WxAgent

> 将任意 AI 大模型接入微信个人号，打造成运行在个人电脑上的**智能体底座**。

基于腾讯官方 iLink Bot 协议，纯 Python 实现。支持 DeepSeek、OpenAI、Claude、Qwen、智谱等主流大模型。无需 Node.js、无需 Docker、无需 GPU。

***

## 架构

```
┌──────────┐   微信消息    ┌──────────────────────────────────────────────────┐
│          │ ──────────→  │  channel/  微信通道层                             │
│  微信    │              │  client · receiver · sender · login · upload    │
│  客户端  │              │  session · message                               │
│          │ ←──────────  ├──────────────────────────────────────────────────┤
└──────────┘   回复消息    │  core/  核心引擎层                               │
                          │  graph (LangGraph 状态图) · dispatcher           │
                          │  agent_loop (legacy) · state · deps             │
                          │  nodes/  classify · react                       │
                          ├──────────────────────────────────────────────────┤
                          │  llm/  LLM 抽象层                                │
                          │  universal · router · fallback · streaming      │
                          │  format_openai · format_anthropic               │
                          ├──────────────────────────────────────────────────┤
                          │  tools/  工具层 (53 工具)                        │
                          │  registry · base · bridge · search              │
                          │  builtin/  file · code · system · system_control│
                          │  web · download · media · disk · batch          │
                          │  monitor · aria2 · feishu                       │
                          ├──────────────────────────────────────────────────┤
                          │  mcp_client/  MCP 协议层                         │
                          │  client · server · loader · transport · protocol│
                          ├──────────────────────────────────────────────────┤
                          │  memory/  记忆系统                                │
                          │  manager · short_term · long_term · retriever   │
                          │  indexer · conflict                              │
                          ├──────────────────────────────────────────────────┤
                          │  security/  安全体系                              │
                          │  path_sandbox · risk_levels · ai_reviewer       │
                          │  audit · data_border · sanitizer                 │
                          ├──────────────────────────────────────────────────┤
                          │  parsers/  文件解析器                             │
                          │  pdf · word · excel · image                     │
                          ├──────────────────────────────────────────────────┤
                          │  tasks/  异步任务 · scheduler/                   │
                          │  observability/  可观测性                        │
                          ├──────────────────────────────────────────────────┤
                          │  web/  管理面板                                   │
                          │  api (FastAPI) · frontend (React)                │
                          │  routes · services · schemas                    │
                          └──────────────────────────────────────────────────┘
                                   │                        ↑
                                   ↓                        │
                          ┌─────────────────────────────────────────┐
                          │            本地系统                      │
                          │  文件系统 / 命令行 / 浏览器 / 媒体       │
                          └─────────────────────────────────────────┘
```

### LangGraph 状态图（默认后端）

```
用户消息 → classify ──→ [new_task]  → react → [无需确认] → END（回复用户）
                    │                      ↓ [需确认]
                    │                wait_user → handle_confirm → react
                    ├──→ [confirm]  → handle_confirm → react
                    ├──→ [meta]     → handle_meta → END
                    └──→ [interrupt]→ handle_interrupt → react
```

- **classify**：LLM 自动判断消息类型（新任务 / 确认回复 / 中断 / 元命令）
- **react**：LLM 推理 + 工具调用循环
- **wait\_user**：危险操作需用户确认（Y/N），最多 3 轮
- **Checkpoint**：SQLite 持久化，支持跨消息中断恢复

### 数据流

```
用户发微信 "桌面有什么文件？"
        │
        ▼
  ① channel/receiver 收到消息 → 3秒防抖 + 去重
        │
        ▼
  ② core/dispatcher 分发 → classify 判断为 new_task
        │
        ▼
  ③ react 节点 → LLM 决定调用 list_directory 工具
        │
        ▼
  ④ tools/builtin/file 执行 os.listdir → 获取文件列表
        │
        ▼
  ⑤ 结果送回 LLM → LLM 生成自然语言回复
        │
        ▼
  ⑥ llm/streaming 智能分段 → channel/sender 发送回复到微信
```

***

## 功能

| 类别     | 能力                                                         |
| ------ | ---------------------------------------------------------- |
| 💬 对话  | 多轮自然语言对话，DeepSeek V4 思考模式，流式输出，长消息智能分段（480字+中文标点）          |
| 📁 文件  | 收发图片/视频/文档，CDN AES-128-ECB 加密传输；PDF/Word/Excel/图片解析        |
| 🔧 工具  | 53 工具（50 内置 + 3 桥接），覆盖文件/代码/系统/网络/下载/媒体/磁盘/批量/监控/飞书 11 大类                   |
| 🧠 记忆  | 短期对话压缩 + 长期 ChromaDB 向量记忆 + 偏好自动学习 + 混合检索                  |
| 🔒 安全  | 路径沙箱 + 命令风险分级 + AI 安全审查 + 审计日志 + 数据出境同意 + 剪贴板脱敏（6 层防护）                      |
| ⏰ 调度   | APScheduler 定时任务 + URL 变化监控 + Skill 场景模式（可预定义触发词+动作）               |
| 🎙 语音  | SILK→WAV→Whisper 自动转录，支持本地/云端双模式                           |
| 🔄 持久化 | Session 自动保存，断线重连无需重新扫码；LangGraph Checkpoint 中断恢复          |
| 👥 多用户 | 按微信用户 ID 隔离对话历史与记忆，互不干扰                                    |
| 🎯 路由  | 按模态/任务类型路由不同模型，主模型失败自动降级备用模型                               |
| 🖥 离线  | `--dry-run` 终端直接对话调试，无需微信连接                                |
| 📊 追踪  | LLM 调用次数、Token 消耗、USD 费用估算；元命令 /help /status /usage        |
| 🖥️ 面板 | Web 管理面板（FastAPI + React），13 个配置页面、服务启停、日志查看、工具管理、Skill 生成 |
| 🔌 MCP  | MCP 客户端/服务端双模式，动态加载外部工具服务器，Tool Search 桥接机制 |
| 🕊 飞书  | 19 个飞书内置工具，消息/文档/多维表格/云空间/日历/权限全覆盖，微信↔飞书跨域协同 |

### 工具清单（53）

| 分类    | 工具                                                                      | 说明                                    |
| ----- | ----------------------------------------------------------------------- | ------------------------------------- |
| 文件操作  | `read_file` `write_file` `list_directory` `search_files` `send_file`    | 读写浏览搜索发送，写操作限制在 workspace             |
| 代码执行  | `run_python` `install_package`                                          | workspace venv 隔离执行，AST 级安全检查         |
| 系统工具  | `run_shell` `clipboard_read` `get_active_window`                        | Shell 三级风险分类，剪贴板自动脱敏                  |
| 系统控制  | `system_action` `open_app` `list_processes` `check_port` `kill_process` | 音量/锁屏/休眠，应用白名单，进程管理                   |
| 网络    | `web_fetch`                                                             | readability 正文提取                     |
| 下载    | `http_download` `download_video` `webpage_snapshot`                     | GitHub 镜像加速，yt-dlp 视频，Playwright 网页快照 |
| Aria2 | `aria2_download` `aria2_status`                                         | RPC 高速下载，断点续传                         |
| 批量操作  | `batch_rename` `organize_files`                                         | 模板重命名，按类型/日期/扩展名整理                    |
| 媒体处理  | `transcribe_audio` `video_add_subtitles` `ocr_image`                    | Whisper 转录，字幕压制，PaddleOCR/云端 OCR      |
| 磁盘管理  | `scan_large_files` `find_duplicates` `disk_usage`                       | 大文件扫描，MD5 去重，空间统计                     |
| 定时监控  | `schedule_task` `monitor_url`                                           | Cron 定时任务，URL 变化监控                    |
| 飞书集成  | `feishu_send_message` `feishu_send_group_message` `feishu_create_document` `feishu_get_document` `feishu_add_document_blocks` `feishu_create_bitable` `feishu_list_bitable_tables` `feishu_create_bitable_table` `feishu_list_bitable` `feishu_add_bitable_records` `feishu_add_bitable_field` `feishu_create_folder` `feishu_list_folder` `feishu_upload_file` `feishu_list_calendar` `feishu_add_permission` `feishu_delete_file` `feishu_copy_file` `feishu_move_file` | 消息/文档/多维表格/云空间/日历/权限，微信↔飞书跨域 |
| 桥接工具  | `tool_search` `tool_describe` `tool_call`                               | 按需搜索/描述/调用工具，Tool Search 机制           |
| MCP    | 动态加载 `mcp_{server}_{tool}`                                              | MCP 服务器工具，运行时动态注册                     |

***

## 快速开始

### 1. 环境

- Python 3.11+
- Windows / macOS / Linux

### 2. 安装

```bash
git clone https://github.com/Elaine-one/WxAgent.git
cd WxAgent

pip install -r requirements.txt
```

可选依赖（缺少时对应功能降级，不影响核心运行）：

```bash
pip install pilk faster-whisper          # 语音消息转录
pip install paddleocr paddlepaddle       # 本地 OCR 识别
pip install watchdog                     # 后台文件索引监控
pip install playwright && playwright install  # 网页快照渲染
```

### 3. 配置

```bash
cp .env.example .env
```

编辑 `.env`，填入 LLM 配置：

```bash
LLM_PROVIDER=openai
LLM_API_KEY=sk-你的APIKey
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

详细配置见下方 [配置参考](#配置参考)。

### 4. 启动

```bash
python main.py
```

终端会显示登录二维码，用**手机微信扫描**即可连接。

离线调试模式（无需微信）：

```bash
python main.py --dry-run
```

### 5. Web 管理面板（可选）

```bash
python web/run_web.py
```

浏览器打开 `http://127.0.0.1:8765`，即可使用 Web 管理面板：

| 页面       | 功能                            |
| -------- | ----------------------------- |
| 仪表盘      | 服务状态、LLM 调用统计、费用估算            |
| 模型配置     | LLM 提供商/API Key/模型设置，连接测试     |
| 安全设置     | 风险分级、路径沙箱、AI 审查器              |
| 行为限制     | 超时、调用上限、会话参数                  |
| 工作区      | 目录结构、venv 包管理                 |
| 记忆检索     | 索引器、检索器权重、嵌入模型                |
| 工具配置     | Aria2/Whisper/OCR/Web/下载等工具参数 |
| 工具注册表    | 查看/启停/重载已注册工具                 |
| 提示词      | 5 个提示词模板在线编辑                  |
| Skill 管理 | 查看/AI 生成/创建/删除 Skill（即场景模式）   |
| 系统控制     | 系统操作定义、应用白名单                  |
| MCP 管理   | MCP 服务器连接/断开/工具浏览/启停          |
| 飞书管理     | 飞书连接测试/文档浏览/多维表格管理            |

技术栈：FastAPI + React 19 + Ant Design 6 + Zustand 5。前端详见 [web/frontend/README.md](web/frontend/README.md)。

***

## 配置参考

### 环境变量（.env）

| 变量                      |   必填   | 默认值                           | 说明                                        |
| ----------------------- | :----: | ----------------------------- | ----------------------------------------- |
| `LLM_PROVIDER`          |    ✅   | `openai`                      | `openai`（兼容接口）或 `anthropic`（Claude 原生）    |
| `LLM_API_KEY`           |    ✅   | —                             | API 密钥                                    |
| `LLM_BASE_URL`          |    ✅   | `https://api.deepseek.com/v1` | API 地址                                    |
| `LLM_MODEL`             |    ✅   | `deepseek-chat`               | 模型名称                                      |
| `LLM_FALLBACK_API_KEY`  | <br /> | —                             | 备用模型 API Key（主模型失败时自动切换）                  |
| `LLM_FALLBACK_BASE_URL` | <br /> | —                             | 备用模型地址                                    |
| `LLM_FALLBACK_MODEL`    | <br /> | —                             | 备用模型名称                                    |
| `VISION_API_KEY`        | <br /> | 同 `LLM_API_KEY`               | 视觉模型 API Key（图片理解）                        |
| `VISION_BASE_URL`       | <br /> | —                             | 视觉模型地址                                    |
| `VISION_MODEL`          | <br /> | —                             | 视觉模型名称                                    |
| `WORKSPACE_DIR`         | <br /> | `项目目录/workspace`              | 工作区根目录（所有写操作在此）                           |
| `AGENT_BACKEND`         | <br /> | `langgraph`                   | `langgraph`（状态图，推荐）或 `legacy`（简单循环）       |
| `MAX_TOOL_ROUNDS`       | <br /> | 10                            | 每任务最大工具调用轮数                               |
| `MAX_HISTORY`           | <br /> | 20                            | 对话历史保留条数                                  |
| `PYTHON_TIMEOUT`        | <br /> | 60                            | Python 执行超时（秒）                            |
| `SHELL_TIMEOUT`         | <br /> | 30                            | Shell 命令超时（秒）                             |
| `ADV_*`                 | <br /> | 见 `.env.example`              | 30+ 个高级配置覆盖（超时、模型、线程池等），详见 `.env.example` |

### config.yaml

项目根目录的 `config.yaml` 提供更细粒度的配置，涵盖：

| 配置块                       | 说明                                                     |
| ------------------------- | ------------------------------------------------------ |
| `model_router`            | 按模态（text/vision）和任务类型（planning/code\_execution）路由到不同模型 |
| `security.risk_levels`    | Shell 命令风险分级（safe/caution/dangerous）                   |
| `security.path_sandbox`   | 读写路径白名单、禁止访问模式                                         |
| `security.ai_reviewer`    | AI 安全审查开关与审查级别                                         |
| `workspace.venv_packages` | 工作区 venv 预装包（basic/full 两档）                            |
| `limits`                  | 各类超时与上限参数                                              |
| `indexer`                 | 后台文件索引（监控目录、支持格式、watchdog 开关）                          |
| `retriever`               | 记忆检索权重（向量/关键词/时间衰减）                                    |
| `file_organize`           | 文件整理规则（按类型/日期/扩展名）                                     |
| `system_control`          | 系统操作定义（休眠/锁屏/音量）与应用白名单                                 |
| `prompts`                 | 5 个提示词模板（系统提示词、分类、视觉、偏好提取、AI 安全审查）                     |
| `mcp`                     | MCP 服务器配置（服务端端口、客户端连接列表）                                |
| `tool_search`             | Tool Search 桥接工具配置（索引构建、搜索阈值）                          |

### 厂商速查表

| 厂商               | `LLM_PROVIDER` | `LLM_BASE_URL`                                      | `LLM_MODEL` 示例      |
| ---------------- | :------------: | --------------------------------------------------- | ------------------- |
| DeepSeek         |     openai     | `https://api.deepseek.com/v1`                       | `deepseek-chat`     |
| DeepSeek V4 思考   |     openai     | `https://api.deepseek.com`                          | `deepseek-v4-flash` |
| Qwen（阿里）         |     openai     | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus`         |
| 智谱 GLM           |     openai     | `https://open.bigmodel.cn/api/paas/v4`              | `glm-4`             |
| OpenAI           |     openai     | `https://api.openai.com/v1`                         | `gpt-4o`            |
| Anthropic Claude |    anthropic   | `https://api.anthropic.com`                         | `claude-sonnet-4-6` |
| 其他兼容接口           |     openai     | 自填                                                  | 自填                  |

***

## 项目结构

```
WxAgent/
├── main.py                  # 主入口：消息循环、防抖去重、Phase3 初始化
├── config.py                # 全局配置：.env + config.yaml 读取、路径常量、System Prompt
├── config.yaml              # YAML 细粒度配置：模型路由、安全策略、限制参数、场景定义
├── .env.example             # 环境变量模板
│
├── channel/                 # 微信通道层（iLink 协议）
│   ├── client.py            #   HTTP 客户端、AES 加密、InboundMessage 定义
│   ├── receiver.py          #   长轮询收消息 (getUpdates)
│   ├── sender.py            #   发文本/媒体消息 (sendmessage)
│   ├── login.py             #   扫码登录 (get_bot_qrcode + 轮询)
│   ├── upload.py            #   CDN 文件上传 (getUploadUrl → AES → POST → 引用)
│   ├── session.py           #   Session 持久化 (session.json)
│   └── message.py           #   消息签名、防抖合并
│
├── core/                    # 核心引擎层
│   ├── graph.py             #   LangGraph 状态图：classify→react→confirm→interrupt
│   ├── dispatcher.py        #   多用户会话调度（LRU + TTL 24h）、中断恢复
│   ├── agent_loop.py        #   Legacy 简单循环后端
│   ├── state.py             #   AgentState 定义（对话历史 + 费用追踪）
│   ├── deps.py              #   依赖注入
│   └── nodes/
│       ├── classify.py      #   意图分类节点（meta/confirm/interrupt/new_task）
│       └── react.py         #   ReAct 推理节点 + Orphaned Tool Call 修复
│
├── llm/                     # LLM 抽象层
│   ├── universal.py         #   统一接口（策略模式封装 OpenAI/Anthropic）
│   ├── format_openai.py     #   OpenAI 兼容格式适配
│   ├── format_anthropic.py  #   Anthropic 原生格式适配
│   ├── router.py            #   模型路由（按模态/任务类型选择模型）
│   ├── fallback.py          #   降级策略（主模型失败→备用模型）
│   ├── streaming.py         #   流式输出 + 长消息智能分段
│   └── base.py              #   LLM 基础接口
│
├── tools/                   # 工具层（53 工具）
│   ├── base.py              #   ToolDef / ToolResult 数据类 + Schema 转换
│   ├── registry.py          #   ToolRegistry 注册表（register + execute）
│   ├── bridge.py            #   桥接工具（tool_search / tool_describe / tool_call）
│   ├── search.py            #   ToolSearchEngine 搜索引擎
│   └── builtin/             #   内置工具模块
│       ├── file.py          #     文件操作（读写浏览搜索发送）
│       ├── code.py          #     代码执行（run_python + install_package）
│       ├── system.py        #     系统工具（Shell + 剪贴板 + 活跃窗口）
│       ├── system_control.py#     系统控制（音量/锁屏/应用/进程/端口）
│       ├── web.py           #     网络工具（网页抓取）
│       ├── download.py      #     下载工具（HTTP + yt-dlp + Playwright 快照）
│       ├── aria2.py         #     Aria2 RPC 下载
│       ├── media.py         #     媒体处理（语音转录 + 字幕 + OCR）
│       ├── disk.py          #     磁盘管理（大文件 + 去重 + 空间统计）
│       ├── batch.py         #     批量操作（重命名 + 整理）
│       ├── monitor.py       #     定时监控（定时任务 + URL 监控）
│       └── feishu.py        #     飞书集成（19 个工具：消息/文档/表格/云空间/日历/权限）
│
├── memory/                  # 记忆系统
│   ├── manager.py           #   记忆管理器（短期 + 长期 + 偏好提取）
│   ├── short_term.py        #   短期记忆（对话压缩，超 50 条自动摘要）
│   ├── long_term.py         #   长期记忆（ChromaDB + BGE-small-zh 向量嵌入）
│   ├── retriever.py         #   混合检索（向量 0.5 + 关键词 0.3 + 时间衰减 0.2）
│   ├── indexer.py           #   后台文件索引（watchdog + 轮询双模式）
│   └── conflict.py          #   记忆冲突检测
│
├── security/                # 安全体系
│   ├── path_sandbox.py      #   路径沙箱（写限 workspace，读限项目/桌面/下载/文档）
│   ├── risk_levels.py       #   命令风险分级（SAFE/CAUTION/DANGEROUS）
│   ├── ai_reviewer.py       #   AI 安全审查（LLM 判断命令恶意意图）
│   ├── audit.py             #   审计日志（SQLite 记录所有安全事件）
│   ├── data_border.py       #   数据出境同意（首次使用云端服务需确认）
│   └── sanitizer.py         #   输入净化（自动替换 API Key/Token/私钥）
│
├── parsers/                 # 文件解析器
│   ├── pdf.py               #   PDF 解析（pdfplumber）
│   ├── word.py              #   Word 解析（python-docx）
│   ├── excel.py             #   Excel 解析（openpyxl）
│   └── image.py             #   图片解析（PaddleOCR / 云端 Vision API）
│
├── tasks/                   # 异步任务
│   ├── manager.py           #   IO 线程池(8) + CPU 进程池(2)，完成回调微信通知
│   └── scheduler.py         #   APScheduler + SQLAlchemy 持久化
│
├── mcp_client/              # MCP 协议层
│   ├── client.py            #   MCP 客户端（连接外部 MCP 服务器）
│   ├── server.py            #   MCP 服务端（暴露本地工具为 MCP 服务）
│   ├── loader.py            #   MCP 工具动态注册到 ToolRegistry
│   ├── transport.py         #   传输层（stdio / SSE）
│   └── protocol.py          #   JSON-RPC 2.0 协议实现
│
└── observability/           # 可观测性
    ├── logger.py            #   日志
    └── metrics.py           #   指标采集

├── web/                     # Web 管理面板
│   ├── run_web.py           #   启动入口（uvicorn，默认 127.0.0.1:8765）
│   └── api/                 #   FastAPI 后端
│       ├── app.py           #     应用实例 + CORS + SPA 托管
│       ├── models/
│       │   └── schemas.py   #     25 个 Pydantic 配置模型
│       ├── routes/
│       │   ├── config.py    #     配置 CRUD + LLM 连接测试
│       │   ├── service.py   #     服务启停管理
│       │   ├── status.py    #     统计/会话/日志查询
│       │   ├── tools.py     #     工具注册表 + Skill CRUD
│       │   ├── mcp.py       #     MCP 服务器管理
│       │   └── feishu.py    #     飞书连接与文档管理
│       └── services/
│           └── config_service.py  # 配置读写（.env + config.yaml）
│
│   └── frontend/            #   React 前端（详见 web/frontend/README.md）
│       ├── src/pages/       #     13 个配置管理页面
│       ├── src/components/  #     Layout + TagList 共享组件
│       ├── src/store/       #     Zustand 状态管理
│       └── src/api/         #     Axios API 客户端
```

***

## 扩展指南

### 添加新工具

1. 在 `tools/builtin/` 下创建新模块（如 `tools/builtin/my_tool.py`）
2. 定义 `ToolDef` 和处理函数，调用 `ToolRegistry.register()` 注册
3. 工具会被 `tools/__init__.py` 的自动发现机制加载，LLM 会自动学会调用新工具，无需额外配置

```python
from tools.base import ToolDef, ToolResult
from tools.registry import ToolRegistry

def _my_handler(query: str, state=None, user_id: str = "") -> ToolResult:
    result = do_something(query)
    return ToolResult(success=True, content=result)

ToolRegistry.register(
    ToolDef(
        name="my_tool",
        description="做什么用的工具。当用户说xxx时使用。",
        parameters={
            "query": {"type": "string", "description": "查询关键词"},
        },
        required=["query"],
    ),
    _my_handler,
)
```

### 可扩展方向

| 方向      | 思路                                 |
| ------- | ---------------------------------- |
| 数据库查询   | 工具直接查 MySQL/PostgreSQL，Bot 变身数据助手  |
| 邮件发送    | SMTP 发邮件，Bot 变成办公助理                |
| 多 IM 平台 | 扩展 channel/ 包，接入 QQ/钉钉/Telegram    |
| 语音通话    | 实时语音交互，Bot 变成语音助手                  |

***

## 常见问题

<details>
<summary><b>扫码后提示"已连接过此机器"？</b></summary>
同一个微信账号只能绑定一个 Bot。删除 <code>session.json</code> 后重新扫码即可。
</details>

<details>
<summary><b>发送图片微信端显示"图片已过期或被清理"？</b></summary>
通常是 <code>aes_key</code> 编码格式与协议不匹配。检查 <code>channel/client.py</code> 中 <code>_build_base_info()</code> 的 <code>channel_version</code> 是否为 <code>"2.4.4"</code>。
</details>

<details>
<summary><b>支持哪些文件格式？</b></summary>
图片（png/jpg/gif/webp）、视频（mp4/mov/avi）、普通文件（pdf/zip/doc 等）。单文件限制 50MB。
</details>

<details>
<summary><b>对话能记住多少上下文？</b></summary>
短期：每个用户保留最近 20 条消息（可配置）。长期：ChromaDB 向量记忆跨会话持久化，自动提取偏好。对话超过 50 条时自动压缩摘要。
</details>

<details>
<summary><b>可选依赖不装会影响使用吗？</b></summary>
不会。所有可选依赖（pilk/faster-whisper/paddleocr/watchdog/playwright）均为条件导入，缺少时对应功能自动降级（如本地 Whisper 不可用则跳过语音转录，OCR 降级到云端 API），不影响核心对话和工具调用。
</details>

<details>
<summary><b>安全机制有哪些？</b></summary>
六层防护：①路径沙箱限制写操作在 workspace 内；②命令风险三级分类（safe/caution/dangerous）；③AI 安全审查（LLM 判断命令恶意意图）；④审计日志（SQLite 记录所有安全事件）；⑤数据出境同意（首次使用云端服务需确认）；⑥剪贴板脱敏（自动替换 API Key/Token/私钥）。
</details>

<details>
<summary><b>可以在服务器上跑吗？</b></summary>
可以，但需注意：扫码登录需要终端显示二维码或访问二维码 URL；服务器如果有公网 IP 可直接运行。无头服务器可访问终端输出的二维码 URL 完成扫码。
</details>

<details>
<summary><b>legacy 和 langgraph 后端有什么区别？</b></summary>
<code>legacy</code> 是简单循环：消息→LLM→工具→回复。<code>langgraph</code>（默认）是完整状态机：支持消息分类、人机确认（危险操作需用户 Y/N）、中断恢复（Checkpoint 持久化）、元命令（/help /status /reset）。推荐使用 langgraph。
</details>

***

## 协议

本项目基于腾讯官方 iLink Bot API：

| 端点                            | 用途             |
| ----------------------------- | -------------- |
| `ilink/bot/get_bot_qrcode`    | 获取登录二维码        |
| `ilink/bot/get_qrcode_status` | 轮询扫码状态         |
| `ilink/bot/getupdates`        | 长轮询收消息         |
| `ilink/bot/sendmessage`       | 发文本 / 媒体引用     |
| `ilink/bot/getuploadurl`      | 获取 CDN 预签名上传地址 |

**CDN 上传链路**：`getUploadUrl` → AES-128-ECB 加密 → POST CDN → `x-encrypted-param` 响应头 → sendmessage 发送媒体引用

参考文档：[微信 iLink Bot 协议完全解析](http://mp.weixin.qq.com/s?__biz=Mzg4NjE2NzUyNw==\&mid=2247485180\&idx=1\&sn=19b1cdc0669c38c9de7755111e522a50)

***

## License

本项目采用 [GNU General Public License v3.0](LICENSE) 开源协议。

Copyright (C) 2026 WxAgent Contributors
