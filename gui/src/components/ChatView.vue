<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'
import { fetchJson, connectWebSocket } from '../api'
import type { ArgusMessage, ArgusNode } from '../types'

const props = defineProps<{ nodeId: string | null }>()

const nodes = ref<ArgusNode[]>([])
const messages = ref<ArgusMessage[]>([])
const text = ref('')
const isGroup = ref(false)
const status = ref('')

const targets = computed(() => {
  const ids: string[] = []
  if (props.nodeId) ids.push(props.nodeId)
  const mentions = text.value.match(/@([A-Za-z0-9_-]+)/g)
  if (mentions) {
    for (const m of mentions) {
      const id = m.slice(1)
      if (!ids.includes(id)) ids.push(id)
    }
  }
  return ids
})

onMounted(async () => {
  await loadNodes()
  connectWebSocket((msg) => {
    if (msg.id && msg.from_id) {
      messages.value.push(msg)
    }
  })
})

watch(() => props.nodeId, loadMessages, { immediate: true })

async function loadNodes() {
  const data = await fetchJson('/api/nodes')
  nodes.value = data
}

async function loadMessages() {
  if (!props.nodeId) {
    messages.value = []
    return
  }
  messages.value = await fetchJson(`/api/messages/${props.nodeId}`)
}

async function send() {
  if (!props.nodeId || !text.value.trim()) return
  let to: string[]
  if (isGroup.value) {
    to = []
  } else {
    const mentions = targets.value.filter((id) => id !== props.nodeId)
    if (mentions.length === 0) {
      status.value = '私聊请 @ 指定接收者'
      setTimeout(() => (status.value = ''), 2000)
      return
    }
    to = [mentions[0]]
  }
  await fetchJson('/api/messages', {
    method: 'POST',
    body: JSON.stringify({ from_id: props.nodeId, to, text: text.value }),
  })
  text.value = ''
  status.value = '已发送'
  setTimeout(() => (status.value = ''), 1500)
  await loadMessages()
}

function insertMention(id: string) {
  text.value += `@${id} `
}
</script>

<template>
  <div class="chat-view">
    <div v-if="!nodeId" class="empty">请在 Tree 视图中选择一个节点</div>
    <template v-else>
      <div class="chat-header">
        <h3>节点: {{ nodeId }}</h3>
        <label><input v-model="isGroup" type="checkbox" /> 群聊</label>
        <span v-if="status" class="status">{{ status }}</span>
      </div>
      <div class="mentions">
        <span>提及:</span>
        <button v-for="n in nodes" :key="n.id" @click="insertMention(n.id)">@{{ n.id }}</button>
      </div>
      <div class="messages">
        <div v-if="messages.length === 0" class="empty-msgs">
          暂无消息，发送一条开始对话
        </div>
        <div
          v-for="msg in messages"
          :key="msg.id"
          class="message"
          :class="{ self: msg.from_id === nodeId }"
        >
          <div class="meta">
            <strong>{{ msg.from_id }}</strong>
            <span class="targets">→ {{ msg.to.join(', ') || 'all' }}</span>
            <span class="time">{{ new Date(msg.timestamp).toLocaleTimeString() }}</span>
          </div>
          <div class="text">{{ msg.text }}</div>
        </div>
      </div>
      <div class="composer">
        <textarea v-model="text" rows="2" placeholder="输入消息，使用 @node_id 提及" @keydown.enter.prevent="send" />
        <button @click="send">发送</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 1rem;
  gap: 0.75rem;
}

.empty {
  color: var(--muted);
  margin: auto;
}

.chat-header {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.chat-header h3 {
  margin: 0;
}

.mentions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}

.mentions button {
  padding: 0.25rem 0.5rem;
  font-size: 0.8rem;
  background: var(--panel);
  color: var(--accent);
  border: 1px solid var(--border);
}

.messages {
  flex: 1;
  overflow-y: auto;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.empty-msgs {
  margin: auto;
  color: var(--muted);
  font-size: 0.9rem;
}

.message {
  max-width: 80%;
  padding: 0.5rem;
  border-radius: 0.5rem;
  background: rgba(56, 189, 248, 0.1);
}

.message.self {
  align-self: flex-end;
  background: rgba(16, 185, 129, 0.15);
}

.meta {
  font-size: 0.75rem;
  color: var(--muted);
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
}

.composer {
  display: flex;
  gap: 0.5rem;
}

.composer textarea {
  flex: 1;
}

.status {
  color: var(--agent);
  font-size: 0.85rem;
}
</style>
