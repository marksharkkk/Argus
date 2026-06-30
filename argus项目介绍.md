# Argus 项目开发计划书

> 👁️ **Argus** - 智能 多Agent 协作工具
> 
> *人类和agent都是协作树上的节点，未来的全新协作模式*

---

## 📌 项目概述

**Argus** 是一个基于 OpenClaw 的多Agent 协作工具。

### 命名来源

**Argus**（阿尔戈斯）- 希腊神话中的百眼巨人，拥有 100 只眼睛，睡觉时也有眼睛睁着，象征"全方位监控"。

---

## 🔄 核心设计简化（2026-03-06 更新）

### 设计原则变更

**1. 协作树完全自定义**
- ❌ 不再有"预设模式"（Team-Leader、顾问团等）
- ✅ 人类用图形界面自由拖拽节点和连线
- ✅ 每个节点/连线由人类定义属性和规则
- ✅ 人类自己也是一个节点（可定义位置）

**2. 通信机制简化**
- ❌ 不再区分 5 种通信类型（太复杂）
- ✅ 只有两种：**私聊**（一对一）和**群聊**（多对多）
- ✅ 所有通信走统一消息格式
- ✅ 由协作树的连线定义谁能和谁说话

**3. 技术栈确定**
- 编排层：**Node.js**（与 OpenClaw 同生态）
- GUI: **Tauri 2.0**（支持 Linux，后续考虑 Windows）
- 前端：Vue 3 / React（待定）

---

### OpenClaw 机制分析

**架构：**
```
┌─────────────────────────────────────────────────────────┐
│                    OpenClaw                             │
├─────────────────────────────────────────────────────────┤
│  定位：自托管网关（Self-hosted Gateway）                 │
│  连接：WhatsApp/Telegram/Discord/iMessage → AI Agent   │
│  运行时：嵌入式 pi-mono agent                           │
│                                                         │
│  核心概念：                                              │
│  - Gateway：单一事实来源（会话、路由、频道连接）          │
│  - Agent：独立的大脑（workspace + agentDir + sessions）  │
│  - Session：对话上下文（JSONL 转录 + 状态存储）           │
│  - Channel：消息渠道（WhatsApp/Telegram 等）             │
│  - Binding：入站消息路由规则                             │
└─────────────────────────────────────────────────────────┘
```

**OpenClaw 会话机制：**
```
会话类型：
├── 主会话 (main): agent:<agentId>:main
│   └── 默认所有 DM 共享（dmScope: "main"）
│
├── 每用户会话 (per-peer): agent:<agentId>:dm:<peerId>
│   └── 按发送者隔离
│
├── 每频道会话 (per-channel-peer): agent:<agentId>:<channel>:dm:<peerId>
│   └── 按频道 + 发送者隔离（推荐）
│
└── 群组会话：agent:<agentId>:<channel>:group:<id>
    └── 每个群组独立
```

**OpenClaw Subagent 机制：**
```
Subagent 是后台运行的独立 Agent 会话：

创建：
- sessions_spawn(task, agentId?, model?, thread?, mode?)
- 会话键：agent:<agentId>:subagent:<uuid>
- 模式：run（一次性）或 session（持久）

通信：
- sessions_send(sessionKey, message) - 发送消息到子 Agent
- sessions_history(sessionKey) - 获取历史
- subagents steer(id, message) - 指导子 Agent
- subagents kill(id) - 终止子 Agent

完成：
- 自动 announce 结果回请求者频道
- 可配置自动归档（默认 60 分钟）

嵌套：
- maxSpawnDepth: 1（默认）- 子 Agent 不能再生子
- maxSpawnDepth: 2 - 支持 orchestrator 模式
  主 Agent → 编排子 Agent → 工作子子 Agent
```

**OpenClaw 多 Agent 路由：**
```json5
{
  agents: {
    list: [
      { id: "coding", workspace: "~/.openclaw/workspace-coding" },
      { id: "social", workspace: "~/.openclaw/workspace-social" },
    ]
  },
  bindings: [
    {
      agentId: "coding",
      match: { channel: "whatsapp", peer: { kind: "direct", id: "+1234567890" } }
    },
    {
      agentId: "social",
      match: { channel: "telegram", accountId: "*" }
    }
  ]
}
```

**OpenClaw 工具系统：**
```
核心工具：
- read/write/edit/exec - 文件操作
- web_search/web_fetch - 网络访问
- browser - 浏览器控制
- message - 消息发送
- sessions_* - 会话管理
- subagents - 子 Agent 管理
- memory_* - 记忆管理

Skill 系统：
-  bundled: ~/.nodejs/lib/node_modules/openclaw/skills
-  managed: ~/.openclaw/skills
-  workspace: <workspace>/skills
```

