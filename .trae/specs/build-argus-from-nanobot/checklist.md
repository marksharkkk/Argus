# Checklist

## Phase 1: 基础设施与项目结构

- [x] `nanobot/` 子包可从 `argus/` 正确导入
- [x] `argus/` 顶层包包含 `core/`、`adapters/`、`memory/`、`cli/`、`gui/`、`config/` 子模块
- [x] `gui/` 目录存在且包含 Tauri 2.0 + Vue 3 项目骨架
- [x] `config/` 包含示例协作树 YAML
- [x] `memory/` 包含五层记忆目录示例
- [x] 根目录 `pyproject.toml` 支持 `pip install -e .` 同时安装 `argus` 和 `nanobot`
- [x] 安装后 `import argus` 和 `import nanobot` 成功

## Phase 2: Argus 配置系统

- [x] `ArgusConfig` 扩展 nanobot `Config` 并新增 `argus` 字段
- [x] `argus onboard` 创建 `~/.argus/config.json`、示例协作树、记忆目录
- [x] 配置文件包含 `argus.collaboration_tree`、`argus.memory_dir`、`argus.gui` 字段

## Phase 3: 协作树核心

- [x] `Node`、`Edge`、`CollaborationTree` 数据类正确定义
- [x] YAML/JSON 协作树解析器工作正常
- [x] agent 节点缺少 `agent_id` 时解析失败并报错
- [x] `bidirectional=true` 正确展开为双向边
- [x] `can_communicate(from, to)` 正确判断单向/双向/无连线场景
- [x] `get_reachable_nodes(from)` 返回所有可达节点
- [x] `parse_mentions(text)` 正确提取 `@node_id`

## Phase 4: 消息路由与多 Agent 运行时

- [x] `ArgusMessage` 包含 from、to、text、reply_to、metadata
- [x] `ArgusBus` 支持按节点 ID 订阅和分发
- [x] `send_private` 只投递给单个目标节点并验证连线
- [x] `send_group` 投递给所有可达节点并支持 `@mention` 过滤
- [x] `NanobotAgentNode` 封装 nanobot `AgentLoop`
- [x] 每个 Agent 节点拥有独立 session 和系统提示
- [x] `argus_send_message` 工具注入到 Agent 工具集
- [x] `MessageRouter` 正确路由 human→agent、agent→agent、agent→human 消息
- [x] 两个 Agent 节点可通过协作树私聊

## Phase 5: 记忆传承系统

- [x] `MemoryStore` 按五层目录管理文件
- [x] 项目记忆可保存/加载
- [x] 团队最佳实践和失败教训可追加
- [x] Agent 成长档案可更新
- [x] 会议纪要可归档
- [x] 协作模式库可保存/列出
- [x] 同类型项目可推荐历史协作树配置

## Phase 6: 会议功能

- [x] `MeetingEngine` 可发起会议
- [x] 会议通知所有参与者
- [x] 轮流发言依次请求每个 Agent
- [x] 每个发言广播给所有参与者
- [x] 自由讨论阶段支持互相 @
- [x] 会议结束后归档到 `memory/meetings/YYYY-MM-DD.md`
- [x] 三人会议流程端到端测试通过

## Phase 7: CLI 与 Gateway

- [x] `argus onboard` 命令可用
- [x] `argus gateway` 可加载配置并启动
- [x] `argus agent -m "..." --node <human_node_id>` 可用
- [x] `argus status` 显示节点状态
- [x] `ArgusOrchestrator` 加载协作树、启动 Agent 节点、初始化消息总线
- [x] 编排器支持优雅关闭并保存会话/归档记忆

## Phase 8: 可视化 GUI

- [x] Tauri 2.0 + Vue 3 项目骨架已初始化（`npm run build` 通过）
- [x] 协作树画布可拖拽创建节点
- [x] 可拖拽创建单向/双向连线
- [x] 节点属性面板可编辑并保存
- [x] 聊天视图显示消息历史并支持发送
- [x] 会议视图显示参与者、发言顺序、历史记录
- [x] GUI 后端 HTTP API 提供协作树、消息、状态接口
- [x] WebSocket 实时推送消息到前端

## Phase 9: 验证与文档

- [x] 三人协作树私聊端到端测试通过
- [x] 群聊 `@all` 和 `@dev @writer` 端到端测试通过
- [x] 会议轮流发言端到端测试通过
- [x] 记忆归档端到端测试通过
- [x] `README.md` 说明 Argus 与 nanobot/OpenClaw 关系
- [x] `docs/QUICKSTART.md` 说明 onboard、配置、启动 gateway
- [x] `docs/ARCHITECTURE.md` 说明核心模块
