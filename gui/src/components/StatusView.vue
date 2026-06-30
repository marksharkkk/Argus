<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchJson } from '../api'
import type { ArgusNode } from '../types'

const nodes = ref<ArgusNode[]>([])
const statuses = ref<Record<string, any>>({})

onMounted(async () => {
  await load()
  setInterval(load, 3000)
})

async function load() {
  nodes.value = await fetchJson('/api/nodes')
  for (const node of nodes.value) {
    try {
      statuses.value[node.id] = await fetchJson(`/api/nodes/${node.id}/status`)
    } catch (e) {
      statuses.value[node.id] = { error: 'failed to load' }
    }
  }
}
</script>

<template>
  <div class="status-view">
    <h2>节点状态</h2>
    <div class="table-wrap">
      <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Label</th>
          <th>Type</th>
          <th>Running</th>
          <th>Inbound</th>
          <th>Outbound</th>
          <th>Sessions</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="node in nodes" :key="node.id">
          <td>{{ node.id }}</td>
          <td>{{ node.label }}</td>
          <td :class="node.type">{{ node.type }}</td>
          <td>{{ statuses[node.id]?.running ?? '-' }}</td>
          <td>{{ statuses[node.id]?.inbound_queue_size ?? '-' }}</td>
          <td>{{ statuses[node.id]?.outbound_queue_size ?? '-' }}</td>
          <td>{{ statuses[node.id]?.session_count ?? '-' }}</td>
        </tr>
      </tbody>
    </table>
    </div>
  </div>
</template>

<style scoped>
.status-view {
  padding: 1rem;
  overflow-y: auto;
}

.table-wrap {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 1rem;
}

th,
td {
  border: 1px solid var(--border);
  padding: 0.5rem;
  text-align: left;
}

th {
  background: var(--panel);
}

.human {
  color: var(--human);
}

.agent {
  color: var(--agent);
}
</style>
