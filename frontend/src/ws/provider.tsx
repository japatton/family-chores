import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { useQueryClient, type QueryClient } from '@tanstack/react-query'

interface WSContextValue {
  connected: boolean
}

const WSContext = createContext<WSContextValue>({ connected: false })

interface WireEvent {
  type: string
  [k: string]: unknown
}

function invalidateForEvent(qc: QueryClient, ev: WireEvent): void {
  switch (ev.type) {
    case 'hello':
      return
    case 'member_created':
    case 'member_updated':
    case 'member_deleted':
      qc.invalidateQueries({ queryKey: ['members'] })
      qc.invalidateQueries({ queryKey: ['today'] })
      return
    case 'chore_created':
    case 'chore_updated':
    case 'chore_deleted':
      qc.invalidateQueries({ queryKey: ['chores'] })
      qc.invalidateQueries({ queryKey: ['today'] })
      return
    case 'instance_updated':
      qc.invalidateQueries({ queryKey: ['today'] })
      qc.invalidateQueries({ queryKey: ['instances'] })
      qc.invalidateQueries({ queryKey: ['members'] })
      return
    case 'pin_set':
    case 'pin_cleared':
      qc.invalidateQueries({ queryKey: ['whoami'] })
      return
    case 'stats_rebuilt':
      qc.invalidateQueries()
      return
    default:
      return
  }
}

function buildWsURL(): string {
  // document.baseURI resolves relative hrefs correctly (including under
  // HA Ingress). Then swap http(s) for ws(s).
  const rel = new URL('./api/ws', document.baseURI)
  rel.protocol = rel.protocol === 'https:' ? 'wss:' : 'ws:'
  return rel.toString()
}

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [connected, setConnected] = useState(false)
  const socketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let stopped = false
    let backoffMs = 1000

    function connect(): void {
      if (stopped) return
      let ws: WebSocket
      try {
        ws = new WebSocket(buildWsURL())
      } catch {
        // URL invalid in this environment — never happens under Ingress
        return
      }
      socketRef.current = ws

      ws.addEventListener('open', () => {
        setConnected(true)
        backoffMs = 1000
      })
      ws.addEventListener('close', () => {
        setConnected(false)
        if (!stopped) {
          window.setTimeout(connect, backoffMs)
          backoffMs = Math.min(backoffMs * 2, 30_000)
        }
      })
      ws.addEventListener('error', () => {
        // Let close handler drive reconnect.
      })
      ws.addEventListener('message', (e) => {
        try {
          const parsed = JSON.parse(String(e.data)) as WireEvent
          invalidateForEvent(qc, parsed)
        } catch {
          // non-JSON frames (e.g. our pong) are ignored.
        }
      })
    }

    connect()

    return () => {
      stopped = true
      socketRef.current?.close()
      socketRef.current = null
    }
  }, [qc])

  return <WSContext.Provider value={{ connected }}>{children}</WSContext.Provider>
}

export function useWSConnected(): boolean {
  return useContext(WSContext).connected
}
