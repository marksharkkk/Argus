export const API_BASE = (import.meta.env.VITE_API_BASE as string) || (import.meta.env.DEV ? '' : 'http://127.0.0.1:18792')
export const WS_BASE = API_BASE.replace(/^http/, 'ws')

export async function fetchJson(path: string, options?: RequestInit): Promise<any> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json()
}

export function connectWebSocket(onMessage: (data: any) => void): WebSocket {
  const ws = new WebSocket(`${WS_BASE}/ws`)
  ws.onopen = () => console.log('Argus WebSocket connected')
  ws.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data))
    } catch (e) {
      onMessage(event.data)
    }
  }
  ws.onclose = () => console.log('Argus WebSocket closed')
  ws.onerror = (err) => console.error('Argus WebSocket error', err)
  return ws
}
