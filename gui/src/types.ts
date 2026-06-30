export interface ArgusNode {
  id: string
  label: string
  type: 'human' | 'agent'
  agent_id?: string | null
  model?: string | null
  delivery?: Record<string, any> | null
  metadata?: Record<string, any>
}

export interface ArgusEdge {
  from: string
  to: string
  bidirectional: boolean
}

export interface ArgusTree {
  nodes: ArgusNode[]
  edges: ArgusEdge[]
}

export interface ArgusMessage {
  id: string
  from_id: string
  to: string[]
  text: string
  timestamp: string
  is_group: boolean
}

export interface Meeting {
  id: string
  topic: string
  organizer: string
  participants: string[]
  status: 'pending' | 'running' | 'closed'
  created_at: string
  closed_at: string | null
  messages: { speaker: string; text: string; timestamp: string }[]
}
