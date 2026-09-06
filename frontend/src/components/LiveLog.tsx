import { useEffect, useRef, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { X, PauseCircle, PlayCircle } from 'lucide-react'
import { fetchEventSource } from '../api/fetchEventSource'

const MAX_LINES = 500
const BATCH_MS = 250

function lineColor(line: string): string {
  const upper = line.toUpperCase()
  if (upper.includes('[ERROR]') || upper.includes(' ERROR ') || upper.includes(':ERROR:'))
    return 'text-red-400'
  if (upper.includes('[WARNING]') || upper.includes('[WARN]') || upper.includes(' WARNING '))
    return 'text-yellow-400'
  return 'text-gray-300'
}

export default function LiveLog() {
  const { t } = useTranslation()
  const [lines, setLines] = useState<string[]>([])
  const [connected, setConnected] = useState(false)
  const [paused, setPaused] = useState(false)
  const [levelFilter, setLevelFilter] = useState<'all' | 'error' | 'warning' | 'info'>('all')
  const bottomRef = useRef<HTMLDivElement>(null)
  const pausedRef = useRef(false)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reconnectDelayRef = useRef(1000)
  const pendingRef = useRef<string[]>([])
  const batchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const connectionIdRef = useRef(0)

  pausedRef.current = paused

  const flushPending = useCallback(() => {
    if (pendingRef.current.length === 0) return
    const batch = pendingRef.current
    pendingRef.current = []
    setLines((prev) => {
      const merged = [...prev, ...batch]
      return merged.length > MAX_LINES ? merged.slice(-MAX_LINES) : merged
    })
  }, [])

  useEffect(() => {
    const connectionId = connectionIdRef.current + 1
    connectionIdRef.current = connectionId
    let disposed = false
    const token = localStorage.getItem('paperless_token')
    const headers: Record<string, string> = {}
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    let activeController: AbortController | null = null
    const isCurrentConnection = () => !disposed && connectionIdRef.current === connectionId

    const connect = () => {
      if (!isCurrentConnection()) return
      if (activeController) {
        activeController.abort()
      }
      activeController = fetchEventSource({
        url: '/api/stats/logs/stream',
        headers,
        onopen: () => {
          if (!isCurrentConnection()) return
          setConnected(true)
          setLines([])
          pendingRef.current = []
          reconnectDelayRef.current = 1000
        },
        onerror: () => {
          if (!isCurrentConnection()) return
          setConnected(false)
          scheduleReconnect()
        },
        onclose: () => {
          if (!isCurrentConnection()) return
          setConnected(false)
          scheduleReconnect()
        },
        onmessage: (data) => {
          if (!isCurrentConnection()) return
          try {
            const line = JSON.parse(data)
            if (typeof line === 'string') {
              pendingRef.current.push(line)
              if (!batchTimerRef.current) {
                batchTimerRef.current = setTimeout(() => {
                  batchTimerRef.current = null
                  flushPending()
                }, BATCH_MS)
              }
            }
          } catch {
            // ignore malformed
          }
        },
      })
    }

    const scheduleReconnect = () => {
      if (!isCurrentConnection()) return
      if (reconnectTimeoutRef.current) return
      reconnectTimeoutRef.current = setTimeout(() => {
        reconnectTimeoutRef.current = null
        connect()
        reconnectDelayRef.current = Math.min(reconnectDelayRef.current * 2, 30000)
      }, reconnectDelayRef.current)
    }

    connect()

    return () => {
      disposed = true
      if (batchTimerRef.current) {
        clearTimeout(batchTimerRef.current)
        batchTimerRef.current = null
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }
      if (activeController) {
        activeController.abort()
      }
    }
  }, [flushPending])

  useEffect(() => {
    if (!paused && bottomRef.current) {
      bottomRef.current.scrollIntoView({ block: 'end' })
    }
  }, [lines, paused])

  const visibleLines = lines.filter((line) => {
    const upper = line.toUpperCase()
    if (levelFilter === 'error') return upper.includes('ERROR')
    if (levelFilter === 'warning') return upper.includes('WARN') || upper.includes('WARNING')
    if (levelFilter === 'info') {
      return !upper.includes('ERROR') && !upper.includes('WARN') && !upper.includes('WARNING')
    }
    return true
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{t('logs.title')}</h1>
          <span
            className={`w-2.5 h-2.5 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`}
            title={connected ? t('logs.connected') : t('logs.disconnected')}
          />
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {connected ? t('logs.live') : t('logs.disconnected')}
          </span>
        </div>
        <div className="flex gap-2 flex-wrap justify-end">
          {(['all', 'error', 'warning', 'info'] as const).map((level) => (
            <button
              key={level}
              onClick={() => setLevelFilter(level)}
              className={`px-3 py-2 text-xs rounded-lg border ${
                levelFilter === level
                  ? 'bg-blue-50 dark:bg-blue-900/40 border-blue-300 dark:border-blue-700 text-blue-700 dark:text-blue-300'
                  : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
            >
              {t(`logs.filter.${level}`)}
            </button>
          ))}
          <button
            onClick={() => setPaused((p) => !p)}
            className="flex items-center gap-1 px-3 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600"
          >
            {paused ? <PlayCircle size={16} /> : <PauseCircle size={16} />}
            {paused ? t('logs.resume') : t('logs.pause')}
          </button>
          <button
            onClick={() => setLines([])}
            className="flex items-center gap-1 px-3 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600"
          >
            <X size={16} />
            {t('logs.clear')}
          </button>
        </div>
      </div>

      <div
        className="bg-gray-900 rounded-lg font-mono text-xs overflow-y-auto"
        style={{ height: 'calc(100vh - 200px)' }}
      >
        {!connected && (
          <div className="px-4 py-2 bg-yellow-500/10 border-b border-yellow-500/30 text-yellow-200">
            {t('logs.reconnecting')}
          </div>
        )}
        {lines.length === 0 ? (
          <p className="text-gray-500 dark:text-gray-400 p-4">{t('logs.emptyState')}</p>
        ) : visibleLines.length === 0 ? (
          <p className="text-gray-500 dark:text-gray-400 p-4">{t('logs.noEntriesForFilter')}</p>
        ) : (
          <div className="p-4 space-y-0.5">
            {visibleLines.map((line, i) => (
              <div key={i} className={`whitespace-pre-wrap break-all leading-5 ${lineColor(line)}`}>
                {line}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
    </div>
  )
}
