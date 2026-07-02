"""真实/无 LLM 验证：human 接管会议 + inbox 持久化。

两种运行模式：
- 真实 LLM（默认）：使用 .real-test-argus/config.json 里的 DeepSeek 配置
    ARGUS_CONFIG_PATH=.real-test-argus/config.json python scripts/validate_human_features.py
- 无 LLM：不调用任何大模型 API，使用 mock agent + mock response_provider
    NO_LLM=1 python scripts/validate_human_features.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from argus.config.loader import get_argus_config_path, load_argus_config
from argus.config.schema import ArgusConfig
from argus.core.meeting import MeetingEngine
from argus.core.message import ArgusMessage
from argus.core.orchestrator import ArgusOrchestrator
from argus.core.tree import CollaborationTree
from argus.memory.store import MemoryStore


BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / ".real-test-argus" / "config.json"
RESULT_PATH = BASE_DIR / ".real-test-argus" / "human_features_result.json"
EXAMPLE_CONFIG_PATH = BASE_DIR / "config" / "example_config.json"
EXAMPLE_TREE_PATH = BASE_DIR / "config" / "example_tree.yaml"
TEST_TREE_PATH = BASE_DIR / ".real-test-argus" / "collaboration_tree.yaml"


class ValidationError(Exception):
    """Raised when a validation assertion fails."""


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _no_llm_mode() -> bool:
    """Return True if the script should run without calling any LLM API."""
    return os.environ.get("NO_LLM", "").lower() in ("1", "true", "yes")


def _ensure_test_workspace() -> None:
    """Create a self-contained test workspace if it does not exist.

    This allows the validation script to run in CI without requiring
    ``argus onboard`` or a pre-populated ``~/.argus`` directory.
    """
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists() and EXAMPLE_CONFIG_PATH.exists():
        import shutil

        shutil.copy2(EXAMPLE_CONFIG_PATH, CONFIG_PATH)
        config_text = CONFIG_PATH.read_text(encoding="utf-8")
        config_data = json.loads(config_text)
        # Override paths to point inside the repo so CI can find them.
        config_data.setdefault("argus", {})
        config_data["argus"]["collaboration_tree"] = str(TEST_TREE_PATH)
        config_data["argus"]["memory_dir"] = str(BASE_DIR / ".real-test-argus" / "memory")
        config_data["argus"]["status_dir"] = str(BASE_DIR / ".real-test-argus" / "status")
        config_data["argus"]["log_dir"] = str(BASE_DIR / ".real-test-argus" / "logs")
        # Ensure providers use environment variables when available.
        if "providers" in config_data:
            for provider in config_data["providers"].values():
                if isinstance(provider, dict):
                    provider.setdefault("api_key", os.environ.get("LLM_API_KEY", "sk-placeholder"))
        CONFIG_PATH.write_text(
            json.dumps(config_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if not TEST_TREE_PATH.exists() and EXAMPLE_TREE_PATH.exists():
        import shutil

        shutil.copy2(EXAMPLE_TREE_PATH, TEST_TREE_PATH)


async def _wait_for(
    predicate: Any,
    timeout: float = 10.0,
    interval: float = 0.05,
) -> None:
    """Wait until predicate() is truthy."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)
    raise TimeoutError("wait_for predicate did not become true")


