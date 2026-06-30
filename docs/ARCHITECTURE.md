# Argus 架构说明

本文档描述 Argus 的系统架构、核心模块职责、消息路由流程、Agent 适配层、记忆系统与 GUI 前后端交互。

## 系统架构图（文字版）

```
┌─────────────────────────────────────────────────────────────────┐
│                          用户层                                   │
│  CLI (argus onboard / gateway / agent / status)                │
│  Tauri + Vue 3 GUI (协作树编辑器 / 聊天 / 会议 / 状态)            │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Argus 编排层 (argus/)                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  Config     │  │  Core       │  │  MemoryStore            │  │
│  │  schema/    │  │  tree/      │  │  projects/team/agents/  │  │
│  │  loader     │  │  bus/       │  │  meetings/modes         │  │
│  │             │  │  router/    │  │                         │  │
│  │             │  │  meeting/   │  │                         │  │
│  │             │  │  orchestrator│  │                         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│  ┌─────────────┐  ┌─────────────┐                                │
│  │ Adapters    │  │ GUI backend │                                │
│  │ nanobot_agent│  │ server.py   │                                │
│  └─────────────┘  └─────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                   nanobot 运行时库 (nanobot/)                    │
│  AgentLoop / AgentRunner / ToolRegistry / SessionManager         │
│  Provider / ChannelManager / Skills                              │
└─────────────────────────────────────────────────────────────────┘
```

## 核心模块说明

### `argus/core/`

| 文件 | 职责 |
|------|------|
| `tree.py` | 协作树数据模型：`Node`、`Edge`、`CollaborationTree`；YAML/JSON 解析；`can_communicate`、`get_reachable_nodes`、`parse_mentions`。 |
| `message.py` | 统一消息模型 `ArgusMessage`，支持私聊/群聊判定与序列化。 |
| `bus.py` | 异步消息总线 `ArgusBus`，按节点 ID 维护队列与回调，提供 `send_private` / `send_group` / `dispatch` / `subscribe`。 |
| `router.py` | 路由引擎 `MessageRouter`，订阅总线后根据协作树连线把消息投递到 Agent 适配器或人类 handler。 |
| `meeting.py` | 会议引擎 `MeetingEngine`：管理 `Meeting` 生命周期、轮流发言、广播、自由讨论、会议纪要归档。 |
| `orchestrator.py` | 编排器 `ArgusOrchestrator`：组合 bus、router、agents、memory_store、health-check loop 与 GUI 后端生命周期。 |

### `argus/adapters/`

`nanobot_agent.py` 是 Argus 与 nanobot 之间的唯一集成边界：

- 为每个 `agent` 节点创建独立的 `AgentLoop`、`SessionManager` 与 `ToolRegistry`。
- 注入 Argus 专属工具 `argus_send_message`，使 Agent 可以向协作树中的可达节点发送消息。
- 通过 `_ArgusSystemPromptHook` 向 Agent 系统提示追加当前节点 ID、可达节点、通信规则等上下文。
- 提供 `start` / `stop` / `send_to_agent` / `status` 生命周期接口。

### `argus/memory/`

`store.py` 实现五层记忆存储，所有数据以 Markdown/YAML 文件形式持久化：

| 层级 | 目录 | 用途 |
|------|------|------|
| 项目记忆 | `memory/projects/` | 保存项目配置、任务历史、结果。 |
| 团队记忆 | `memory/team/` | 追加最佳实践与失败教训。 |
| Agent 档案 | `memory/agents/` | 记录 Agent 任务数、成功率、技能、平均耗时。 |
| 会议纪要 | `memory/meetings/` | 按日期归档会议完整记录。 |
| 协作模式库 | `memory/modes/` | 保存常用协作树配置，支持评分与按项目类型推荐。 |

### `argus/cli/`

`main.py` 使用 Typer 提供 CLI：

- `onboard`：初始化 `~/.argus/`。
- `gateway`：加载配置并启动完整 Gateway。
- `agent --node <id>`：以人类节点身份进入交互会话。
- `status`：显示 Gateway 运行状态或协作树概览。

### `argus/gui/`

`server.py` 提供 FastAPI/UVicorn 后端：

- REST API：获取/保存协作树、查询节点状态、发送消息、获取消息历史、会议生命周期。
- WebSocket `/ws`：实时广播消息到前端。
- 通过 `GuiServerState` 与 `ArgusOrchestrator` 共享状态。

### `argus/config/`

- `schema.py`：`ArgusConfig` 继承 nanobot `Config`，新增 `argus` 专属字段。
- `loader.py`：加载/保存 `~/.argus/config.json`，支持自动补全缺失字段。

