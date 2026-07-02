"""Lightweight internationalization helpers for Argus.

Supported languages: zh (Chinese), en (English).
The active language is read from ``ArgusConfig.argus.language`` or the
``ARGUS_LANGUAGE`` environment variable, falling back to the system locale
and finally to ``zh``.
"""

from __future__ import annotations

import locale
import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class I18nStrings:
    """Collection of user-facing strings for one language."""

    language: str
    # CLI: general
    ok: str
    error: str
    warning: str
    cancelled: str
    done: str
    # CLI: commands
    onboard_done: str
    workspace_initialized: str
    gateway_started: str
    gateway_stopped: str
    status_header: str
    status_node: str
    agent_sent: str
    agent_prompt_required: str
    agent_joined: str
    agent_exited: str
    # Core / messages
    unreachable_target: str
    no_meeting_found: str
    meeting_closed: str
    meeting_topic_updated: str
    turn_skipped: str
    command_queued: str
    # GUI labels
    tree_editor: str
    chat_view: str
    meeting_view: str
    status_view: str
    send: str
    start_meeting: str
    close_meeting: str
    topic: str
    participants: str
    online: str
    offline: str
    # Human node
    inbox_drained: str
    message_persisted: str


STRINGS: dict[str, I18nStrings] = {
    "zh": I18nStrings(
        language="zh",
        ok="完成",
        error="错误",
        warning="警告",
        cancelled="已取消",
        done="完成",
        onboard_done="工作空间初始化完成",
        workspace_initialized="已创建工作空间、默认配置、协作树与记忆目录",
        gateway_started="Gateway 已启动",
        gateway_stopped="Gateway 已停止",
        status_header="Argus 状态",
        status_node="{node_id}: {status}",
        agent_sent="消息已发送",
        agent_prompt_required="请提供 -m/--message 消息内容",
        agent_joined="已以 human 节点加入", agent_exited="Agent 模式已退出",
        unreachable_target="目标节点不可达",
        no_meeting_found="未找到会议",
        meeting_closed="会议已结束",
        meeting_topic_updated="会议主题已更新",
        turn_skipped="已跳过当前发言",
        command_queued="命令已加入队列",
        tree_editor="协作树",
        chat_view="聊天",
        meeting_view="会议",
        status_view="状态",
        send="发送",
        start_meeting="开始会议",
        close_meeting="结束会议",
        topic="主题",
        participants="参与者",
        online="在线",
        offline="离线",
        inbox_drained="inbox 已补发 {count} 条消息",
        message_persisted="离线消息已暂存 inbox",
    ),
    "en": I18nStrings(
        language="en",
        ok="OK",
        error="Error",
        warning="Warning",
        cancelled="Cancelled",
        done="Done",
        onboard_done="Workspace initialized",
        workspace_initialized="Created workspace, default config, collaboration tree and memory directories",
        gateway_started="Gateway started",
        gateway_stopped="Gateway stopped",
        status_header="Argus Status",
        status_node="{node_id}: {status}",
        agent_sent="Message sent",
        agent_prompt_required="Please provide -m/--message",
        agent_joined="Joined as human node", agent_exited="Agent mode exited",
        unreachable_target="Target node is unreachable",
        no_meeting_found="Meeting not found",
        meeting_closed="Meeting closed",
        meeting_topic_updated="Meeting topic updated",
        turn_skipped="Current turn skipped",
        command_queued="Command queued",
        tree_editor="Collaboration Tree",
        chat_view="Chat",
        meeting_view="Meeting",
        status_view="Status",
        send="Send",
        start_meeting="Start Meeting",
        close_meeting="Close Meeting",
        topic="Topic",
        participants="Participants",
        online="Online",
        offline="Offline",
        inbox_drained="Inbox drained: {count} messages",
        message_persisted="Offline message persisted to inbox",
    ),
}

DEFAULT_LANGUAGE = "zh"


def get_system_language() -> str:
    """Return 'zh' if the system locale is Chinese-ish, otherwise 'en'."""
    try:
        loc = locale.getlocale()[0]
    except (AttributeError, ValueError):
        loc = None
    if loc and loc.lower().startswith("zh"):
        return "zh"
    return "en"


def get_active_language(config: Any | None = None) -> str:
    """Resolve the active language from env, config, locale, or default."""
    env_lang = os.environ.get("ARGUS_LANGUAGE")
    if env_lang in STRINGS:
        return env_lang

    if config is not None:
        try:
            cfg_lang = getattr(config.argus, "language", None)
        except AttributeError:
            cfg_lang = None
        if cfg_lang in STRINGS:
            return cfg_lang

    system_lang = get_system_language()
    return system_lang if system_lang in STRINGS else DEFAULT_LANGUAGE


def get_strings(config: Any | None = None) -> I18nStrings:
    """Return the translation strings for the active language."""
    return STRINGS[get_active_language(config)]


def t(key: str, config: Any | None = None, **kwargs: Any) -> str:
    """Translate a string by key, optionally formatting kwargs."""
    strings = get_strings(config)
    text = getattr(strings, key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    return text