---

### Argus 定位

**Argus = OpenClaw Subagent 系统 + 协作编排层 + 可视化界面**

```
┌─────────────────────────────────────────────────────────┐
│                    Argus 架构                           │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  前端：Tauri 2.0 / Electron (支持 Linux + Web)          │
│        或纯 Web 界面 + 本地后端                          │
│                                                         │
│  编排层：Python/Node.js                                 │
│  - 协作模式解析器（YAML/JSON树状图）                     │
│  - 任务调度器                                           │
│  - 通信路由器（私聊/广播/会议）                          │
│  - 记忆管理器                                           │
│                                                         │
│  OpenClaw 适配层：                                       │
│  - sessions_spawn → 创建 Agent 节点                      │
│  - sessions_send → 节点间通信                           │
│  - subagents steer → 任务指导                          │
│  - memory 读写 → 传承系统                              │
│                                                         │
│  Subagent 团队：                                         │
│  Human(节点) ←→ Leader ←→ Dev1 ←→ Dev2 ←→ QA          │
│  (所有节点都是对等的，人类也是节点)                       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 🎯 核心差异化

| 维度            | Golutra       | OpenClaw    | Argus        |
| ------------- | ------------- | ----------- | ------------ |
| **定位**        | 终端管理器         | 消息网关        | 协作编排器        |
| **协作模式**      | 固定（人类→Agent）  | 无           | 可自定义树状图      |
| **通信方式**      | 私聊（终端注入）      | DM/群组       | 私聊 + 广播 + 会议 |
| **节点对等**      | ❌ 人类是监工       | ❌ Agent 是助理 | ✅ 人类也是节点     |
| **状态监控**      |  ❌仅有agent状态     |❌无    | ✅ 人类、agent都有，确保系统正常运行|
| **Agent 间通信** | ❌ 无           | ⚠️ 有限       | ✅ 原生支持       |
| **记忆系统**      | ❌ 无           | ✅ 每 Agent   | ✅ 团队共享记忆     |
| **协作模式**      | ❌ 固定          | ❌ 无         | ✅ 图形化定义      |
| **平台**        | Windows/macOS | 全平台 (CLI)   | Linux + Web  |

---

## 🌳 协作树设计（简化版）

### 核心理念

**完全自定义，无预设模式**

```
┌─────────────────────────────────────────────────────────┐
│              协作树（自由拖拽编辑）                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  节点（Node）：                                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                │
│  │  Human  │  │ Agent1  │  │ Agent2  │   ...          │
│  └─────────┘  └─────────┘  └─────────┘                │
│       ↓            ↓            ↓                      │
│   属性面板     属性面板     属性面板                    │
│                                                         │
│  连线（Edge）：                                         │
│  Human ───→ Agent1  （单向：人类→Agent1）              │
│  Human ←───→ Agent2 （双向：互相通信）                 │
│  Agent1 ←──→ Agent2 （Agent 间直接交流）               │
│                                                         │
│  规则：                                                  │
│  - 有连线 = 可以通信                                    │
│  - 无连线 = 不能直接说话                                │
│  - 箭头方向 = 通信方向                                  │
│  - 人类也是节点，位置随意                               │
└─────────────────────────────────────────────────────────┘
```

### 节点定义（Node）

```yaml
# 完全自定义，人类自由填写
nodes:
  - id: human
    label: "我"
    type: human
    delivery:
      channel: telegram
      chat_id: "6289012035"
    metadata:
      描述：项目决策者
      
  - id: agent1
    label: "开发助手"
    type: agent
    agent_id: coding  # OpenClaw agent ID
    model: gpt-4
    metadata:
      擅长：Python 开发
      
  - id: agent2
    label: "测试助手"
    type: agent
    agent_id: testing
    model: gpt-4o
    metadata:
      擅长：自动化测试
```

**节点属性（GUI 中编辑）：**
- `id` - 唯一标识（自动生成）
- `label` - 显示名称（人类填写）
- `type` - human / agent
- `agent_id` - OpenClaw agent ID（agent 节点需要）
- `delivery` - 人类节点的消息渠道（Telegram/WhatsApp 等）
- `metadata` - 任意自定义字段（描述、擅长领域等）

---

### 连线定义（Edge）

```yaml
# 连线定义谁能和谁说话
edges:
  - from: human
    to: agent1
    bidirectional: true  # 双向通信
    
  - from: human
    to: agent2
    bidirectional: true
    
  - from: agent1
    to: agent2
    bidirectional: true  # Agent 间可以直接交流
