# Argus 多 Agent 协作编排平台构建规格

## Why

nanobot 是一个轻量级的个人 AI Agent（OpenClaw 的简化实现），提供单 Agent 会话、工具调用、Subagent、多渠道接入等核心能力，但缺乏多 Agent 之间的协作编排。Argus 的目标是在 nanobot 之上构建一层协作编排层，让用户可以通过可视化协作树自由定义人类与多个 AI Agent 的协作拓扑，实现私聊、群聊、会议等原生多 Agent 通信模式，并建立可传承的团队记忆系统。

## What Changes

- 以 nanobot 为运行时基础，在其之上构建 Argus 编排核心与 GUI
- 新增协作树（Collaboration Tree）数据模型、解析器与持久化
- 新增多 Agent 消息路由系统：私聊、群聊、会议
- 新增 Argus Agent 节点管理器，支持在同一进程中运行多个 nanobot Agent 实例
- 新增五层记忆传承系统（项目/团队/Agent 档案/会议/模式库）
- 新增 Tauri 2.0 + Vue 3 可视化协作树编辑器与聊天视图
- 新增 `argus` CLI 与 `argus gateway` 入口命令
- **BREAKING**：Argus 作为独立产品，命名空间从 `nanobot` 切换到 `argus`，但内部保留 `nanobot` 作为 Agent 运行时库

## Impact

- 新增能力：协作树编排、多 Agent 通信、人类节点、记忆传承、可视化 GUI
- 受影响代码：新增 `argus/` 顶层包、`argus/core/`、`argus/gui/`、`argus/cli/` 等
- nanobot 源码作为依赖/子目录保留，不直接修改其 Agent 核心逻辑，只通过适配层调用

## ADDED Requirements

### Requirement: 项目结构与命名空间

Argus 项目 SHALL 建立清晰的顶层结构，将 nanobot 作为 Agent 运行时库集成，而非直接修改 nanobot 代码。

#### Scenario: 源码布局
- **WHEN** 开发者查看项目根目录
- **THEN** 应看到 `nanobot/`（nanobot 源码）、`argus/`（Argus 新代码）、`gui/`（Tauri 前端）、`config/`（协作树配置示例）、`memory/`（记忆存储）

#### Scenario: 可安装包
- **WHEN** 用户执行 `pip install -e .`
- **THEN** 应安装 `argus` 包，同时保留 `nanobot` 包可用

### Requirement: 协作树数据模型

Argus SHALL 提供 YAML/JSON 协作树配置格式，支持节点、连线、属性的完全自定义。

#### Scenario: 节点定义
- **WHEN** 用户定义一个节点
- **THEN** 节点 SHALL 包含 `id`、`label`、`type`（`human` 或 `agent`）、`agent_id`（agent 类型必填）、`delivery`（human 类型可选）、`metadata`（任意自定义字段）

#### Scenario: 连线定义
- **WHEN** 用户定义一条连线
- **THEN** 连线 SHALL 包含 `from`、`to`、`bidirectional`（布尔值，默认 false）

#### Scenario: 通信权限
- **WHEN** 消息从节点 A 发往节点 B
- **THEN** 系统 SHALL 检查协作树中是否存在从 A 到 B 的有向路径；若不存在则拒绝投递
- **AND** 当 `bidirectional=true` 时， SHALL 视为 A→B 和 B→A 两条有向边

#### Scenario: 完全自定义
- **WHEN** 用户编辑协作树
- **THEN** 系统 SHALL 不提供任何预设模式，所有节点、连线和属性由用户自由定义

### Requirement: 多 Agent 运行时管理

Argus SHALL 能够基于 nanobot 的 `AgentLoop`/`AgentRunner` 在同一进程中启动并管理多个 Agent 节点。

#### Scenario: Agent 节点启动
- **WHEN** 协作树配置加载后
- **THEN** 系统 SHALL 为每个 `type=agent` 的节点创建独立的 `AgentLoop` 实例，每个实例拥有独立的 session 上下文和系统提示

