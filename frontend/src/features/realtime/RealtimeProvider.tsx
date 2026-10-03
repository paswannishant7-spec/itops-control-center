import { useQueryClient } from '@tanstack/react-query'
import { type PropsWithChildren, useEffect, useRef, useState } from 'react'
import { useAuth } from '../auth/authContextValue'
import {
  realtimeMessageSchema,
  realtimeUrl,
  topicQueryKeys,
  type RealtimeTopic,
} from './realtime'
import './realtime.css'

type ConnectionState = 'connecting' | 'live' | 'reconnecting' | 'paused'

const labels: Record<ConnectionState, string> = {
  connecting: 'Connecting live updates',
  live: 'Live updates connected',
  reconnecting: 'Reconnecting live updates',
  paused: 'Live updates paused',
}

export function RealtimeProvider({ children }: PropsWithChildren) {
  const { accessToken, user, refresh } = useAuth()
  const queryClient = useQueryClient()
  const [state, setState] = useState<ConnectionState>('paused')
  const previousUser = useRef<string | null>(null)

  useEffect(() => {
    const next = user?.id ?? null
    if (previousUser.current && previousUser.current !== next)
      queryClient.clear()
    previousUser.current = next
  }, [queryClient, user?.id])

  useEffect(() => {
    if (!accessToken || !user) return
    let disposed = false
    let socket: WebSocket | null = null
    let reconnectTimer: number | undefined
    let fallbackTimer: number | undefined
    let debounceTimer: number | undefined
    let attempt = 0
    let cursor = 0
    const pending = new Set<Exclude<RealtimeTopic, 'access'>>()

    const refreshAll = () => void queryClient.invalidateQueries()
    const startFallback = () => {
      if (fallbackTimer !== undefined) return
      fallbackTimer = window.setInterval(refreshAll, 30_000)
    }
    const stopFallback = () => {
      if (fallbackTimer !== undefined) window.clearInterval(fallbackTimer)
      fallbackTimer = undefined
    }
    const flushInvalidations = () => {
      debounceTimer = undefined
      for (const topic of pending) {
        for (const key of topicQueryKeys[topic])
          void queryClient.invalidateQueries({ queryKey: [key] })
      }
      pending.clear()
    }
    const invalidate = (topic: Exclude<RealtimeTopic, 'access'>) => {
      pending.add(topic)
      if (debounceTimer === undefined)
        debounceTimer = window.setTimeout(flushInvalidations, 75)
    }
    const scheduleReconnect = () => {
      if (disposed || reconnectTimer !== undefined) return
      setState('reconnecting')
      startFallback()
      const delay = Math.min(30_000, 1000 * 2 ** Math.min(attempt, 5))
      attempt += 1
      reconnectTimer = window.setTimeout(
        () => {
          reconnectTimer = undefined
          connect()
        },
        delay + Math.floor(Math.random() * 250),
      )
    }
    const connect = () => {
      if (disposed) return
      setState(attempt ? 'reconnecting' : 'connecting')
      try {
        socket = new WebSocket(realtimeUrl())
      } catch {
        scheduleReconnect()
        return
      }
      socket.onopen = () => {
        socket?.send(
          JSON.stringify({ type: 'authenticate', access_token: accessToken }),
        )
      }
      socket.onmessage = (event) => {
        let raw: unknown
        try {
          raw = JSON.parse(String(event.data))
        } catch {
          return
        }
        const parsed = realtimeMessageSchema.safeParse(raw)
        if (!parsed.success) return
        const message = parsed.data
        if (message.type === 'ping') {
          if (socket?.readyState === WebSocket.OPEN)
            socket.send(JSON.stringify({ type: 'pong' }))
          return
        }
        if (message.type === 'ready') {
          cursor = message.cursor
          attempt = 0
          setState('live')
          stopFallback()
          refreshAll()
          return
        }
        if (message.type === 'resync') {
          cursor = Math.max(cursor, message.cursor)
          refreshAll()
          if (message.reason === 'access_changed' && refresh) void refresh()
          return
        }
        if (message.sequence <= cursor) return
        cursor = message.sequence
        invalidate(message.topic)
      }
      socket.onclose = (event) => {
        socket = null
        if (disposed) return
        if (event.code === 4401 || event.code === 4403) {
          setState('paused')
          startFallback()
          if (event.code === 4401 && refresh)
            void refresh().catch(() => undefined)
          return
        }
        scheduleReconnect()
      }
      socket.onerror = () => socket?.close()
    }

    connect()
    return () => {
      disposed = true
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
      if (fallbackTimer !== undefined) window.clearInterval(fallbackTimer)
      if (debounceTimer !== undefined) window.clearTimeout(debounceTimer)
      socket?.close(1000, 'Client session changed')
    }
  }, [accessToken, queryClient, refresh, user])

  const visibleState = user && accessToken ? state : 'paused'

  return (
    <>
      {children}
      {user ? (
        <div
          className={`realtime-status realtime-status--${visibleState}`}
          role="status"
        >
          <span aria-hidden="true" />
          {labels[visibleState]}
        </div>
      ) : null}
    </>
  )
}
