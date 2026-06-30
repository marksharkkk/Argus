<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { fetchJson, connectWebSocket } from '../api'
import type { Meeting, ArgusNode } from '../types'

const nodes = ref<ArgusNode[]>([])
const meetings = ref<Meeting[]>([])
const selectedMeeting = ref<Meeting | null>(null)
const organizer = ref('')
const participants = ref<string[]>([])
const topic = ref('')
const takeoverTopic = ref('')

let refreshInterval: number | undefined

onMounted(async () => {
  await loadNodes()
  await loadMeetingsList()
  refreshInterval = window.setInterval(loadMeetingsList, 5000)
  connectWebSocket((msg) => {
    const meetingId = msg.metadata?.meeting_id
    if (meetingId) {
      loadMeetingsList()
      if (selectedMeeting.value?.id === meetingId) {
        loadMeeting(meetingId)
      }
    }
  })
})

onUnmounted(() => {
  if (refreshInterval) window.clearInterval(refreshInterval)
})

async function loadNodes() {
  nodes.value = await fetchJson('/api/nodes')
}

async function loadMeetingsList() {
  meetings.value = await fetchJson('/api/meetings')
  if (selectedMeeting.value) {
    await loadMeeting(selectedMeeting.value.id)
  }
}

async function loadMeeting(id: string) {
  selectedMeeting.value = await fetchJson(`/api/meetings/${id}`)
}

async function createMeeting() {
  if (!organizer.value || !topic.value || participants.value.length === 0) return
  const meeting: Meeting = await fetchJson('/api/meetings', {
    method: 'POST',
    body: JSON.stringify({ organizer: organizer.value, participants: participants.value, topic: topic.value }),
  })
  meetings.value.push(meeting)
  selectedMeeting.value = meeting
}

async function closeMeeting() {
  if (!selectedMeeting.value) return
  await fetchJson(`/api/meetings/${selectedMeeting.value.id}/close`, { method: 'POST' })
  await loadMeeting(selectedMeeting.value.id)
}

async function skipTurn() {
  if (!selectedMeeting.value) return
  await fetchJson(`/api/meetings/${selectedMeeting.value.id}/command`, {
    method: 'POST',
    body: JSON.stringify({ command: 'skip_turn' }),
  })
  await loadMeeting(selectedMeeting.value.id)
}

async function updateTopic() {
  if (!selectedMeeting.value || !takeoverTopic.value.trim()) return
  await fetchJson(`/api/meetings/${selectedMeeting.value.id}/command`, {
    method: 'POST',
    body: JSON.stringify({ command: 'update_topic', payload: takeoverTopic.value.trim() }),
  })
  takeoverTopic.value = ''
  await loadMeeting(selectedMeeting.value.id)
}

</script>

<template>
  <div class="meeting-view">
    <aside class="meeting-list">
      <h3>会议</h3>
      <div v-if="meetings.length === 0" class="empty-list">暂无会议</div>
      <button v-for="m in meetings" :key="m.id" :class="{ active: selectedMeeting?.id === m.id }" @click="loadMeeting(m.id)">
        <span class="status-dot" :class="m.status" />
        {{ m.topic }}
      </button>
    </aside>

    <div class="meeting-form">
      <h3>发起会议</h3>
      <label>组织者</label>
      <select v-model="organizer">
        <option v-for="n in nodes" :key="n.id" :value="n.id">{{ n.label }} ({{ n.id }})</option>
      </select>
      <label>参与者</label>
      <div class="participant-checks">
        <label v-for="n in nodes" :key="n.id">
          <input v-model="participants" type="checkbox" :value="n.id" />
          {{ n.label }}
        </label>
      </div>
      <label>主题</label>
      <input v-model="topic" />
      <button @click="createMeeting">发起会议</button>

      <div v-if="selectedMeeting" class="meeting-detail">
        <h4>{{ selectedMeeting.topic }}</h4>
        <p class="meta-line">
          组织者: {{ selectedMeeting.organizer }}
          | 参与者: {{ selectedMeeting.participants.join(', ') }}
          | 状态: <span class="status-badge" :class="selectedMeeting.status">{{ selectedMeeting.status }}</span>
        </p>
        <div class="history">
          <div v-for="(entry, idx) in selectedMeeting.messages" :key="idx" class="entry">
            <strong>{{ entry.speaker }}</strong>
            <span class="time">{{ new Date(entry.timestamp).toLocaleTimeString() }}</span>
            <p>{{ entry.text }}</p>
          </div>
        </div>
        <div v-if="selectedMeeting.status === 'running'" class="takeover">
          <h4>Human 接管</h4>
          <div class="takeover-row">
            <button class="secondary" @click="skipTurn">跳过当前发言</button>
          </div>
          <div class="takeover-row">
            <input v-model="takeoverTopic" placeholder="新主题" />
            <button class="secondary" @click="updateTopic">更新主题</button>
          </div>
          <button class="danger" @click="closeMeeting">结束会议</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.meeting-view {
  display: flex;
  height: 100%;
  padding: 1rem;
  gap: 1rem;
}

.meeting-list {
  width: 200px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  overflow-y: auto;
}

.meeting-list button {
  text-align: left;
  background: transparent;
  color: var(--text);
  border: 1px solid transparent;
}

.meeting-list button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.meeting-list button.active,
.meeting-list button:hover {
  background: rgba(56, 189, 248, 0.15);
  border-color: var(--accent);
}

.empty-list {
  color: var(--muted);
  font-size: 0.85rem;
  margin-top: 0.5rem;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  background: var(--muted);
}

.status-dot.running {
  background: var(--agent);
}

.status-dot.closed {
  background: #ef4444;
}

.meta-line {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  flex-wrap: wrap;
}

.status-badge {
  padding: 0.15rem 0.4rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  background: var(--muted);
  color: #0f172a;
}

.status-badge.running {
  background: var(--agent);
}

.status-badge.closed {
  background: #ef4444;
  color: #fff;
}

.meeting-form {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  overflow-y: auto;
}

.meeting-form label {
  font-size: 0.85rem;
  color: var(--muted);
}

.participant-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.meeting-detail {
  margin-top: 1rem;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 0.75rem;
}

.history {
  max-height: 320px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 0.75rem 0;
}

.entry {
  background: rgba(56, 189, 248, 0.1);
  padding: 0.5rem;
  border-radius: 0.375rem;
}

.time {
  font-size: 0.75rem;
  color: var(--muted);
  margin-left: 0.5rem;
}

.danger {
  background: #ef4444;
  color: white;
}

.takeover {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.takeover h4 {
  margin: 0;
  color: var(--human);
}

.takeover-row {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.takeover-row input {
  flex: 1;
}

.takeover-row button {
  flex-shrink: 0;
  white-space: nowrap;
}

.secondary {
  background: var(--accent);
  color: #0f172a;
}
</style>
