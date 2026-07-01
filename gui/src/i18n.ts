import { ref, computed } from 'vue'

export type Language = 'zh' | 'en'

const messages: Record<Language, Record<string, string>> = {
  zh: {
    appTitle: 'Argus',
    tree: '协作树',
    chat: '聊天',
    meeting: '会议',
    status: '状态',
    connected: '● 实时已连接',
    disconnected: '● 实时断开',
    send: '发送',
    noMessages: '暂无消息，发送一条开始对话',
    target: '目标',
    message: '消息',
    startMeeting: '开始会议',
    closeMeeting: '结束会议',
    topic: '主题',
    participants: '参与者',
    meetings: '会议列表',
    noMeetings: '暂无会议',
    refresh: '刷新',
    online: '在线',
    offline: '离线',
    node: '节点',
    type: '类型',
    model: '模型',
    reachable: '可达节点',
    language: '语言',
    loading: '加载中...',
    properties: '属性',
    save: '保存',
    saved: '已保存',
    deleteSelected: '删除选中',
    humanNode: '人类节点',
    agentNode: 'Agent 节点',
    selectHint: '选择一个节点或连线以编辑属性',
  },
  en: {
    appTitle: 'Argus',
    tree: 'Tree',
    chat: 'Chat',
    meeting: 'Meeting',
    status: 'Status',
    connected: '● Live connected',
    disconnected: '● Live disconnected',
    send: 'Send',
    noMessages: 'No messages yet, send one to start',
    target: 'Target',
    message: 'Message',
    startMeeting: 'Start Meeting',
    closeMeeting: 'Close Meeting',
    topic: 'Topic',
    participants: 'Participants',
    meetings: 'Meetings',
    noMeetings: 'No meetings yet',
    refresh: 'Refresh',
    online: 'Online',
    offline: 'Offline',
    node: 'Node',
    type: 'Type',
    model: 'Model',
    reachable: 'Reachable',
    language: 'Language',
    loading: 'Loading...',
    properties: 'Properties',
    save: 'Save',
    saved: 'Saved',
    deleteSelected: 'Delete',
    humanNode: 'Human Node',
    agentNode: 'Agent Node',
    selectHint: 'Select a node or edge to edit properties',
  },
}

const currentLang = ref<Language>('zh')

export function setLanguage(lang: Language) {
  if (messages[lang]) {
    currentLang.value = lang
    localStorage.setItem('argus-language', lang)
  }
}

export function initLanguage(configLang?: string) {
  const saved = localStorage.getItem('argus-language') as Language | null
  if (saved && messages[saved]) {
    currentLang.value = saved
    return
  }
  if (configLang && (configLang === 'zh' || configLang === 'en')) {
    currentLang.value = configLang
    return
  }
  const browserLang = navigator.language.toLowerCase()
  currentLang.value = browserLang.startsWith('zh') ? 'zh' : 'en'
}

export function t(key: string): string {
  return messages[currentLang.value][key] || key
}

export const language = computed(() => currentLang.value)
