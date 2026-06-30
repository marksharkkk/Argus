<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { VueFlow, useVueFlow, type Node, type Edge, type Connection } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import { fetchJson } from '../api'
import type { ArgusNode, ArgusEdge, ArgusTree } from '../types'

const props = defineProps<{ selected?: string | null }>()
const emit = defineEmits<{ (e: 'update:selected', id: string | null): void }>()

const elements = ref<any[]>([])
const selectedNode = computed(() => {
  if (!props.selected) return null
  const el = elements.value.find((n: any) => n.id === props.selected && 'position' in n)
  return (el as Node | undefined) || null
})
const selectedEdge = ref<Edge | null>(null)
const saveStatus = ref('')
const { screenToFlowPosition } = useVueFlow() as any

onMounted(async () => {
  await loadTree()
})

async function loadTree() {
  const tree: ArgusTree = await fetchJson('/api/tree')
  const nodes: Node[] = tree.nodes.map((node, idx) => ({
    id: node.id,
    type: 'default',
    position: { x: 80 + (idx % 4) * 220, y: 80 + Math.floor(idx / 4) * 160 },
    label: node.label,
    class: node.type,
    data: { raw: node },
  }))
  const edges: Edge[] = tree.edges.map((edge) => ({
    id: `${edge.from}-${edge.to}`,
    source: edge.from,
    target: edge.to,
    label: edge.bidirectional ? '↔' : '→',
    markerEnd: 'arrowclosed',
    data: { raw: edge },
  }))
  elements.value = [...nodes, ...edges]
}

function onNodeClick(event: any) {
  const node: Node = event.node
  selectedEdge.value = null
  emit('update:selected', node.id)
}

function onEdgeClick(event: any) {
  selectedEdge.value = event.edge
  emit('update:selected', null)
}

function onConnect(connection: Connection) {
  if (!connection.source || !connection.target) return
  const id = `${connection.source}-${connection.target}`
  if (elements.value.some((e) => 'source' in e && e.id === id)) return
  const edge: Edge = {
    id,
    source: connection.source,
    target: connection.target,
    label: '→',
    markerEnd: 'arrowclosed',
    data: { raw: { from: connection.source, to: connection.target, bidirectional: false } },
  }
  elements.value.push(edge)
}

function updateNodeFromForm() {
  if (!selectedNode.value) return
  const raw: ArgusNode = selectedNode.value.data.raw
  selectedNode.value.label = raw.label
  selectedNode.value.class = raw.type
}

function updateEdgeBidirectional() {
  if (!selectedEdge.value) return
  const raw: ArgusEdge = selectedEdge.value.data.raw
  selectedEdge.value.label = raw.bidirectional ? '↔' : '→'
}

function deleteSelected() {
  if (selectedNode.value) {
    const id = selectedNode.value.id
    elements.value = elements.value.filter((e) => e.id !== id && !('source' in e && (e.source === id || e.target === id)))
    emit('update:selected', null)
  } else if (selectedEdge.value) {
    elements.value = elements.value.filter((e) => e.id !== selectedEdge.value?.id)
    selectedEdge.value = null
  }
}

function onDragStart(event: DragEvent, type: string) {
  event.dataTransfer?.setData('application/argus-node-type', type)
}

function onDragOver(event: DragEvent) {
  event.preventDefault()
}

function onDrop(event: DragEvent) {
  event.preventDefault()
  const type = event.dataTransfer?.getData('application/argus-node-type') as 'human' | 'agent'
  if (!type) return
  const position = screenToFlowPosition({ x: event.clientX, y: event.clientY })
  const id = `${type}_${Date.now()}`
  const node: Node = {
    id,
    type: 'default',
    position,
    label: type === 'human' ? '新人类' : '新 Agent',
    class: type,
    data: {
      raw: {
        id,
        label: type === 'human' ? '新人类' : '新 Agent',
        type,
        metadata: {},
        ...(type === 'agent' ? { agent_id: id } : {}),
      } as ArgusNode,
    },
  }
  elements.value.push(node)
}

async function saveTree() {
  const nodes: ArgusNode[] = []
  const edges: ArgusEdge[] = []
  for (const el of elements.value) {
    if ('position' in el) {
      nodes.push(el.data.raw as ArgusNode)
    } else {
      const raw = el.data.raw as ArgusEdge
      edges.push({ ...raw, bidirectional: raw.bidirectional })
    }
  }
  await fetchJson('/api/tree', {
    method: 'POST',
    body: JSON.stringify({ nodes, edges }),
  })
  saveStatus.value = '已保存'
  setTimeout(() => (saveStatus.value = ''), 2000)
}

