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

<p align="center">
  <video src="https://github.com/user-attachments/assets/0d06f494-1566-408b-b739-0ddc13b0dbc8" controls width="80%"></video>
</p>

## 架构

<div align="center">

```
┌───────────────────────────────────────────────────┐
│                   WeChat Client                    │
│                 (User Interface)                   │
└───────────────────────┬───────────────────────────┘
                        │  iLink 协议
                        ▼
┌───────────────────────────────────────────────────┐
│               Communication Layer                  │
│                                                   │
│     client · receiver · sender · login · session  │
│     upload · message                              │
└───────────────────────┬───────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────┐
│                Agent Runtime Core                  │
│                                                   │
│     graph → dispatcher → agent_loop → nodes       │
│                                                   │
└────────┬──────────────────────────────┬───────────┘
         │                              │
         ▼                              ▼
┌───────────────────┐        ┌──────────────────────┐
│ Model Abstraction │        │    Infrastructure    │
│                   │        │                      │
│ universal         │        │ memory               │
│ router            │        │ security             │
│ fallback          │        │ mcp_client           │
│ streaming         │        │ parsers              │
└─────────┬─────────┘        └──────────────────────┘
          │
          ▼
┌───────────────────────────────────────────────────┐
│                   Tool Runtime                     │
│                                                   │
│   file · code · system · feishu · web · media     │
│   aria2 · download · monitor · disk · batch       │
│                                                   │
│                     58+ Tools                      │
└───────────────────────┬───────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────┐
│               Local Execution Layer                │
│                                                   │
│     File System · Browser · Terminal · Media      │
└───────────────────────────────────────────────────┘
```

</div>

### LangGraph 状态图（默认后端）

<div align="center">

```
用户消息
    │
    ▼
┌──────────┐
│ classify │  LLM 识别消息类型
└──┬──┬──┬──┘
   │  │  │
   │  │  └─ interrupt → handle_interrupt ──→ react
   │  │
   │  └─ meta → handle_meta ──→ END
   │
   ├─ new_task → react ──→ respond ──→ END
   │              │
   │              └─ need_confirm ──→ wait_user
   │                                     │
   └─ confirm ──────────────────────→ handle_confirm
                                         ↑       │
                                         └───────┘
                                         回到 react
```

</div>

- **classify**：LLM 判断消息类型（新任务 / 确认回复 / 中断 / 元命令）
- **react**：LLM 推理 + 工具调用循环（最多 10 轮）
- **wait_user**：危险操作人工确认（Y/N），最多 3 轮
- **Checkpoint**：SQLite 持久化，支持跨消息中断恢复

### 数据流

<div align="center">

```
"桌面有什么文件？"
       │
       ▼
  ┌───────────────┐
  │    WeChat     │  用户发送消息
  └───────┬───────┘
          │
          ▼
  ┌───────────────┐
  │   channel/    │  ① receiver 收消息，3s 防抖去重
  │   receiver    │  ② 提取文字 + 媒体附件
  └───────┬───────┘
          │
          ▼
  ┌───────────────┐
  │     core/     │  ③ dispatcher 分发消息
  │  dispatcher   │  ④ 匹配 Skill 触发词 → 注入候选
  └───────┬───────┘
          │
          ▼
  ┌───────────────┐
  │   classify    │  ⑤ LLM 判断消息类型 → new_task
  │  (LLM 分类)   │
  └───────┬───────┘
          │
          ▼
  ┌───────────────┐
  │     react     │  ⑥ LLM 推理 → 决定调用工具
  │  (推理循环)   │  ⑦ 生成 tool_call
  └───────┬───────┘
          │
          ▼
  ┌───────────────┐
  │    tools/     │  ⑧ tools/builtin/file.py
  │    builtin    │     → os.listdir() 执行
  └───────┬───────┘
          │
          ▼
  ┌───────────────┐
  │     react     │  ⑨ 工具结果返回 LLM
  │  (继续推理)   │  ⑩ 生成自然语言回复
  └───────┬───────┘
          │
          ▼
  ┌───────────────┐
  │  dispatcher   │  ⑪ 智能分段（≤ 600 字/段）
  │  (分段发送)   │  ⑫ channel/sender → 微信
  └───────┬───────┘
          │
          ▼
  ┌───────────────┐
  │    WeChat     │  用户看到回复
  └───────────────┘
```