async def test_inbox_persistence(
    orchestrator: ArgusOrchestrator,
) -> dict[str, Any]:
    """验证 human 离线时消息进入 inbox，上线后自动投递。"""
    logger.info("=== 测试 inbox 持久化 ===")

    received: list[ArgusMessage] = []

    async def human_handler(message: ArgusMessage) -> None:
        received.append(message)

    # 先上线再下线，确保 human_manager 已注册该节点
    orchestrator.register_human_handler("human", human_handler)
    await asyncio.sleep(0.2)
    orchestrator.unregister_human_handler("human")
    await asyncio.sleep(0.2)

    inbox_dir = orchestrator.human_manager._storage_dir
    _assert(inbox_dir is not None, "inbox 存储目录未配置")
    inbox_file = inbox_dir / "human.inbox.json"

    # 离线时从 dev 给 human 发一条私聊
    test_text = "human 离线测试消息"
    orchestrator.bus.send_private("dev", "human", test_text)
    await asyncio.sleep(0.3)

    # 验证 inbox 文件已持久化
    _assert(inbox_file.exists(), f"inbox 文件未生成: {inbox_file}")
    data = json.loads(inbox_file.read_text(encoding="utf-8"))
    texts = [m["text"] for m in data.get("messages", [])]
    _assert(test_text in texts, f"inbox 中未找到测试消息: {texts}")

    # 重新上线，应自动 drain inbox
    received.clear()
    orchestrator.register_human_handler("human", human_handler)
    await asyncio.sleep(0.3)

    _assert(
        any(m.text == test_text for m in received),
        f"上线后未收到 inbox 中的离线消息: {[m.text for m in received]}",
    )
    if inbox_file.exists():
        data_after = json.loads(inbox_file.read_text(encoding="utf-8"))
        _assert(
            data_after.get("messages", []) == [],
            f"inbox drain 后文件仍包含消息: {data_after}",
        )

    logger.info("inbox 持久化验证通过")
    return {
        "passed": True,
        "offline_message": test_text,
        "delivered_after_login": True,
    }


def _make_mock_response_provider(
    slow_for: str | set[str] | None = None,
    slow_delay: float = 0.0,
) -> Any:
    """Return a deterministic response provider for the meeting engine.

    When ``slow_for`` is set, those participants will sleep before replying,
    which lets us test ``skip_turn`` while a turn is in progress.
    """
    slow_set = {slow_for} if isinstance(slow_for, str) else set(slow_for or ())

    async def response_provider(
        participant_id: str,
        prompt: str,
        history: list[ArgusMessage],
    ) -> str:
        if participant_id in slow_set:
            await asyncio.sleep(slow_delay)
        return f"[{participant_id}] 这是确定性回复，用于无 LLM 验证。"

    return response_provider


async def test_meeting_takeover(
    orchestrator: ArgusOrchestrator,
    no_llm: bool = False,
) -> dict[str, Any]:
    """验证 human 可在会议中跳过当前发言、更新议题、结束会议。"""
    logger.info("=== 测试 human 接管会议 ===")

    human_messages: list[ArgusMessage] = []

    async def human_handler(message: ArgusMessage) -> None:
        human_messages.append(message)

    # 确保 human 在线
    orchestrator.register_human_handler("human", human_handler)
    await asyncio.sleep(0.2)

    engine_kwargs: dict[str, Any] = {
        "bus": orchestrator.bus,
        "router": orchestrator.router,
        "memory_store": orchestrator.memory_store,
    }
    if no_llm:
        # 让 dev 和 writer 的回合都故意慢，确保 skip_turn 发生在思考过程中
        engine_kwargs["response_provider"] = _make_mock_response_provider(
            slow_for={"dev", "writer"},
            slow_delay=5.0,
        )
        engine_kwargs["response_timeout"] = 10.0
    else:
        engine_kwargs["response_timeout"] = 60.0

    meeting_engine = MeetingEngine(**engine_kwargs)

    meeting = await meeting_engine.start_meeting(
        organizer="human",
        participants=["human", "dev", "writer"],
        topic="human 接管会议测试",
    )
    logger.info("会议已启动: {}", meeting.id)

    # 等待会议开始消息被 human 收到
    try:
        await _wait_for(
            lambda: any("会议开始" in m.text for m in human_messages),
            timeout=10.0,
        )
    except TimeoutError:
        status = orchestrator.human_manager.status()
        logger.error("human 未收到会议开始消息。当前状态: {}", status)
        logger.error("human_messages: {}", [m.text for m in human_messages])
        raise

    # dev 正在慢速生成回复，立即跳过它
    await meeting_engine.command_meeting(meeting.id, "skip_turn")

    if no_llm:
        # 等收到 dev 被跳过的广播后，writer 的慢速回合已经开始，再跳过 writer
        await _wait_for(
            lambda: any("主持人跳过 dev 的发言" in m.text for m in human_messages),
            timeout=5.0,
        )
        await meeting_engine.command_meeting(meeting.id, "skip_turn")
        await asyncio.sleep(0.3)
    else:
        # 真实 LLM 模式下，等 dev 开始思考后再跳过；然后等 writer 开始后再跳过
        await asyncio.sleep(2.0)
        await meeting_engine.command_meeting(meeting.id, "skip_turn")
        await asyncio.sleep(2.0)
        await meeting_engine.command_meeting(meeting.id, "skip_turn")
        await asyncio.sleep(1.0)

    router_texts = [m.text for m in human_messages]
    _assert(
        any("主持人跳过 dev 的发言" in t for t in router_texts),
        f"未收到 dev 被跳过的提示: {router_texts[-10:]}",
    )
    _assert(
        any("主持人跳过 writer 的发言" in t for t in router_texts),
        f"未收到 writer 被跳过的提示: {router_texts[-10:]}",
    )

    # 更新议题
    await meeting_engine.command_meeting(meeting.id, "update_topic", "已接管的议题")
    await asyncio.sleep(0.3)
    _assert(
        meeting.topic == "已接管的议题",
        f"议题未更新: {meeting.topic}",
    )
    _assert(
        any("会议议题更新为：已接管的议题" in m.text for m in human_messages),
        "未收到议题更新广播",
    )

    # 结束会议
    closed = await meeting_engine.close_meeting(meeting.id)
    await meeting_engine.wait_for_meeting(meeting.id)
    _assert(closed.status == "closed", f"会议未正确关闭: {closed.status}")

    logger.info("human 接管会议验证通过")
    return {
        "passed": True,
        "meeting_id": meeting.id,
        "final_topic": meeting.topic,
        "status": closed.status,
        "human_received_messages": [m.text for m in human_messages],
    }


