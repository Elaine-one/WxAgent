<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/协议-iLink_Bot-green.svg" alt="Protocol">
  <img src="https://img.shields.io/badge/LLM-多厂商-orange.svg" alt="LLM">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

# WxAgent

> 将任意 AI 大模型接入微信个人号，打造成运行在个人电脑上的**智能体底座**。

基于腾讯官方 iLink Bot 协议，纯 Python 实现。支持 DeepSeek、OpenAI、Claude、Qwen、智谱等主流大模型。无需 Node.js、无需 Docker、无需 LangChain。

---

## 架构

```
┌──────────┐   微信消息    ┌─────────────────────────────┐    API 调用    ┌──────────┐
│          │ ──────────→  │         main.py              │ ────────────→  │  LLM     │
│  微信    │              │  收消息 → 对话管理 → LLM 决策  │               │ DeepSeek │
│  客户端  │              │      ↑          ↓            │               │ OpenAI   │
│          │ ←──────────  │  工具执行 ← 工具调用          │ ←────────────  │ Claude   │
└──────────┘   回复消息    └─────────────────────────────┘   返回结果      └──────────┘
                                   │        ↑
                                   ↓        │
                          ┌─────────────────────────┐
                          │      工具层              │
                          │  read_file   send_file  │
                          │  list_dir    run_shell  │
                          │  search_files           │
                          └─────────────────────────┘
                                   │
                                   ↓
                          ┌─────────────────────────┐
                          │      本地系统            │
                          │  文件系统 / 命令行       │
                          └─────────────────────────┘
```

### 数据流

```
用户发微信 "桌面有什么文件？"
        │
        ▼
  ① main.py 收到消息
        │
        ▼
  ② LLM 分析 → 决定调用 list_directory 工具
        │
        ▼
  ③ tools.py 执行 os.listdir → 获取文件列表
        │
        ▼
  ④ 结果送回 LLM → LLM 生成自然语言回复
        │
        ▼
  ⑤ main.py 通过 iLink API 发送回复到微信
```

### 工具调用循环

每次用户消息最多执行 **5 轮** 工具调用。LLM 可以在同一轮调用多个工具（并行），结果汇总后再决策下一步。

```
用户消息 → LLM → [工具1, 工具2] → 结果 → LLM → [工具3] → 结果 → LLM → 最终回复
```

---

## 功能

| 类别 | 能力 |
|------|------|
| 💬 对话 | 多轮自然语言对话，支持 DeepSeek V4 思考模式 |
| 📁 文件 | 收发图片、视频、文档，CDN AES-128-ECB 加密传输 |
| 🔧 工具 | 读文件、列目录、搜文件、执行只读 Shell 命令 |
| 🔄 持久化 | Session 自动保存，断线重连无需重新扫码 |
| 👥 多用户 | 按微信用户隔离对话历史，互不干扰 |

---

## 快速开始

### 1. 环境

- Python 3.9+
- Windows / macOS / Linux

### 2. 安装

```bash
git clone https://github.com/yourusername/WxAgent.git
cd WxAgent

pip install httpx openai anthropic cryptography python-dotenv qrcode
```

### 3. 配置

```bash
cp .env.example .env
```

编辑 `.env`，选择一种 LLM 厂商填入：

```bash
# 方式一：OpenAI 兼容接口（推荐）
LLM_PROVIDER=openai
LLM_API_KEY=sk-你的APIKey
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

# 方式二：Anthropic 原生接口
# LLM_PROVIDER=anthropic
# LLM_API_KEY=sk-ant-api03-你的APIKey
# LLM_BASE_URL=https://api.anthropic.com
# LLM_MODEL=claude-sonnet-4-6
```

### 4. 启动

```bash
python main.py
```

终端会显示登录二维码，用**手机微信扫描**即可连接。连接后二维码会自动刷新，长连接保持在线。

---

## 配置参考

| 参数 | 必填 | 说明 |
|------|:--:|------|
| `LLM_PROVIDER` | ✅ | `openai`（兼容接口）或 `anthropic`（Claude 原生） |
| `LLM_API_KEY` | ✅ | API 密钥 |
| `LLM_BASE_URL` | ✅ | API 地址 |
| `LLM_MODEL` | ✅ | 模型名称 |

### 厂商速查表

| 厂商 | `LLM_PROVIDER` | `LLM_BASE_URL` | `LLM_MODEL` 示例 |
|------|:---:|------|------|
| DeepSeek | openai | `https://api.deepseek.com/v1` | `deepseek-chat` |
| DeepSeek V4 思考 | openai | `https://api.deepseek.com` | `deepseek-v4-flash` |
| Qwen（阿里） | openai | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 智谱 GLM | openai | `https://open.bigmodel.cn/api/paas/v4` | `glm-4` |
| OpenAI | openai | `https://api.openai.com/v1` | `gpt-4o` |
| Anthropic Claude | anthropic | `https://api.anthropic.com` | `claude-sonnet-4-6` |
| 其他兼容接口 | openai | 自填 | 自填 |

