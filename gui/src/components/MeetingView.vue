<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchJson, connectWebSocket } from '../api'
import type { Meeting, ArgusNode } from '../types'

const nodes = ref<ArgusNode[]>([])
const meetings = ref<Meeting[]>([])
const selectedMeeting = ref<Meeting | null>(null)
const organizer = ref('')
const participants = ref<string[]>([])
const topic = ref('')

onMounted(async () => {
  await loadNodes()
  await loadMeetings()
  connectWebSocket((msg) => {
    const meetingId = msg.metadata?.meeting_id
    if (meetingId && selectedMeeting.value?.id === meetingId) {
      loadMeeting(meetingId)
    }
  })
})

async function loadNodes() {
  nodes.value = await fetchJson('/api/nodes')
}

async function loadMeetings() {
  // The backend does not have a list endpoint, so we rely on the selected/in-memory ones.
  // Refresh current selected meeting if any.
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

function toggleParticipant(id: string) {
  if (participants.value.includes(id)) {
    participants.value = participants.value.filter((p) => p !== id)
  } else {
    participants.value.push(id)
  }
}
</script>

<template>
  <div class="meeting-view">
    <aside class="meeting-list">
      <h3>会议</h3>
      <button v-for="m in meetings" :key="m.id" :class="{ active: selectedMeeting?.id === m.id }" @click="loadMeeting(m.id)">
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
          <input type="checkbox" :checked="participants.includes(n.id)" @change="toggleParticipant(n.id)" />
          {{ n.label }}
        </label>
      </div>
      <label>主题</label>
      <input v-model="topic" />
      <button @click="createMeeting">发起会议</button>

      <div v-if="selectedMeeting" class="meeting-detail">
        <h4>{{ selectedMeeting.topic }}</h4>
        <p>组织者: {{ selectedMeeting.organizer }} | 参与者: {{ selectedMeeting.participants.join(', ') }} | 状态: {{ selectedMeeting.status }}</p>
        <div class="history">
          <div v-for="(entry, idx) in selectedMeeting.messages" :key="idx" class="entry">
            <strong>{{ entry.speaker }}</strong>
            <span class="time">{{ new Date(entry.timestamp).toLocaleTimeString() }}</span>
            <p>{{ entry.text }}</p>
          </div>
        </div>
        <button v-if="selectedMeeting.status === 'running'" class="danger" @click="closeMeeting">结束会议</button>
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

.meeting-list button.active,
.meeting-list button:hover {
  background: rgba(56, 189, 248, 0.15);
  border-color: var(--accent);
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
</style>
