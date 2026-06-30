# Argus 功能展示

> Argus = **可观测、可接管、可继承** 的多 Agent 协作操作系统。

![Argus Hero](images/argus-hero.svg)

---

## 核心能力一览

| 能力 | 说明 | 适合场景 |
|------|------|----------|
| **协作树** | 用有向图定义 human/agent 之间的通信链路 | 多角色项目团队 |
| **消息总线** | 私聊/群聊按可达性路由，@mention 过滤 | 定向通知、分组讨论 |
| **会议引擎** | 轮询发言 + 自由讨论，后台异步运行 | 方案评审、迭代规划 |
| **Human 接管** | `skip_turn` / `update_topic` / `close` | 需要人类把关的关键决策 |
| **Inbox 持久化** | 离线消息落盘，上线自动 drain | 异步协作、跨时区团队 |
| **五层记忆** | 项目/团队/个体/会议/模式记忆逐层沉淀 | 经验复用、长期项目 |
| **GUI / CLI** | Tauri + Vue3 桌面界面 + Python CLI | 本地调试、日常运营 |

---

## 1. 协作树：让沟通有边界

![Collaboration Tree](images/collaboration-tree.svg)

Argus 不假设所有节点都能互相通信。通过 **有向边** 显式定义谁能给谁发消息：

- **实线箭头**：消息可发送
- **虚线箭头**：反向可回复
- **无连接**：不可达，消息会被拦截

这带来两个好处：
1. **安全**：避免敏感信息被无关 agent 收到。
2. **清晰**：团队拓扑即代码，新人一眼看懂组织关系。

> 使用场景：一个产品团队里，PM 只向 dev 提需求，dev 与 writer 互相协作，writer 不能直接向 PM 发版。

---

## 2. Human 接管会议：机器开会，人类把关

![Meeting Takeover](images/meeting-takeover.svg)

会议一旦启动，Agent 按轮询依次发言。Human 不需要等待，可以随时通过命令队列插入控制：

- `skip_turn`：跳过当前 agent 的发言
- `update_topic`：动态修改会议主题
- `close`：立即结束会议

整个会议在 **后台 task** 中运行，human 的命令异步处理，不会阻塞其他 agent 的日常工作。

> 使用场景：凌晨让 agent 们自动评审 PR，早上人类上线后发现某个 agent 卡住了，直接 `skip_turn` 继续。

---

## 3. Inbox 持久化：离线不断线

![Inbox Persistence](images/inbox-persistence.svg)

Human 节点会离线。Argus 的做法是：

1. Human 离线时，发给它的消息进入 `human_inboxes/{node_id}.inbox.json`。
2. Agent 继续自己的工作，**不被阻塞**。
3. Human 重新上线后，inbox 自动 drain，离线消息一次性推送。

每个 human 有独立 inbox，容量上限 1000 条，重启后仍可恢复。

> 使用场景：创始人白天开会，agent 夜间自动整理日报；第二天早上打开 Argus，所有消息都在。

---

## 4. 使用场景示例

### 场景 A：AI 创业小团队

- **human**：创始人
- **agent**：dev（写代码）、writer（写文案）、pm（整理需求）
- **协作树**：创始人连接所有人；dev 与 writer 互相协作；pm 单向接收创始人输入。
- **典型会议**："下周产品迭代规划"，由 pm 组织，dev 和 writer 发言，创始人随时 `skip_turn` 或 `update_topic`。

### 场景 B：24x7 自动化运维

- **human**：值班工程师
- **agent**：monitor、debugger、executor、reporter
- **协作树**：monitor 发现异常 → debugger 分析 → executor 执行修复 → reporter 生成报告给 human。
- **inbox 持久化**：异常报告在 human 离线时暂存，上线后立即收到。

### 场景 C：内容生产线

- **human**：主编
- **agent**：researcher、writer、editor、reviewer
- **会议模式**："本月专题策划"，researcher 先提供资料，writer 出稿，editor 润色，reviewer 审稿，主编最终 `close` 定稿。

---

## 5. 快速体验 GUI

```bash
# 不消耗 LLM API，使用 mock agent
python scripts/start_gui_for_demo.py
```

然后打开 http://127.0.0.1:18793，即可看到：

- **Tree**：可视化编辑协作树
- **Chat**：按节点私聊或群聊
- **Meeting**：发起会议并实时查看会议状态
- **Status**：查看所有节点在线/运行状态

> 注意：启动真实 LLM 需要复制 `config/example_config.json` 并填入自己的 API Key。

---

## 6. 技术亮点

- **Spec-driven**：从 `argus项目介绍.md` 出发，逐步实现每一个细节。
- **Memory inheritance**：五层记忆架构让经验可积累、可迁移。
- **Async by default**：所有消息路由和会议执行都是异步的，保证系统响应性。
- **Mock mode**：`mock=True` 即可零成本运行全部功能，方便开发和演示。

---

* Argus 适合那些想让多个 AI Agent 真正协作、同时保留人类最终决策权的团队。*
