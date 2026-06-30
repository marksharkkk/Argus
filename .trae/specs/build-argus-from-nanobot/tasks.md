# Tasks

## Phase 1: 基础设施与项目结构

- [ ] Task 1: 建立 Argus 顶层项目结构
  - [ ] SubTask 1.1: 将 nanobot-main 目录整理为项目可运行的 `nanobot/` 子包
  - [ ] SubTask 1.2: 创建 `argus/` 顶层包，包含 `core/`、`adapters/`、`memory/`、`cli/`、`gui/` 子模块
  - [ ] SubTask 1.3: 创建 `gui/` 目录作为 Tauri 2.0 + Vue 3 前端根目录
  - [ ] SubTask 1.4: 创建 `config/` 和 `memory/` 示例目录
  - [ ] SubTask 1.5: 编写根目录 `pyproject.toml`，支持 `pip install -e .` 同时安装 `argus` 和 `nanobot`
  - [ ] SubTask 1.6: 验证安装后在 Python 中可 `import argus` 和 `import nanobot`

- [ ] Task 2: Argus 配置系统
  - [ ] SubTask 2.1: 在 `argus/config/schema.py` 定义 `ArgusConfig`，扩展 nanobot 的 `Config`
  - [ ] SubTask 2.2: 新增 `argus` 字段：`collaboration_tree`（默认路径）、`memory_dir`、`gui`（host/port）
  - [ ] SubTask 2.3: 实现 `argus/config/loader.py` 加载 `~/.argus/config.json`
  - [ ] SubTask 2.4: 实现 `argus onboard` 命令，创建默认配置、示例协作树、记忆目录
  - [ ] SubTask 2.5: 验证 `argus onboard` 生成正确的目录结构和配置文件

## Phase 2: 协作树核心

- [ ] Task 3: 协作树数据模型与解析器
  - [ ] SubTask 3.1: 在 `argus/core/tree.py` 定义 `Node`、`Edge`、`CollaborationTree` 数据类
  - [ ] SubTask 3.2: 实现 YAML/JSON 解析器 `CollaborationTree.from_file(path)`
  - [ ] SubTask 3.3: 实现节点属性验证：agent 节点必填 `agent_id`，human 节点可选 `delivery`
  - [ ] SubTask 3.4: 实现连线验证：无重复边、`bidirectional` 正确展开为双向边
  - [ ] SubTask 3.5: 编写单元测试验证解析器

- [ ] Task 4: 协作树通信权限
  - [ ] SubTask 4.1: 实现 `CollaborationTree.can_communicate(from_id, to_id)` 方法
  - [ ] SubTask 4.2: 实现 `CollaborationTree.get_reachable_nodes(from_id)` 方法
  - [ ] SubTask 4.3: 实现 `@mention` 解析函数 `parse_mentions(text)`
  - [ ] SubTask 4.4: 编写单元测试覆盖单向/双向/无连线场景

## Phase 3: 消息路由与多 Agent 运行时

- [ ] Task 5: 统一消息模型
  - [ ] SubTask 5.1: 在 `argus/core/message.py` 定义 `ArgusMessage`（from, to, text, reply_to, metadata）
  - [ ] SubTask 5.2: 定义 `MessageTarget` 枚举或类型，区分私聊和群聊
  - [ ] SubTask 5.3: 实现消息序列化/反序列化

- [ ] Task 6: Argus 消息总线
  - [ ] SubTask 6.1: 在 `argus/core/bus.py` 实现 `ArgusBus`，支持按节点 ID 分发消息
  - [ ] SubTask 6.2: 实现 `ArgusBus.send_private(from_id, to_id, text)`
  - [ ] SubTask 6.3: 实现 `ArgusBus.send_group(from_id, text, mentions=None)`
  - [ ] SubTask 6.4: 实现消息订阅/取消订阅接口

- [ ] Task 7: nanobot Agent 适配层
  - [ ] SubTask 7.1: 在 `argus/adapters/nanobot_agent.py` 封装 `NanobotAgentNode`
  - [ ] SubTask 7.2: 为每个 Agent 节点独立创建 `AgentLoop`、`SessionManager`、`ToolRegistry`
  - [ ] SubTask 7.3: 注入 `argus_send_message` 工具到 Agent 工具集
  - [ ] SubTask 7.4: 为每个 Agent 生成包含协作树上下文的系统提示
  - [ ] SubTask 7.5: 实现 Agent 节点生命周期管理：启动、停止、重启

- [ ] Task 8: 消息路由引擎
  - [ ] SubTask 8.1: 在 `argus/core/router.py` 实现 `MessageRouter`
  - [ ] SubTask 8.2: 路由私聊消息到目标 Agent 节点或 human delivery 渠道
  - [ ] SubTask 8.3: 路由群聊消息到所有可达节点
  - [ ] SubTask 8.4: 实现人类节点通过 channel 发送/接收消息
  - [ ] SubTask 8.5: 编写集成测试：两个 Agent 节点通过协作树私聊