```

**连线属性（GUI 中编辑）：**
- `from` - 起始节点 ID
- `to` - 目标节点 ID
- `bidirectional` - 是否双向（true/false）

---

### 示例：简单三人团队

```yaml
# 人类自定义的协作树
nodes:
  - id: human
    label: "我"
    type: human
    delivery:
      channel: telegram
      
  - id: dev
    label: "开发"
    type: agent
    agent_id: coding
    
  - id: writer
    label: "写作"
    type: agent
    agent_id: writing

edges:
  - from: human
    to: dev
    bidirectional: true
    
  - from: human
    to: writer
    bidirectional: true
    
  - from: dev
    to: writer
    bidirectional: true  # 开发和写作可以直接讨论
```

**效果：**
```
    我
   / \
  ↓   ↓
开发 ←→ 写作

我可以和开发/写作说话
开发和写作也可以直接讨论
```

---

### 示例：复杂项目团队

```yaml
nodes:
  - id: human
    label: "项目经理"
    type: human
    
  - id: leader
    label: "技术负责人"
    type: agent
    agent_id: tech-lead
    
  - id: dev1
    label: "前端"
    type: agent
    agent_id: frontend
    
  - id: dev2
    label: "后端"
    type: agent
    agent_id: backend
    
  - id: qa
    label: "测试"
    type: agent
    agent_id: qa

edges:
  # 经理只和负责人说话
  - from: human
    to: leader
    bidirectional: true
    
  # 负责人管理所有人
  - from: leader
    to: dev1
    bidirectional: true
  - from: leader
    to: dev2
    bidirectional: true
  - from: leader
    to: qa
    bidirectional: true
    
  # 开发和测试可以讨论
  - from: dev1
    to: dev2
    bidirectional: true
  - from: dev1
    to: qa
    bidirectional: true
  - from: dev2
    to: qa
    bidirectional: true
```

**可视化：**
```
    经理
      │
      ↓
   负责人
   /  |  \
  ↓   ↓   ↓
前端 ←→ 后端
  ↖   ↗
    测试
```

---

## 💬 通信机制（简化版）

### 核心原则

**只有两种通信：**

1. **私聊** - 一对一（有连线就能说话）
2. **群聊** - 多对多（@所有人 或 @特定节点）

**没有复杂的类型区分，所有消息统一格式。**

---

### 消息格式

```yaml
# 统一消息格式（超级简单）
message:
  from: human  # 发送者节点 ID
  to: [dev]    # 接收者列表（空 = 群聊）
  text: "这个功能怎么做？"
  reply_to: uuid?  # 回复某条消息（可选）
```

---

### 通信规则

**由协作树的连线自动决定：**

```yaml
# 协作树配置
edges:
  - from: human
    to: dev
    bidirectional: true
    
  - from: human
    to: writer
    bidirectional: true
    
  - from: dev
    to: writer
    bidirectional: true
```

**通信权限：**
```
human → dev     ✅ 有连线，可以
human → writer  ✅ 有连线，可以
dev → writer    ✅ 有连线，可以
dev → human     ✅ 双向连线，可以
writer → human  ✅ 双向连线，可以

# 如果没有连线
qa → dev        ❌ 无连线，不能直接说话
```

---

### 实现方式

#### 私聊（一对一）

```javascript
// 人类 → Agent
sessions_send({
  sessionKey: dev_session,
  message: "这个功能怎么做？"
})

// Agent → Agent
sessions_send({
  sessionKey: writer_session,
  message: "dev，我需要你的接口文档"
})

// Agent → 人类
message({
  action: "send",
  channel: "telegram",
  to: "6289012035",
  message: "任务完成了"
})
```

#### 群聊（一对多）

```javascript
// 人类 → 所有 Agent
const allAgents = [dev_session, writer_session]
for (const session of allAgents) {
  sessions_send({
    sessionKey: session,
    message: "@all 大家注意，有新需求"
  })
}

// 人类 → 特定几个 Agent
const targets = [dev_session, writer_session]
for (const session of targets) {
  sessions_send({
    sessionKey: session,
    message: "@dev @writer 你们讨论一下这个功能"
  })
}
```

---

### 群聊实现（@机制）

```javascript
// 解析 @提及
function parseMentions(text) {
  const mentions = text.match(/@(\w+)/g) || []
  return mentions.map(m => m.slice(1)) // 去掉 @
}

