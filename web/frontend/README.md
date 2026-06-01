# WxAgent 管理面板前端

WeChat Claude 机器人的 Web 管理面板，提供可视化配置、服务管理、日志查看、工具管理等功能。

## 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 19 | UI 框架 |
| TypeScript | 6 | 类型安全 |
| Vite | 8 | 构建工具 |
| Ant Design | 6 | UI 组件库 |
| Zustand | 5 | 状态管理 |
| React Router | 7 | 路由 |
| Axios | 1.x | HTTP 客户端 |

## 开发环境

### 前置要求

- Node.js 18+
- 后端服务运行在 `http://127.0.0.1:8765`（或通过 Vite 代理）

### 安装与启动

```bash
cd web/frontend
npm install
npm run dev
```

开发服务器启动在 `http://localhost:5173`，API 请求自动代理到后端 `127.0.0.1:8765`。

### 构建

```bash
npm run build
```

构建产物输出到 `dist/`，由 FastAPI 后端托管（SPA 模式）。

### 其他命令

| 命令 | 说明 |
|------|------|
| `npm run dev` | 启动开发服务器（端口 5173） |
| `npm run build` | TypeScript 编译 + Vite 生产构建 |
| `npm run lint` | ESLint 代码检查 |
| `npm run preview` | 预览生产构建 |

## 项目结构

```
src/
├── App.tsx                  # 路由定义（11 个页面路由）
├── main.tsx                 # 应用入口
├── index.css                # 全局样式
│
├── api/
│   └── client.ts            # Axios API 客户端（11 个 API 函数）
│
├── assets/                  # 静态资源
│   └── hero.png
│
├── components/
│   ├── Layout.tsx           # 全局布局（可折叠侧边栏 + 顶栏状态灯 + 内容区）
│   └── TagList.tsx          # 标签列表编辑组件（添加/删除标签）
│
├── hooks/
│   └── useEditMode.ts       # 编辑模式管理 Hook（进入/取消/保存退出）
│
├── pages/
│   ├── Dashboard.tsx        # 仪表盘：服务状态、LLM 调用统计、费用估算
│   ├── LLMConfig.tsx        # 模型配置：LLM 提供商/API Key/模型设置、连接测试
│   ├── Security.tsx         # 安全设置：风险分级、路径沙箱、AI 审查器（预留）
│   ├── Limits.tsx           # 行为限制：超时、调用上限、会话参数
│   ├── Workspace.tsx        # 工作区：目录结构、venv 包管理
│   ├── Memory.tsx           # 记忆检索：索引器、检索器权重、嵌入模型
│   ├── Tools.tsx            # 工具配置：Aria2/Whisper/OCR/Web/下载等参数
│   ├── ToolRegistry.tsx     # 工具注册表：查看/启停/重载已注册工具
│   ├── Prompts.tsx          # 提示词：5 个提示词模板在线编辑
│   ├── Scenarios.tsx        # Skill 管理：查看/AI 生成/创建/删除 Skill
│   └── SystemControl.tsx    # 系统控制：系统操作定义、应用白名单
│
└── store/
    ├── configStore.ts       # 配置状态管理（读取/更新各模块配置）
    └── serviceStore.ts      # 服务状态管理（启停/状态查询）
```

## 页面与路由映射

| 路径 | 组件 | 功能 |
|------|------|------|
| `/` | Dashboard | 仪表盘：服务状态、统计、日志 |
| `/llm` | LLMConfig | 模型配置与连接测试 |
| `/security` | Security | 安全策略配置 |
| `/limits` | Limits | 行为限制参数 |
| `/workspace` | Workspace | 工作区目录与包管理 |
| `/memory` | Memory | 记忆检索配置 |
| `/tools` | Tools | 工具参数配置 |
| `/tool-registry` | ToolRegistry | 工具注册表管理 |
| `/prompts` | Prompts | 提示词模板编辑 |
| `/scenarios` | Scenarios | Skill 管理与生成 |
| `/system` | SystemControl | 系统控制配置 |

## API 集成

### 开发模式

Vite 开发服务器将 `/api` 请求代理到后端 `http://127.0.0.1:8765`，配置在 `vite.config.ts`：

```typescript
server: {
  port: 5173,
  proxy: {
    '/api': {
      target: 'http://127.0.0.1:8765',
      changeOrigin: true,
    },
  },
}
```

### 生产模式

FastAPI 后端直接托管前端静态文件（`dist/`），无需单独部署前端。所有路由回退到 `index.html`（SPA 模式）。

### API 函数

`src/api/client.ts` 导出以下函数：

| 函数 | 方法 | 路径 | 说明 |
|------|------|------|------|
| `getConfig` | GET | `/config` | 获取全部或指定模块配置 |
| `updateConfig` | PUT | `/config/{module}` | 更新指定模块配置 |
| `testLLM` | POST | `/config/test-llm` | 测试 LLM 连接（自定义参数） |
| `testLLMCurrent` | POST | `/config/test-llm-current` | 测试当前 LLM 配置 |
| `getStatus` | GET | `/status` | 获取服务运行状态 |
| `startService` | POST | `/service/start` | 启动服务 |
| `stopService` | POST | `/service/stop` | 停止服务 |
| `restartService` | POST | `/service/restart` | 重启服务 |
| `getStats` | GET | `/stats` | 获取 LLM 调用统计 |
| `getLogs` | GET | `/logs` | 获取日志条目 |
| `generateSkill` | POST | `/skills/generate` | AI 生成 Skill |

## 状态管理

### configStore

配置读写状态管理，使用 Zustand：

- `config` — 当前配置数据
- `loading` / `saving` — 加载/保存状态
- `fetchConfig(module?)` — 获取配置
- `updateConfig(module, data)` — 更新配置（保存后自动刷新）

### serviceStore

服务状态管理：

- `status` — 服务运行状态（running/pid/uptime）
- `fetchStatus()` — 查询服务状态
- `start()` / `stop()` / `restart()` — 服务控制

## 通用模式

### 编辑模式

大部分配置页面使用 `useEditMode` Hook 实现编辑/查看模式切换：

1. 默认为查看模式（表单禁用）
2. 点击"编辑"进入编辑模式
3. 修改后点击"保存"调用 API，或"取消"放弃修改
4. 保存成功后自动退出编辑模式

### TagList 组件

`TagList` 用于编辑字符串数组（如 GitHub 镜像列表、路径白名单等），支持：
- 以 Tag 形式展示数组元素
- 输入框 + 回车/按钮添加新标签
- 点击 Tag 关闭按钮删除标签
- 自动去重