## Phase 4: 记忆传承系统

- [ ] Task 9: 记忆存储层
  - [ ] SubTask 9.1: 在 `argus/memory/store.py` 实现 `MemoryStore`，按五层目录管理 Markdown/YAML 文件
  - [ ] SubTask 9.2: 实现 `project_memory.save(project_id, data)` 和 `load(project_id)`
  - [ ] SubTask 9.3: 实现 `team_memory.append_best_practice(entry)` 和 `append_lesson(entry)`
  - [ ] SubTask 9.4: 实现 `agent_profile.update(agent_id, stats)`
  - [ ] SubTask 9.5: 实现 `meeting_archive.save(date, transcript)`
  - [ ] SubTask 9.6: 实现 `mode_library.save(name, tree)` 和 `list_modes()`

- [ ] Task 10: 记忆生成与推荐
  - [ ] SubTask 10.1: 实现任务完成后的项目记忆自动归档
  - [ ] SubTask 10.2: 实现最佳实践/失败教训的自动提取（调用 LLM）
  - [ ] SubTask 10.3: 实现 Agent 表现评分与成长档案更新
  - [ ] SubTask 10.4: 实现基于项目类型推荐历史协作树配置
  - [ ] SubTask 10.5: 编写测试验证记忆写入和推荐逻辑

## Phase 5: 会议功能

- [x] Task 11: 会议引擎
  - [x] SubTask 11.1: 在 `argus/core/meeting.py` 实现 `Meeting` 和 `MeetingEngine`
  - [x] SubTask 11.2: 实现会议开始通知所有参与者
  - [x] SubTask 11.3: 实现轮流发言：依次请求每个 Agent 发表观点
  - [x] SubTask 11.4: 实现发言广播给所有参与者
  - [x] SubTask 11.5: 实现自由讨论阶段，参与者可互相 @
  - [x] SubTask 11.6: 会议结束后自动归档到 `memory/meetings/YYYY-MM-DD.md`
  - [x] SubTask 11.7: 编写测试验证三人会议流程

## Phase 6: CLI 与 Gateway

- [x] Task 12: CLI 命令
  - [x] SubTask 12.1: 在 `argus/cli/main.py` 实现 Typer CLI，包含 `onboard`、`gateway`、`agent`、`status` 命令
  - [x] SubTask 12.2: 实现 `argus gateway` 加载配置并启动所有服务
  - [x] SubTask 12.3: 实现 `argus agent -m "..." --node <human_node_id>`
  - [x] SubTask 12.4: 实现 `argus status` 显示节点状态

- [x] Task 13: Gateway 编排器
  - [x] SubTask 13.1: 在 `argus/core/orchestrator.py` 实现 `ArgusOrchestrator`
  - [x] SubTask 13.2: 编排器加载协作树、启动 Agent 节点、初始化消息总线、启动 channel 监听
  - [x] SubTask 13.3: 集成状态监控，周期性检查节点健康
  - [x] SubTask 13.4: 实现优雅关闭：保存会话、归档记忆、停止所有 Agent

## Phase 7: 可视化 GUI

- [x] Task 14: Tauri + Vue 3 项目初始化
  - [x] SubTask 14.1: 在 `gui/` 初始化 Tauri 2.0 项目（`npm create tauri-app@latest -- --template vue-ts` 或等效）
  - [x] SubTask 14.2: 安装 Vue Flow 或 React Flow 的 Vue 版本用于协作树画布
  - [x] SubTask 14.3: 配置 Tauri 调用 Python 后端的命令接口
  - [x] SubTask 14.4: 验证 `npm run tauri dev` 能启动空白窗口

- [x] Task 15: 协作树编辑器组件
  - [x] SubTask 15.1: 实现 `TreeEditor.vue` 画布组件
  - [x] SubTask 15.2: 实现拖拽创建节点
  - [x] SubTask 15.3: 实现拖拽连线（支持单向/双向）
  - [x] SubTask 15.4: 实现节点选中删除、属性面板编辑
  - [x] SubTask 15.5: 实现保存/加载协作树 YAML

- [x] Task 16: 聊天与会议视图
  - [x] SubTask 16.1: 实现 `ChatView.vue`，显示选中节点的消息历史并支持发送
  - [x] SubTask 16.2: 实现 `MeetingView.vue`，显示会议参与者、发言顺序和历史
  - [x] SubTask 16.3: 实现 WebSocket 或 Tauri 事件与后端消息同步