#### Scenario: Agent 系统提示
- **WHEN** Agent 节点运行
- **THEN** 系统 SHALL 向 Agent 注入协作树上下文，包括：当前节点 ID、可达节点列表、通信规则、角色描述

#### Scenario: Agent 工具注入
- **WHEN** Agent 节点执行
- **THEN** 系统 SHALL 注入 `argus_send_message` 工具，允许 Agent 向其他节点发送消息
- **AND** 保留 nanobot 原有工具（read/write/edit/exec/web_search 等）

### Requirement: 消息路由系统

Argus SHALL 实现统一消息路由层，支持私聊和群聊两种通信模式，所有通信由协作树连线定义。

#### Scenario: 私聊
- **WHEN** 消息 `to` 字段只包含一个节点
- **THEN** 系统 SHALL 仅将消息投递给该节点
- **AND** 投递前 SHALL 验证发送者与目标节点之间存在有向连线

#### Scenario: 群聊
- **WHEN** 消息 `to` 字段为空或包含多个节点
- **THEN** 系统 SHALL 将消息投递给所有与发送者有连线的目标节点
- **AND** 支持 `@node_id` 提及语法过滤接收者

#### Scenario: 统一消息格式
- **WHEN** 任意节点发送消息
- **THEN** 消息 SHALL 包含 `from`、`to`、`text`、`reply_to`（可选）

#### Scenario: 人类节点通信
- **WHEN** human 节点通过 Telegram/WhatsApp/Discord 等渠道发送消息
- **THEN** 系统 SHALL 通过 nanobot 的 channel 层接收并路由到目标 Agent
- **AND** 当 Agent 回复 human 时， SHALL 通过配置的 `delivery.channel` 和 `delivery.chat_id` 发送

### Requirement: 会议功能

Argus SHALL 支持基于协作树的会议功能，通过群聊 + 轮流发言实现。

#### Scenario: 发起会议
- **WHEN** 用户调用 `startMeeting(organizer, participants, topic)`
- **THEN** 系统 SHALL 通知所有参与者会议开始
- **AND** 按顺序请求每个参与者发言
- **AND** 将每个发言广播给所有参与者
- **AND** 最后开放自由讨论

#### Scenario: 会议上下文
- **WHEN** 会议进行中
- **THEN** 每个 Agent 参与者 SHALL 收到完整会议历史作为上下文

### Requirement: 记忆传承系统

Argus SHALL 构建五层记忆体系，支持团队经验的沉淀、迁移与智能推荐。

#### Scenario: 项目记忆
- **WHEN** 项目运行结束或用户触发归档
- **THEN** 系统 SHALL 将项目配置、任务历史、结果记录写入 `memory/projects/<project_id>.md`

#### Scenario: 团队记忆
- **WHEN** 项目运行过程中产生最佳实践或失败教训
- **THEN** 系统 SHALL 将信息写入 `memory/team/best_practices.md` 或 `memory/team/lessons_learned.md`

#### Scenario: Agent 成长档案
- **WHEN** Agent 完成任务
- **THEN** 系统 SHALL 更新 `memory/agents/<agent_id>.md`，记录擅长任务类型、历史表现、技能进化

#### Scenario: 会议纪要库
- **WHEN** 会议结束
- **THEN** 系统 SHALL 将会议记录写入 `memory/meetings/YYYY-MM-DD.md`

#### Scenario: 协作模式库
- **WHEN** 用户保存常用协作树配置
- **THEN** 系统 SHALL 将其写入 `memory/modes/<mode_name>.yaml`
- **AND** 后续 SHALL 根据历史效果评分推荐最优模式

#### Scenario: 记忆传承效果
- **WHEN** 用户第二次创建同类型项目
- **THEN** 系统 SHALL 推荐历史最佳协作树配置和节点组合

### Requirement: 可视化 GUI

Argus SHALL 提供基于 Tauri 2.0 + Vue 3 的桌面 GUI，支持协作树可视化编辑、节点属性面板、聊天视图和会议视图。