// 发送群聊消息
function sendGroupMessage(nodes, text, sender) {
  const mentions = parseMentions(text)
  
  for (const node of nodes) {
    // 如果被@了，或者没有指定@（全员消息）
    if (mentions.length === 0 || mentions.includes(node.id)) {
      sessions_send({
        sessionKey: node.session,
        message: text,
        context: {
          mentions: mentions,
          sender: sender
        }
      })
    }
  }
}

// 使用
sendGroupMessage(allNodes, "@dev @writer 你们讨论一下", "human")
```

---

### 会议功能（简化版）

**不需要复杂的状态机，用群聊 + 轮流发言实现：**

```javascript
// 人类发起会议
async function startMeeting(organizer, participants, topic) {
  // 1. 通知所有人
  sendGroupMessage(participants, `会议开始：${topic}`, organizer)
  
  // 2. 轮流发言
  for (const participant of participants) {
    const response = await sessions_send({
      sessionKey: participant.session,
      message: `请发表你的看法（关于：${topic}）`
    })
    
    // 3. 广播给所有人
    sendGroupMessage(participants, `${participant.label}: ${response}`, organizer)
  }
  
  // 4. 自由讨论（开放群聊）
  sendGroupMessage(participants, "现在自由讨论", organizer)
}
```

**效果：**
```
人类："会议开始：新需求讨论"
人类："开发，请发表你的看法"
开发："我觉得应该这样做..."
人类："开发说：我觉得应该这样做..."（广播给所有人）
人类："测试，请发表你的看法"
测试："我需要注意..."
人类："测试说：我需要注意..."（广播给所有人）
人类："现在自由讨论"
开发："@测试 你觉得这个方案可行吗？"
测试："@开发 可行，但我建议..."
```

---

### 人类节点通信

**人类通过 OpenClaw 的消息渠道接收：**

```javascript
// Agent → 人类
message({
  action: "send",
  channel: "telegram",  // 或 whatsapp/discord
  to: "6289012035",     // 人类聊天 ID
  message: "任务完成了"
})

// 人类 → Agent（通过 OpenClaw 路由）
// 人类在 Telegram 回复消息
// → OpenClaw 接收
// → Argus 监听到
// → 路由到对应的 Agent session
```

**实现：**
- 人类节点配置 `delivery.channel` 和 `delivery.chat_id`
- Agent 用 `message` 工具发送给人类
- 人类回复通过 OpenClaw 的 binding 路由回 Argus
- Argus 解析后转发给目标 Agent

---

### 简单示例：三人协作

```yaml
# 协作树
nodes:
  - id: human
    label: "我"
    type: human
  - id: dev
    label: "开发"
    type: agent
  - id: writer
    label: "写作"
    type: agent

edges:
  - from: human
    to: dev
    bidirectional: true
  - from: human
    to: writer
    bidirectional: true
  - from: dev
    to: writer
    bidirectional: true
```

**使用流程：**

```
1. 人类 → 开发（私聊）
   "这个功能怎么做？"
   
2. 开发 → 写作（私聊，因为有连线）
   "@writer 我需要你的内容结构"
   
3. 写作 → 开发（私聊）
   "@dev 结构是这样的..."
   
4. 人类 → 所有人（群聊）
   "@all 项目进度如何？"
   
5. 开发 → 人类（私聊）
   "完成 50%"
   
6. 写作 → 人类（私聊）
   "完成 80%"
```

**实现代码：**

```javascript
// 1. 人类 → 开发
sessions_send({
  sessionKey: dev_session,
  message: "这个功能怎么做？"
})

// 2. 开发 → 写作（Argus 自动路由）
// 检查协作树：dev → writer 有连线 ✅
sessions_send({
  sessionKey: writer_session,
  message: "@writer 我需要你的内容结构"
})