function parseMeta(value: string): Record<string, any> {
  try {
    return JSON.parse(value || '{}')
  } catch {
    return {}
  }
}

function formatMeta(value: Record<string, any> | undefined): string {
  return JSON.stringify(value || {}, null, 2)
}
</script>

<template>
  <div class="tree-editor">
    <div class="palette">
      <h3>节点</h3>
      <div class="draggable human" draggable="true" @dragstart="onDragStart($event, 'human')">
        人类节点
      </div>
      <div class="draggable agent" draggable="true" @dragstart="onDragStart($event, 'agent')">
        Agent 节点
      </div>
      <button class="save-btn" @click="saveTree">保存协作树</button>
      <span v-if="saveStatus" class="save-status">{{ saveStatus }}</span>
    </div>

    <div class="canvas" @drop="onDrop" @dragover="onDragOver">
      <VueFlow v-model="elements" @connect="onConnect" @node-click="onNodeClick" @edge-click="onEdgeClick" fit-view-on-init>
        <Background />
      </VueFlow>
    </div>

    <aside class="properties">
      <div v-if="selectedNode">
        <h3>节点属性</h3>
        <label>ID</label>
        <input v-model="selectedNode.data.raw.id" @change="updateNodeFromForm" />
        <label>Label</label>
        <input v-model="selectedNode.data.raw.label" @change="updateNodeFromForm" />
        <label>Type</label>
        <select v-model="selectedNode.data.raw.type" @change="updateNodeFromForm">
          <option value="human">human</option>
          <option value="agent">agent</option>
        </select>
        <label v-if="selectedNode.data.raw.type === 'agent'">Agent ID</label>
        <input v-if="selectedNode.data.raw.type === 'agent'" v-model="selectedNode.data.raw.agent_id" />
        <label v-if="selectedNode.data.raw.type === 'agent'">Model</label>
        <input v-if="selectedNode.data.raw.type === 'agent'" v-model="selectedNode.data.raw.model" />
        <label>Delivery (JSON)</label>
        <textarea rows="3" :value="formatMeta(selectedNode.data.raw.delivery)" @change="selectedNode.data.raw.delivery = parseMeta(($event.target as HTMLTextAreaElement).value)" />
        <label>Metadata (JSON)</label>
        <textarea rows="4" :value="formatMeta(selectedNode.data.raw.metadata)" @change="selectedNode.data.raw.metadata = parseMeta(($event.target as HTMLTextAreaElement).value)" />
      </div>
      <div v-else-if="selectedEdge">
        <h3>连线属性</h3>
        <p>{{ selectedEdge.source }} → {{ selectedEdge.target }}</p>
        <label>
          <input type="checkbox" v-model="selectedEdge.data.raw.bidirectional" @change="updateEdgeBidirectional" />
          双向
        </label>
      </div>
      <div v-else class="hint">
        选择一个节点或连线以编辑属性
      </div>
      <button v-if="selectedNode || selectedEdge" class="danger" @click="deleteSelected">删除选中</button>
    </aside>
  </div>
</template>

<style scoped>
.tree-editor {
  display: flex;
  width: 100%;
  height: 100%;
}

.palette {
  width: 160px;
  flex-shrink: 0;
  background: var(--panel);
  border-right: 1px solid var(--border);
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.palette h3 {
  margin: 0 0 0.5rem;
}

.draggable {
  padding: 0.75rem;
  border-radius: 0.375rem;
  cursor: grab;
  text-align: center;
  font-weight: 600;
  color: #0f172a;
}

.draggable.human {
  background: var(--human);
}

.draggable.agent {
  background: var(--agent);
}

.canvas {
  flex: 1 1 auto;
  position: relative;
  min-width: 200px;
  min-height: 0;
}

.properties {
  width: 260px;
  flex-shrink: 0;
  background: var(--panel);
  border-left: 1px solid var(--border);
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  overflow-y: auto;
}

.properties h3 {
  margin: 0 0 0.5rem;
}

.properties label {
  font-size: 0.8rem;
  color: var(--muted);
  margin-top: 0.5rem;
}

.properties input,
.properties select,
.properties textarea {
  width: 100%;
}

.properties .hint {
  color: var(--muted);
  font-size: 0.85rem;
}

.save-btn {
  margin-top: auto;
}

.save-status {
  font-size: 0.8rem;
  color: var(--agent);
}

.danger {
  background: #ef4444;
  color: white;
}
</style>

<style>
.vue-flow__node.human {
  background: var(--human);
  color: #0f172a;
  border-color: #b45309;
}

.vue-flow__node.agent {
  background: var(--agent);
  color: #0f172a;
  border-color: #047857;
}
</style>