</div>

***

## 功能

| 类别 | 能力 |
|------|------|
| 对话 | 多轮自然语言对话，流式输出，长消息智能分段（600字/段） |
| 工具 | 58 工具（55 内置 + 3 桥接），覆盖文件/代码/系统/网络/下载/媒体/磁盘/批量/监控/飞书/地图 12 大类 |
| 记忆 | 短期对话压缩 + 长期 ChromaDB 向量记忆 + 偏好自动学习 + 混合检索 |
| 安全 | 路径沙箱 + 命令风险分级 + AI 安全审查 + 审计日志 + 数据出境同意 + 剪贴板脱敏 |
| 调度 | APScheduler 定时任务 + URL 变化监控 + Skill 场景模式（触发词匹配 → 动态注入 LLM） |
| 语音 | SILK→WAV→Whisper 自动转录，支持本地/云端双模式 |
| 多用户 | 按微信用户 ID 隔离对话历史与记忆，LRU + TTL 会话管理 |
| 路由 | 按模态/任务类型路由不同模型，主模型失败自动降级 |
| 面板 | Web 管理面板（FastAPI + React），13 个配置页面，服务启停、日志查看、工具管理、Skill 生成 |
| MCP | MCP 客户端/服务端双模式，动态加载外部工具服务器，Tool Search 桥接机制 |
| 飞书 | 23 个飞书工具，消息/文档/文档块/多维表格/云空间/日历/权限全覆盖，微信↔飞书跨域协同 |

### 工具分类

| 分类 | 数量 | 主要工具 |
|------|:----:|------|
| 文件操作 | 6 | `read_file` `write_file` `delete_file` `list_directory` `search_files` `send_file` |
| 代码执行 | 2 | `run_python` `install_package` |
| 系统工具 | 3 | `run_shell` `clipboard_read` `get_active_window` |
| 系统控制 | 5 | `system_action` `open_app` `list_processes` `check_port` `kill_process` |
| 网络 | 1 | `web_fetch` |
| 下载 | 3 | `http_download` `download_video` `webpage_snapshot` |
| Aria2 | 2 | `aria2_download` `aria2_status` |
| 批量操作 | 2 | `batch_rename` `organize_files` |
| 媒体处理 | 3 | `transcribe_audio` `video_add_subtitles` `ocr_image` |
| 磁盘管理 | 3 | `scan_large_files` `find_duplicates` `disk_usage` |
| 定时监控 | 2 | `schedule_task` `monitor_url` |
| 飞书集成 | 23 | 消息·文档·文档块·多维表格·云空间·日历·权限，支持增删改查 |
| 桥接工具 | 3 | `tool_search` `tool_describe` `tool_call` |
| MCP | 动态 | `mcp_{server}_{tool}` — 运行时动态注册 |

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

可选依赖（缺少时对应功能降级）：

```bash
pip install pilk faster-whisper          # 语音消息转录
pip install paddleocr paddlepaddle       # 本地 OCR
pip install watchdog                     # 后台文件索引
pip install playwright && playwright install  # 网页快照
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

详细配置见 [配置参考](#配置参考)。

### 4. 启动

```bash
python main.py
```

终端显示登录二维码，手机微信扫码即可连接。离线调试：

```bash
python main.py --dry-run
```

### 5. Web 管理面板（可选）

```bash
python web/run_web.py
```

访问 `http://127.0.0.1:8765`：

| 页面 | 功能 |
|------|------|
| 仪表盘 | 服务状态、启动检测、LLM 调用统计 |
| 模型配置 | LLM 提供商/API Key/模型设置，连接测试 |
| 安全设置 | 风险分级、路径沙箱、AI 审查器 |
| 行为限制 | 超时、调用上限、会话参数 |
| 工作区 | 目录结构、venv 包管理 |
| 记忆检索 | 索引器、检索器权重、嵌入模型 |
| 工具配置 | Aria2/Whisper/OCR/Web/下载等参数 |
| 工具注册表 | 查看/启停/重载已注册工具 |
| 提示词 | 5 个提示词模板在线编辑 |
| Skill 管理 | 查看/AI 生成/创建/删除 Skill |
| 系统控制 | 系统操作定义、应用白名单 |
| MCP 管理 | MCP 服务器连接/断开/工具浏览 |
| 飞书管理 | 飞书连接测试/文档浏览/多维表格管理 |

