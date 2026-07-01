# Argus 快速入门

本文档带你从零开始安装 Argus、初始化工作空间、编写第一个协作树、启动 Gateway 并与 Agent 交互。

## 环境准备

- Python 3.11 或更高版本
- （可选）Node.js 18+ 与 npm，用于构建/运行 Tauri GUI 前端

## 安装

```bash
git clone <repo-url>
cd argus
pip install -e .
```

验证安装：

```bash
python -c "import argus; print('ok')"
argus --help
```

## `argus onboard` 详解

`onboard` 命令会在用户主目录创建 Argus 工作空间：

```bash
argus onboard
```

执行后生成以下结构：

```
~/.argus/
├── config.json                  # Argus 配置文件
├── collaboration_tree.yaml      # 默认示例协作树
└── memory/                      # 五层记忆目录
    ├── projects/                # 项目记忆
    ├── team/
    │   ├── best_practices.md    # 团队最佳实践
    │   └── lessons_learned.md   # 失败教训
    ├── agents/                  # Agent 成长档案
    ├── meetings/                # 会议纪要库
    └── modes/                   # 协作模式库
```

`onboard` 是幂等的：重复执行不会覆盖已有文件。

### 配置说明

`~/.argus/config.json` 包含 Argus 专属 `argus` 字段：

```json
{
  "argus": {
    "collaborationTree": "~/.argus/collaboration_tree.yaml",
    "memoryDir": "~/.argus/memory",
    "guiHost": "127.0.0.1",
    "guiPort": 18791,
    "apiHost": "127.0.0.1",
    "apiPort": 18792
  }
}
```

## 编写第一个协作树配置

协作树描述“谁能和谁说话”。编辑 `~/.argus/collaboration_tree.yaml`：

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
    metadata:
      role: "software developer"
      skills: ["python", "typescript"]

  - id: writer
    label: "写作"
    type: agent
    agent_id: writing
    model: openrouter/openai/gpt-4o
    metadata:
      role: "technical writer"
      skills: ["documentation", "markdown"]

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

规则：

- `type=agent` 的节点必须提供 `agent_id`。
- `bidirectional: true` 表示同时创建 `from -> to` 和 `to -> from` 两条有向边。
- 只有存在有向边的两个节点之间才能通信。

## 启动 Gateway 和 GUI

### 启动 Gateway

```bash
argus gateway
```

Gateway 会：

1. 加载 `~/.argus/config.json` 与 `~/.argus/collaboration_tree.yaml`
2. 为每个 `agent` 节点创建并启动内置 Agent 运行时
3. 启动 `ArgusBus` 消息总线与 `MessageRouter` 路由引擎
4. 启动 GUI 后端 HTTP/WebSocket 服务（默认 `http://127.0.0.1:18792`）
5. 进入事件循环，等待 `Ctrl+C` 优雅关闭

### 启动 Tauri GUI（可选）

如果你已安装 Node.js：

```bash
cd gui
npm install
npm run tauri dev
```

GUI 默认连接本地后端，提供：

- 协作树可视化编辑器
- 节点属性面板
- 聊天视图
- 会议视图
- 节点状态面板

## 使用 CLI agent 与 Agent 交互

在另一个终端执行：

```bash
argus agent --node human
```

进入交互模式后，输入消息即可发送。提及语法：

- `@dev 你好` —— 私聊 dev
- `@all 大家注意` —— 广播给所有可达节点
- `@dev @writer 开会` —— 群聊给 dev 和 writer

输入 `/quit` 或按 `Ctrl+C` 退出。

也可以直接发送一条初始消息：

```bash
argus agent --node human -m "@dev 请帮我写一段 Python 快速排序"
```

## 发起会议

目前会议通过 GUI 或 HTTP API 发起。使用 `curl` 示例：

```bash
curl -X POST http://127.0.0.1:18792/api/meetings \
  -H "Content-Type: application/json" \
  -d '{"organizer":"human","participants":["human","dev","writer"],"topic":"技术栈选型"}'
```

会议流程：

1. 通知所有参与者会议开始
2. 按顺序请求每个 Agent 发言
3. 将每次发言广播给所有参与者
4. 进入自由讨论阶段
5. 调用 `/api/meetings/{meeting_id}/close` 结束并自动归档到 `~/.argus/memory/meetings/YYYY-MM-DD.md`

## 下一步

- 阅读 [`ARCHITECTURE.md`](./ARCHITECTURE.md) 了解系统架构与消息路由细节。
- 查看 `tests/e2e/` 中的端到端测试，学习如何以编程方式驱动 Argus。
