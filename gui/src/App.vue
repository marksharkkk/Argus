<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import TreeEditor from './components/TreeEditor.vue'
import ChatView from './components/ChatView.vue'
import MeetingView from './components/MeetingView.vue'
import StatusView from './components/StatusView.vue'
import { fetchJson, connectWebSocket } from './api'
import { t, initLanguage, setLanguage, language } from './i18n'
import type { ArgusNode } from './types'

const view = ref<'tree' | 'chat' | 'meeting' | 'status'>('tree')
const selectedNode = ref<string | null>(null)
const wsStatus = ref<'connected' | 'disconnected'>('disconnected')
let ws: WebSocket | null = null

onMounted(async () => {
  let nodes: ArgusNode[] = []
  let configLang = 'zh'
  for (let i = 0; i < 10; i++) {
    try {
      const config = await fetchJson('/api/config')
      configLang = config.language || configLang
      nodes = await fetchJson('/api/nodes')
      break
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 500))
    }
  }
  initLanguage(configLang)
  const human = nodes.find((n) => n.type === 'human')
  selectedNode.value = human ? human.id : (nodes[0]?.id ?? null)

  ws = connectWebSocket((msg) => {
    if (msg.type === 'pong') return
    wsStatus.value = 'connected'
  })
  ws.onopen = () => {
    wsStatus.value = 'connected'
  }
  ws.onclose = () => {
    wsStatus.value = 'disconnected'
  }
})

onUnmounted(() => {
  ws?.close()
})

function switchLang(lang: 'zh' | 'en') {
  setLanguage(lang)
}
</script>

<template>
  <div class="app-layout">
    <aside class="sidebar">
      <h1>{{ t('appTitle') }}</h1>
      <nav>
        <button :class="{ active: view === 'tree' }" @click="view = 'tree'">{{ t('tree') }}</button>
        <button :class="{ active: view === 'chat' }" @click="view = 'chat'">{{ t('chat') }}</button>
        <button :class="{ active: view === 'meeting' }" @click="view = 'meeting'">{{ t('meeting') }}</button>
        <button :class="{ active: view === 'status' }" @click="view = 'status'">{{ t('status') }}</button>
      </nav>
      <div class="lang-switch">
        <span>{{ t('language') }}:</span>
        <button :class="{ active: language === 'zh' }" @click="switchLang('zh')">中</button>
        <button :class="{ active: language === 'en' }" @click="switchLang('en')">En</button>
      </div>
      <div class="status-dot" :class="wsStatus">
        {{ wsStatus === 'connected' ? t('connected') : t('disconnected') }}
      </div>
    </aside>
    <main class="main">
      <TreeEditor v-if="view === 'tree'" v-model:selected="selectedNode" />
      <ChatView v-else-if="view === 'chat'" :node-id="selectedNode" />
      <MeetingView v-else-if="view === 'meeting'" />
      <StatusView v-else />
    </main>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  width: 100%;
  height: 100%;
}

.sidebar {
  width: 160px;
  background: var(--panel);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 1rem;
  gap: 1rem;
}

.sidebar h1 {
  margin: 0;
  font-size: 1.25rem;
  color: var(--accent);
}

.sidebar nav {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.sidebar nav button,
.lang-switch button {
  text-align: left;
  background: transparent;
  color: var(--text);
  border: 1px solid transparent;
}

.sidebar nav button.active,
.sidebar nav button:hover,
.lang-switch button.active,
.lang-switch button:hover {
  background: rgba(56, 189, 248, 0.15);
  border-color: var(--accent);
}

.lang-switch {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.8rem;
  color: var(--muted);
}

.lang-switch button {
  padding: 0.15rem 0.4rem;
  text-align: center;
  min-width: 1.8rem;
}

.status-dot {
  margin-top: auto;
  font-size: 0.75rem;
  color: var(--muted);
}

.status-dot.connected {
  color: var(--agent);
}

.main {
  flex: 1;
  overflow: hidden;
}
</style>