技术栈：FastAPI + React 19 + Ant Design 6 + Zustand 5。详见 [web/frontend/README.md](web/frontend/README.md)。

***

## 配置参考

### 环境变量（.env）

| 变量 | 必填 | 默认值 | 说明 |
|------|:----:|--------|------|
| `LLM_PROVIDER` | ✅ | `openai` | `openai`（兼容接口）或 `anthropic` |
| `LLM_API_KEY` | ✅ | — | API 密钥 |
| `LLM_BASE_URL` | ✅ | `https://api.deepseek.com/v1` | API 地址 |
| `LLM_MODEL` | ✅ | `deepseek-chat` | 模型名称 |
| `WORKSPACE_DIR` | | `项目目录/workspace` | 工作区根目录 |
| `AGENT_BACKEND` | | `langgraph` | `langgraph`（推荐）或 `legacy` |
| `MAX_TOOL_ROUNDS` | | 10 | 每任务最大工具调用轮数 |
| `ADV_MAX_CHARS` | | 600 | 分段发送字数上限 |
| … | | | 30+ 高级配置详见 `.env.example` |

### 厂商速查表

| 厂商 | `LLM_PROVIDER` | `LLM_BASE_URL` | `LLM_MODEL` 示例 |
|------|:---:|------|------|
| DeepSeek | openai | `https://api.deepseek.com/v1` | `deepseek-chat` |
| DeepSeek V4 | openai | `https://api.deepseek.com` | `deepseek-v4-flash` |
| Qwen | openai | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 智谱 GLM | openai | `https://open.bigmodel.cn/api/paas/v4` | `glm-4` |
| OpenAI | openai | `https://api.openai.com/v1` | `gpt-4o` |
| Claude | anthropic | `https://api.anthropic.com` | `claude-sonnet-4-6` |
| 其他兼容 | openai | 自填 | 自填 |

config.yaml 提供更细粒度配置：模型路由、安全策略、工作区 venv、记忆检索权重、Skill 场景定义、MCP 服务器列表等。完整说明见 `.env.example` 和 `config.yaml` 内注释。

***

## 项目结构

```
WxAgent/
├── main.py                  # 主入口：消息循环、防抖去重、初始化
├── config.py                # 全局配置 + System Prompt 动态构建
├── config.yaml              # YAML 细粒度配置
│
├── channel/                 # 微信通道层（iLink 协议）
│   ├── client.py            #   HTTP 客户端、AES 加密、InboundMessage
│   ├── receiver.py          #   长轮询收消息
│   ├── sender.py            #   发文本/媒体消息
│   ├── login.py             #   扫码登录
│   ├── upload.py            #   CDN 文件上传（AES-128-ECB）
│   ├── session.py           #   Session 持久化
│   └── message.py           #   消息签名、防抖合并
│
├── core/                    # 核心引擎层
│   ├── graph.py             #   LangGraph 状态图 + builder
│   ├── dispatcher.py        #   多用户会话调度（LRU + TTL 24h）
│   ├── agent_loop.py        #   Legacy 简单循环
│   ├── state.py             #   AgentState 定义
│   ├── deps.py              #   依赖注入
│   └── nodes/
│       ├── classify.py      #   意图分类（meta/confirm/interrupt/new_task）
│       └── react.py         #   ReAct 推理 + 动态 Skill 注入
│
├── llm/                     # LLM 抽象层
│   ├── universal.py         #   统一接口（OpenAI/Anthropic 策略模式）
│   ├── format_openai.py     #   OpenAI 兼容格式
│   ├── format_anthropic.py  #   Anthropic 原生格式
│   ├── router.py            #   多模态任务路由
│   ├── fallback.py          #   主模型失败降级
│   ├── streaming.py         #   流式输出 + 段落智能分段
│   └── base.py              #   基础接口
│
├── tools/                   # 工具层（58 工具）
│   ├── base.py              #   ToolDef / ToolResult 数据类
│   ├── registry.py          #   ToolRegistry 注册表
│   ├── bridge.py            #   桥接工具（tool_search/describe/call）
│   ├── search.py            #   ToolSearchEngine
│   └── builtin/             #   内置工具：file · code · system · feishu · ... (12 个模块)
│
├── memory/                  # 记忆系统
│   ├── manager.py           #   短期 + 长期 + 偏好提取
│   ├── short_term.py        #   对话压缩（超 50 条自动摘要）
│   ├── long_term.py         #   ChromaDB + BGE-small-zh 向量嵌入
│   ├── retriever.py         #   混合检索（向量 + 关键词 + 时间衰减）
│   └── indexer.py           #   后台文件索引
│
├── security/                # 安全体系（6 层防护）
│
├── parsers/                 # 文件解析器（PDF/Word/Excel/图片）
│
├── mcp_client/              # MCP 协议层
│   ├── client.py            #   MCP 客户端
│   ├── server.py            #   MCP 服务端
│   ├── loader.py            #   动态注册到 ToolRegistry
│   └── transport.py         #   传输层（stdio / SSE / 飞书 MCP）
│
├── web/                     # Web 管理面板
│   ├── run_web.py           #   启动入口（uvicorn, :8765）
│   ├── api/                 #   FastAPI 后端（6 路由模块）
│   └── frontend/            #   React 前端（13 页面）
│
├── tasks/                   # 异步任务 + APScheduler
└── observability/           # 日志 + 指标采集
```