#### Scenario: 协作树编辑器
- **WHEN** 用户打开 GUI
- **THEN** 应看到画布，可拖拽创建节点、拖拽连线、编辑节点属性、删除节点/连线

#### Scenario: 节点面板
- **WHEN** 用户选中节点
- **THEN** 应显示属性面板，可编辑 id、label、type、agent_id、model、delivery、metadata 等字段

#### Scenario: 聊天视图
- **WHEN** 用户选中某个节点或会话
- **THEN** 应显示该节点相关的聊天记录，并支持发送消息

#### Scenario: 会议视图
- **WHEN** 用户发起会议
- **THEN** 应显示会议参与者、发言顺序、当前发言者、历史发言记录

### Requirement: CLI 与 Gateway

Argus SHALL 提供命令行入口，支持初始化、运行 gateway、运行 CLI Agent 会话。

#### Scenario: 初始化
- **WHEN** 用户执行 `argus onboard`
- **THEN** 系统 SHALL 创建 `~/.argus/` 配置目录、默认 `config.json`、示例协作树、记忆目录

#### Scenario: 启动 Gateway
- **WHEN** 用户执行 `argus gateway`
- **THEN** 系统 SHALL 加载配置、启动所有 Agent 节点、启动 GUI 后端服务、启动 channel 监听

#### Scenario: CLI 交互
- **WHEN** 用户执行 `argus agent -m "..."`
- **THEN** 系统 SHALL 作为 human 节点与协作树中的 Agent 交互

### Requirement: 状态监控

Argus SHALL 监控所有节点（human + agent）的运行时状态，确保系统正常运行。

#### Scenario: 状态展示
- **WHEN** 用户查看 GUI 状态面板或执行 `argus status`
- **THEN** 应看到每个 Agent 节点的运行状态、最后活动时间、当前任务、会话数量

#### Scenario: 异常处理
- **WHEN** 某个 Agent 节点崩溃或长时间无响应
- **THEN** 系统 SHALL 记录日志，并在 GUI 中标记该节点为异常

### Requirement: 与 nanobot 的集成边界

Argus SHALL 清晰定义与 nanobot 的集成边界，避免侵入 nanobot 核心代码。

#### Scenario: 复用能力
- **WHEN** Argus 需要 Agent 执行能力
- **THEN** 应调用 nanobot 的 `AgentLoop`、`AgentRunner`、`ToolRegistry`、`SessionManager`、`ChannelManager`

#### Scenario: 扩展能力
- **WHEN** Argus 需要多 Agent 协作能力
- **THEN** 应在 nanobot 之上新增 `argus/core/` 编排层，不直接修改 `nanobot/agent/` 等目录

## MODIFIED Requirements

### Requirement: 配置文件

nanobot 的 `~/.nanobot/config.json` 配置 SHALL 扩展为 Argus 的 `~/.argus/config.json`，新增 `argus` 专属字段。

#### Scenario: 配置兼容性
- **WHEN** Argus 加载配置
- **THEN** 应保留 nanobot 原有 `providers`、`agents`、`channels`、`tools` 字段
- **AND** 新增 `argus.collaboration_tree`（默认协作树路径）、`argus.memory`（记忆目录）、`argus.gui`（GUI 端口等）字段

### Requirement: Agent 工具集

nanobot Agent 的工具列表 SHALL 扩展 Argus 专属工具。

#### Scenario: 新增 argus_send_message 工具
- **WHEN** Agent 在 Argus 模式下运行
- **THEN** 工具列表 SHALL 包含 `argus_send_message`，参数为 `to`、`text`、`is_group`（可选）

## REMOVED Requirements

### Requirement: nanobot 单一 Agent 交互模式
**Reason**：Argus 的核心是多人/多 Agent 协作，单一 Agent CLI 模式被协作树驱动的 human 节点交互取代。
**Migration**：原有 `nanobot agent` 行为由 `argus agent --node <human_node_id>` 提供。