// 3. 人类 → 所有人
for (const node of [dev_session, writer_session]) {
  sessions_send({
    sessionKey: node,
    message: "@all 项目进度如何？"
  })
}
```

---

## 🧬 传承系统设计

### 记忆层次

```
┌─────────────────────────────────────────────────────────┐
│                   Argus 记忆系统                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Level 1: 项目记忆 (Project Memory)                     │
│  - 项目配置（协作树、节点定义）                          │
│  - 任务历史（执行过的任务）                              │
│  - 结果记录（成功/失败/耗时）                            │
│  存储：memory/projects/<project_id>.md                  │
│                                                         │
│  Level 2: 团队记忆 (Team Memory)                        │
│  - 最佳实践（什么任务用什么配置）                        │
│  - 失败教训（什么坑要避开）                              │
│  - 优化建议（如何做得更好）                              │
│  存储：memory/team/best_practices.md                    │
│        memory/team/lessons_learned.md                   │
│                                                         │
│  Level 3: Agent 成长档案 (Agent Profile)                │
│  - 擅长任务类型                                          │
│  - 历史表现评分                                          │
│  - 技能进化轨迹                                          │
│  存储：memory/agents/<agent_id>.md                      │
│                                                         │
│  Level 4: 会议纪要库 (Meeting Archive)                  │
│  - 历史会议记录                                          │
│  - 重要决议索引                                          │
│  - 任务变更追踪                                          │
│  存储：memory/meetings/YYYY-MM-DD.md                    │
│                                                         │
│  Level 5: 协作模式库 (Mode Library)                     │
│  - 预置模式模板                                          │
│  - 用户自定义模式                                        │
│  - 模式效果评分                                          │
│  存储：memory/modes/<mode_name>.yaml                    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 传承效果

```
第一次做 Web 开发项目：
- 人类手动配置协作树
- 选择节点角色
- 执行中遇到问题
- 记录到项目记忆

第二次：
- 系统推荐："上次 Web 项目用的这个配置，效果不错"
- 自动加载最佳实践
- 避免上次的坑
- Agent 成长档案更新

第十次：
- 系统自动推荐最优协作树
- 自动选择最佳节点组合
- 预估时间和风险
- 团队记忆持续进化
```

---

## 🛠️ 技术栈

### 编排层：Node.js + TypeScript

```
理由：
✅ 与 OpenClaw 同生态，集成方便
✅ 可以直接调用 OpenClaw 的 sessions_* 工具
✅ TypeScript 类型安全
✅ 用户熟悉（OpenClaw 也是 Node.js）

技术选型：
- 运行时：Node.js 22+
- 语言：TypeScript
- 包管理：pnpm
- 构建：esbuild / tsup
```

---

### GUI: Tauri 2.0

```
理由：
✅ 支持 Linux（用户当前系统）
✅ 支持 Windows（后续目标用户）
✅ 打包小（~10MB vs Electron ~100MB）
✅ 性能好（Rust 后端）
✅ 前端可以用 Vue/React/Svelte

技术选型：
- 框架：Tauri 2.0
- 前端：Vue 3 + TypeScript（或 React）
- 绘图：React Flow / Vue Flow（协作树拖拽）
- 打包：Tauri bundler（.deb, .rpm, .AppImage, .exe）

Windows 支持：
- Tauri 2.0 原生支持 Windows
- 打包生成 .msi / .exe
- 无需额外配置
```

---

### 项目结构

```
argus/
├── core/                    # 编排核心（Node.js）
│   ├── orchestrator.ts      # 主编排引擎
│   ├── node-manager.ts      # 节点管理（创建/销毁）
│   ├── message-router.ts    # 消息路由（私聊/群聊）
│   └── collaboration-tree.ts # 协作树解析
│
├── adapters/
│   └── openclaw.ts          # OpenClaw 适配层
│
├── memory/
│   ├── project-memory.ts    # 项目记忆
│   └── team-memory.ts       # 团队记忆
│
├── gui/                     # Tauri 前端
│   ├── src/
│   │   ├── components/
│   │   │   ├── TreeEditor.vue    # 协作树编辑器
│   │   │   ├── NodePanel.vue     # 节点面板
│   │   │   ├── ChatView.vue      # 聊天视图
│   │   │   └── MeetingView.vue   # 会议视图
│   │   └── App.vue
│   ├── src-tauri/          # Tauri Rust 后端
│   │   ├── src/
│   │   │   ├── main.rs
│   │   │   └── commands.rs   # Rust 命令（调用 Node.js）
│   │   └── Cargo.toml
│   └── package.json
│
├── package.json
└── tsconfig.json
```

---

### 数据存储

```yaml
# 协作树配置
config/:
  project-name.yaml    # 每个项目一个协作树配置

# 记忆系统（Markdown，兼容 OpenClaw）
memory/:
  projects/
    project-name.md    # 项目记忆
  team/
    best-practices.md  # 最佳实践
    lessons-learned.md # 失败教训
  agents/
    agent-id.md        # Agent 成长档案
  meetings/
    YYYY-MM-DD.md      # 会议纪要

# 运行时状态（JSON）
state/:
  active-sessions.json  # 活跃会话
  message-queue.json    # 消息队列
```