***

## 扩展指南

### 添加新工具

在 `tools/builtin/` 下新建模块，注册即可被 LLM 发现：

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
        parameters={"query": {"type": "string", "description": "查询关键词"}},
        required=["query"],
    ),
    _my_handler,
)
```

### 可扩展方向

| 方向 | 思路 |
|------|------|
| 数据库查询 | 工具直接查 MySQL/PostgreSQL，Bot 变身数据助手 |
| 多 IM 平台 | 扩展 channel/ 包，接入 QQ/钉钉/Telegram |
| 邮件发送 | SMTP 发邮件，Bot 变成办公助理 |

***

## 常见问题

<details>
<summary><b>扫码后提示"已连接过此机器"？</b></summary>
同一微信账号只能绑定一个 Bot。删除 <code>session.json</code> 后重新扫码。
</details>

<details>
<summary><b>发送图片微信端显示"图片已过期或被清理"？</b></summary>
检查 <code>channel/client.py</code> 中 <code>_build_base_info()</code> 的 <code>channel_version</code> 是否为 <code>"2.4.4"</code>。
</details>

<details>
<summary><b>支持哪些文件格式？</b></summary>
图片（png/jpg/gif/webp）、视频（mp4/mov/avi）、普通文件（pdf/zip/doc 等），单文件 50MB。
</details>

<details>
<summary><b>对话能记住多少上下文？</b></summary>
短期：每用户保留最近 20 条消息。长期：ChromaDB 向量记忆跨会话持久化，超 50 条自动压缩摘要。
</details>

<details>
<summary><b>可选依赖不装会影响使用吗？</b></summary>
不会。所有可选依赖均为条件导入，缺少时对应功能自动降级，不影响核心对话和工具调用。
</details>

<details>
<summary><b>安全机制有哪些？</b></summary>
六层防护：路径沙箱、命令风险分级、AI 安全审查、审计日志、数据出境同意、剪贴板脱敏。
</details>

<details>
<summary><b>legacy 和 langgraph 后端有什么区别？</b></summary>
<code>legacy</code>：简单循环，消息→LLM→工具→回复。<code>langgraph</code>（默认）：完整状态机，支持消息分类、人机确认、中断恢复、元命令。推荐 langgraph。
</details>

***

## 协议

基于腾讯官方 iLink Bot API：

| 端点 | 用途 |
|------|------|
| `ilink/bot/get_bot_qrcode` | 获取登录二维码 |
| `ilink/bot/get_qrcode_status` | 轮询扫码状态 |
| `ilink/bot/getupdates` | 长轮询收消息 |
| `ilink/bot/sendmessage` | 发文本 / 媒体引用 |
| `ilink/bot/getuploadurl` | 获取 CDN 预签名上传地址 |

CDN 上传链路：`getUploadUrl` → AES-128-ECB 加密 → POST CDN → `x-encrypted-param` → sendmessage 发送媒体引用

***

## License

本项目采用 [GNU General Public License v3.0](LICENSE) 开源协议。

Copyright (C) 2026 Elaine-one