- [x] Task 17: GUI 后端接口
  - [x] SubTask 17.1: 在 `argus/gui/server.py` 实现 HTTP API：获取/保存协作树、发送消息、获取消息历史、获取节点状态
  - [x] SubTask 17.2: 实现 WebSocket 推送实时消息
  - [x] SubTask 17.3: 将 GUI 后端集成到 `argus gateway`

## Phase 8: 验证与文档

- [x] Task 18: 端到端测试
  - [x] SubTask 18.1: 编写端到端测试：加载三人协作树，人类私聊开发 Agent，开发 Agent 私聊写作 Agent
  - [x] SubTask 18.2: 编写端到端测试：群聊 `@all` 和 `@dev @writer`
  - [x] SubTask 18.3: 编写端到端测试：发起会议并验证轮流发言
  - [x] SubTask 18.4: 验证记忆系统正确归档

- [x] Task 19: 文档
  - [x] SubTask 19.1: 编写 `README.md` 说明 Argus 与 nanobot/OpenClaw 的关系
  - [x] SubTask 19.2: 编写 `docs/QUICKSTART.md` 说明 onboard、配置协作树、启动 gateway
  - [x] SubTask 19.3: 编写 `docs/ARCHITECTURE.md` 说明核心模块

# Task Dependencies

- Task 2 depends on Task 1
- Task 3 depends on Task 1
- Task 4 depends on Task 3
- Task 5 depends on Task 1
- Task 6 depends on Task 5
- Task 7 depends on Task 1
- Task 8 depends on Task 4, Task 6, Task 7
- Task 9 depends on Task 2
- Task 10 depends on Task 9
- Task 11 depends on Task 8
- Task 12 depends on Task 2, Task 8
- Task 13 depends on Task 8, Task 12
- Task 14 depends on Task 1
- Task 15 depends on Task 14, Task 3
- Task 16 depends on Task 14, Task 8
- Task 17 depends on Task 13, Task 14
- Task 18 depends on Task 8, Task 11, Task 10
- Task 19 depends on Task 18

## Verification Fix Tasks (2026-06-29)

以下问题在本次最终系统验证中被发现，需要在后续迭代中修复：

- [x] **Fix 1: 补齐项目根目录 `memory/` 五层记忆目录示例**
  - 失败检查点：Phase 1 - `memory/` 包含五层记忆目录示例
  - 原因：当前 `memory/` 仅包含 `team/`，缺少 `projects/`、`agents/`、`meetings/`、`modes/`
  - 建议：在 `memory/` 下创建空的 `projects/`、`agents/`、`meetings/`、`modes/` 目录，并可选择放入 `.gitkeep` 或示例文件

- [x] **Fix 2: 修复 `argus onboard` 在 Windows 默认控制台的 UnicodeEncodeError**
  - 失败检查点：Phase 2 - `argus onboard` 创建 `~/.argus/config.json`、示例协作树、记忆目录；Phase 7 - `argus onboard` 命令可用
  - 原因：`_success()` 与 `Panel.fit()` 使用了 `✓`、`─`、`│` 等 Unicode 字符，在默认编码为 GBK 的 Windows 终端中触发 `UnicodeEncodeError: 'gbk' codec can't encode character '\u2713'`
  - 建议：移除或替换 CLI 输出中的特殊 Unicode 符号（例如改用 ASCII 的 `[OK]` / `[INFO]`），或为 Rich Console 显式设置可兼容的编码

- [x] **Fix 3: 统一 `argus` 配置字段与 checklist/spec 的命名**
  - 失败检查点：Phase 2 - 配置文件包含 `argus.collaboration_tree`、`argus.memory_dir`、`argus.gui` 字段
  - 原因：当前配置输出为 `argus.collaborationTree`、`argus.memoryDir`、`argus.guiHost`、`argus.guiPort`，与 checklist/spec 要求的 `argus.collaboration_tree`、`argus.memory_dir`、`argus.gui` 不匹配
  - 建议：在 `ArgusExtensionConfig` 中新增/调整字段别名，或修改 checklist/spec 以匹配实现；若保留实现，应更新 checklist 描述

- [x] **Fix 4: 将连线验证与 `@mention` 过滤下沉到 `ArgusBus`**
  - 失败检查点：Phase 4 - `send_private` 只投递给单个目标节点并验证连线；`send_group` 投递给所有可达节点并支持 `@mention` 过滤
  - 原因：当前 `ArgusBus.send_private` / `send_group` 仅负责入队，不感知协作树；验证和过滤逻辑在 `MessageRouter` 中实现
  - 建议：让 `ArgusBus` 持有 `CollaborationTree` 引用，在 `send_private` / `send_group` / `dispatch` 中完成可达性校验和 `@mention` 过滤，或明确调整 checklist 将这两项归于 `MessageRouter`