## 协作树数据模型

```yaml
nodes:
  - id: human
    label: "我"
    type: human

  - id: dev
    label: "开发"
    type: agent
    agent_id: coding
    model: openrouter/openai/gpt-4o

edges:
  - from: human
    to: dev
    bidirectional: true
```

- `Node.id` 是消息路由中的唯一标识。
- `Node.type` 只能是 `human` 或 `agent`；`agent` 必须提供 `agent_id`。
- `Edge.bidirectional=true` 会展开为两条有向边。
- `CollaborationTree` 校验节点引用、重复边，并提供 `can_communicate(from, to)` 与 `get_reachable_nodes(from)`。

## 消息路由流程

1. **发送**：某节点调用 `ArgusBus.send_private` 或 `ArgusBus.send_group`。
2. **入队**：`dispatch` 将消息放入目标节点的队列，并触发该节点的回调集合。
3. **路由**：`MessageRouter._on_message` 被调用，根据 `message.to` 的长度判断私聊/群聊。
   - 私聊：检查 `tree.can_communicate(from, target)`，通过则交付。
   - 群聊：计算 `reachable ∩ target` 或 `@mention` 过滤后的集合，逐个交付。
4. **交付**：
   - 目标为 `agent`：调用 `NanobotAgentNode.send_to_agent`，将消息注入该 Agent 的 nanobot 入站队列。
   - 目标为 `human`：调用注册的人类 handler（CLI 打印、channel 发送、GUI 推送等）。

群聊 `@mention` 规则：

- `@all` 表示所有可达节点。
- `@dev @writer` 只将消息投递给 `dev` 与 `writer`（且必须与发送者可达）。
- 未使用 `@` 时，按 `to` 字段或广播处理。

## Agent 适配层说明

`NanobotAgentNode` 封装一个 nanobot Agent 实例：

1. 接收 `Node`、`CollaborationTree`、`ArgusBus`、`ArgusConfig`、工作目录。
2. 根据 `node.model` 或配置默认值选择 LLM Provider。
3. 创建独立的 `AgentLoop`，并注入 `ArgusSendMessageTool`。
4. 启动时向 `ArgusBus` 注册节点；停止时关闭 `AgentLoop` 与 MCP。
5. `send_to_agent(text)` 将 Argus 消息包装为 nanobot `InboundMessage` 推入 Agent 队列。

`ArgusSendMessageTool.execute` 负责把 Agent 的回复重新发送到 `ArgusBus`，形成闭环。

## 记忆传承系统五层结构

```
memory/
├── projects/
│   └── <project_id>.md        # frontmatter + task history
├── team/
│   ├── best_practices.md      # 追加式 Markdown
│   └── lessons_learned.md     # 追加式 Markdown
├── agents/
│   └── <agent_id>.md          # frontmatter + skills/notes
├── meetings/
│   └── <YYYY-MM-DD>.md        # frontmatter + transcript
└── modes/
    └── <mode_name>.yaml       # 完整协作树 + ratings
```

- `MemoryStore.save_project` / `load_project`：项目记忆读写。
- `append_best_practice` / `append_lesson`：团队经验追加。
- `update_agent_profile` / `load_agent_profile`：Agent 档案更新。
- `save_meeting` / `load_meeting` / `list_meetings`：会议纪要归档。
- `save_mode` / `rate_mode` / `recommend_mode`：模式保存、评分与基于项目类型的推荐。

## GUI 前后端交互

### 后端

`argus/gui/server.py` 启动 FastAPI 应用：

- `GET /api/tree`：返回当前协作树。
- `POST /api/tree`：保存并切换新的协作树。
- `GET /api/nodes` / `/api/nodes/{id}/status`：节点列表与状态。
- `POST /api/messages`：发送消息。
- `GET /api/messages/{node_id}`：获取节点相关消息历史。
- `POST /api/meetings` / `GET /api/meetings/{id}` / `POST /api/meetings/{id}/close`：会议生命周期。
- `WebSocket /ws`：实时消息广播，前端连接后自动同步新消息。

### 前端

`gui/` 目录为 Tauri 2.0 + Vue 3 项目：

- `TreeEditor.vue`：使用 Vue Flow 渲染协作树，支持拖拽创建节点/连线、属性面板编辑。
- `ChatView.vue`：显示选中节点会话历史并发送消息。
- `MeetingView.vue`：显示会议参与者、发言顺序、历史记录。
- `StatusView.vue`：显示各节点运行状态。
- `api.ts`：封装 HTTP API 调用。

前端通过 HTTP 与后端通信，并通过 WebSocket 接收实时消息推送，保证聊天与会议视图的即时更新。