---

## 项目结构

```
WxAgent/
├── main.py              # 主入口 & Agent 循环
│                        #   收消息 → 对话管理 → LLM → 工具 → 回复
├── ilink.py             # iLink 协议层 (364 行)
│                        #   扫码登录、长轮询收消息、发文本、Session 持久化
├── ilink_upload.py      # CDN 文件上传 (269 行)
│                        #   AES-128-ECB 加密、getUploadUrl、CDN POST、sendmessage
├── llm.py               # LLM 抽象层 (234 行)
│                        #   统一接口：OpenAI 兼容 / Anthropic 原生
│                        #   处理 reasoning_content 等多厂商差异
├── tools.py             # 工具注册表 (264 行)
│                        #   ToolDef 定义 → to_openai_schema / to_anthropic_schema
│                        #   execute 分发 → 5 个工具实现
├── config.py            # 全局配置 (67 行)
│                        #   .env 读取、路径常量、System Prompt、历史轮数
├── .env.example         # 配置模板
└── session.json         # 登录凭证（自动生成，勿提交）
```

---

## 扩展指南

### 添加新工具

在 `tools.py` 中加两处：

```python
# 1. 注册工具定义
ToolDef(
    name="search_web",
    description="搜索网页内容。用于回答需要最新信息的问题。",
    parameters={
        "query": {"type": "string", "description": "搜索关键词"},
    },
    required=["query"],
),

# 2. 在 execute() 中添加执行分支
elif name == "search_web":
    return _search_web(args.get("query", ""))
```

LLM 会自动学会调用新工具，无需额外配置。

### 可扩展方向

| 方向 | 思路 |
|------|------|
| 网页搜索 | 接入 Bing/Google Search API，让 Bot 回答实时问题 |
| 数据库查询 | 工具直接查 MySQL/PostgreSQL，Bot 变身数据助手 |
| 邮件发送 | SMTP 发邮件，Bot 变成办公助理 |
| 定时推送 | `CronCreate` 定时任务 + 天气/股价/提醒主动推送 |
| 长期记忆 | 接向量数据库（ChromaDB/Milvus），实现跨会话记忆 |
| MCP 生态 | 兼容 MCP 协议，接入更多工具服务器 |
| Web 管理台 | Flask/FastAPI 面板，可视化管理对话历史与配置 |

### 调整对话历史长度

`config.py` 第 26 行：

```python
MAX_HISTORY = 20    # 每个用户保留的消息数，改大即可
```

---

## 常见问题

<details>
<summary><b>扫码后提示"已连接过此机器"？</b></summary>
同一个微信账号只能绑定一个 Bot。删除 <code>session.json</code> 后重新扫码即可。
</details>

<details>
<summary><b>发送图片微信端显示"图片已过期或被清理"？</b></summary>
通常是 <code>aes_key</code> 编码格式与协议不匹配。检查 <code>ilink.py</code> 中 <code>_build_base_info()</code> 的 <code>channel_version</code> 是否为 <code>"2.4.4"</code>。
</details>

<details>
<summary><b>支持哪些文件格式？</b></summary>
图片（png/jpg/gif/webp）、视频（mp4/mov/avi）、普通文件（pdf/zip/doc 等）。单文件限制 50MB。
</details>

<details>
<summary><b>对话能记住多少上下文？</b></summary>
每个用户保留最近 20 条消息（约 19 轮对话）。超过后自动丢弃最早的消息，System Prompt 始终保留。
</details>

<details>
<summary><b>可以在服务器上跑吗？</b></summary>
可以，但需注意：扫码登录需要终端显示二维码或访问二维码 URL；服务器如果有公网 IP 可直接运行。无头服务器可访问终端输出的二维码 URL 完成扫码。
</details>

---

## 协议

本项目基于腾讯官方 iLink Bot API：

| 端点 | 用途 |
|------|------|
| `ilink/bot/get_bot_qrcode` | 获取登录二维码 |
| `ilink/bot/get_qrcode_status` | 轮询扫码状态 |
| `ilink/bot/getupdates` | 长轮询收消息 |
| `ilink/bot/sendmessage` | 发文本 / 媒体引用 |
| `ilink/bot/getuploadurl` | 获取 CDN 预签名上传地址 |

**CDN 上传链路**：`getUploadUrl` → AES-128-ECB 加密 → POST CDN → `x-encrypted-param` 响应头 → sendmessage 发送媒体引用

参考文档：[微信 iLink Bot 协议完全解析](http://mp.weixin.qq.com/s?__biz=Mzg4NjE2NzUyNw==&mid=2247485180&idx=1&sn=19b1cdc0669c38c9de7755111e522a50)

---

## License

MIT © 2026
