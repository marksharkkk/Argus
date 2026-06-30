<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import TreeEditor from './components/TreeEditor.vue'
import ChatView from './components/ChatView.vue'
import MeetingView from './components/MeetingView.vue'
import StatusView from './components/StatusView.vue'
import { fetchJson, connectWebSocket } from './api'
import type { ArgusNode } from './types'

const view = ref<'tree' | 'chat' | 'meeting' | 'status'>('tree')
const selectedNode = ref<string | null>(null)
const wsStatus = ref<'connected' | 'disconnected'>('disconnected')
let ws: WebSocket | null = null

onMounted(async () => {
  let nodes: ArgusNode[] = []
  for (let i = 0; i < 10; i++) {
    try {
      nodes = await fetchJson('/api/nodes')
      break
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 500))
    }
  }
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
</script>

<template>
  <div class="app-layout">
    <aside class="sidebar">
      <h1>Argus</h1>
      <nav>
        <button :class="{ active: view === 'tree' }" @click="view = 'tree'">Tree</button>
        <button :class="{ active: view === 'chat' }" @click="view = 'chat'">Chat</button>
        <button :class="{ active: view === 'meeting' }" @click="view = 'meeting'">Meeting</button>
        <button :class="{ active: view === 'status' }" @click="view = 'status'">Status</button>
      </nav>
      <div class="status-dot" :class="wsStatus">
        {{ wsStatus === 'connected' ? '● 实时已连接' : '● 实时断开' }}
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
  width: 140px;
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

.sidebar nav button {
  text-align: left;
  background: transparent;
  color: var(--text);
  border: 1px solid transparent;
}

.sidebar nav button.active,
.sidebar nav button:hover {
  background: rgba(56, 189, 248, 0.15);
  border-color: var(--accent);
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