async def main() -> int:
    """Run all human-feature validations."""
    os.environ.setdefault("ARGUS_CONFIG_PATH", str(CONFIG_PATH))
    _ensure_test_workspace()
    no_llm = _no_llm_mode()
    if no_llm:
        logger.info("运行模式: 无 LLM（mock agent + mock response_provider）")
    else:
        logger.info("运行模式: 真实 LLM")

    config_path = get_argus_config_path()
    logger.info("加载配置: {}", config_path)
    config = load_argus_config(config_path)

    tree_path = Path(config.argus.collaboration_tree).expanduser().resolve()
    logger.info("加载协作树: {}", tree_path)
    tree = CollaborationTree.from_file(tree_path)

    memory_store = MemoryStore(Path(config.argus.memory_dir).expanduser())
    orchestrator = ArgusOrchestrator(
        config=config,
        tree=tree,
        memory_store=memory_store,
        mock=no_llm,
    )

    result: dict[str, Any] = {
        "config_path": str(config_path),
        "tree_path": str(tree_path),
        "no_llm": no_llm,
        "tests": {},
        "errors": [],
    }

    exit_code = 0
    try:
        await orchestrator.start()
        logger.info("Orchestrator 已启动")
        await asyncio.sleep(0.5)

        result["tests"]["inbox_persistence"] = await test_inbox_persistence(orchestrator)
        result["tests"]["meeting_takeover"] = await test_meeting_takeover(
            orchestrator,
            no_llm=no_llm,
        )

    except ValidationError as exc:
        logger.error("验证失败: {}", exc)
        result["errors"].append(str(exc))
        exit_code = 1
    except Exception as exc:
        logger.exception("验证过程出现未预期错误")
        result["errors"].append(f"{type(exc).__name__}: {exc}")
        exit_code = 1
    finally:
        logger.info("关闭 orchestrator...")
        await orchestrator.stop()

        RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULT_PATH.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("结果已保存: {}", RESULT_PATH)

    if exit_code == 0:
        logger.info("全部验证通过")
    return exit_code


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, level="INFO")
    sys.exit(asyncio.run(main()))
