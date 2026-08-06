import { useCallback, useEffect, useRef, useState } from 'react'
import { Banner } from '@astryxdesign/core/Banner'
import { Icon } from '@astryxdesign/core/Icon'
import { IconButton } from '@astryxdesign/core/IconButton'
import { Text } from '@astryxdesign/core/Text'
import { VisuallyHidden } from '@astryxdesign/core/VisuallyHidden'
import { ChatLog } from './components/ChatLog'
import { Composer } from './components/Composer'
import { Intro } from './components/Intro'
import { LoginGate } from './components/LoginGate'
import { MemoryPanel } from './components/MemoryPanel'
import { MoreMenu } from './components/MoreMenu'
import { SessionMenu } from './components/SessionMenu'
import { Symbol } from './components/Symbol'
import {
  cancelChat,
  createSession,
  fetchChatJob,
  fetchSessionMessages,
  fetchSessions,
  logout,
  startChat,
  startOpening,
  whoAmI,
  type ChatJobResult,
} from './api/client'
import {
  ASSISTANT_NAME,
  DRAFT_STORAGE_KEY,
  INTRO_SEEN_STORAGE_KEY,
  MAX_CONSECUTIVE_POLL_FAILURES,
  MAX_WAIT_MS,
  PENDING_JOB_STORAGE_KEY,
  POLL_INTERVAL_MS,
  SERVICE_NAME,
  SESSION_ID_STORAGE_KEY,
} from './constants'

export interface ChatTurn {
  id: string
  role: 'user' | 'assistant'
  state: 'sent' | 'pending' | 'done' | 'error'
  text: string
  step: string | null
  // 실패했을 때 무엇을 다시 보내야 하는지. 어시스턴트 턴에만 있음
  source?: string
}

interface PendingJob {
  jobId: string
  turnId: string
  sessionId: string
  kind?: 'chat' | 'opening'
  message?: string
}

function readPendingJob(): PendingJob | null {
  const raw = localStorage.getItem(PENDING_JOB_STORAGE_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as PendingJob
  } catch {
    return null
  }
}

function clearPendingJob() {
  localStorage.removeItem(PENDING_JOB_STORAGE_KEY)
}

function newId(): string {
  // http(비보안) 컨텍스트에서는 randomUUID 가 없음
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

function draftKey(user: string, session: string) {
  return `${DRAFT_STORAGE_KEY}.${user}.${session}`
}

function readDraft(user: string, session: string) {
  try {
    return localStorage.getItem(draftKey(user, session)) ?? ''
  } catch {
    return ''
  }
}

function writeDraft(user: string, session: string, text: string) {
  try {
    const key = draftKey(user, session)
    if (text) localStorage.setItem(key, text)
    else localStorage.removeItem(key)
  } catch {
    // 사파리 프라이빗 등
  }
}

export default function App() {
  const [userId, setUserId] = useState<string | null>(null)
  const [isCheckingSignIn, setIsCheckingSignIn] = useState(true)
  const [needsIntro, setNeedsIntro] = useState(false)
  const [sessionId, setSessionId] = useState('')
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [draft, setDraft] = useState('')
  const [isOnline, setIsOnline] = useState(() => navigator.onLine)
  const [openPanel, setOpenPanel] = useState<'sessions' | 'memory' | 'more' | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  // 서버를 기다리는 동안만 입력을 잠금. 타이핑 연출 중에는 다시 쓸 수 있음
  const [isWaiting, setIsWaiting] = useState(false)
  const [isRevealing, setIsRevealing] = useState(false)
  const consecutiveFailures = useRef(0)
  // 폴링 세대. 취소·세션 전환·재시도 때 올려서 옛 tick 이 답을 덮지 못하게 함
  const pollGeneration = useRef(0)
  const stopPolling = useRef<(() => void) | null>(null)
  const activeSession = useRef('')

  const patchTurn = useCallback((id: string, patch: Partial<ChatTurn>) => {
    setTurns((prev) => prev.map((turn) => (turn.id === id ? { ...turn, ...patch } : turn)))
  }, [])

  const haltPolling = useCallback(() => {
    pollGeneration.current += 1
    stopPolling.current?.()
    stopPolling.current = null
  }, [])

  // 새로고침해도 로그인은 쿠키에 남아 있음. JS 는 토큰을 만지지 않음
  useEffect(() => {
    whoAmI()
      .then((found) => {
        setUserId(found)
        if (found) setNeedsIntro(!localStorage.getItem(`${INTRO_SEEN_STORAGE_KEY}.${found}`))
      })
      .catch(() => setUserId(null))
      .finally(() => setIsCheckingSignIn(false))
  }, [])

  // 끊긴 걸 모르고 계속 보내면 실패만 쌓임
  useEffect(() => {
    const goOnline = () => setIsOnline(true)
    const goOffline = () => setIsOnline(false)
    window.addEventListener('online', goOnline)
    window.addEventListener('offline', goOffline)
    return () => {
      window.removeEventListener('online', goOnline)
      window.removeEventListener('offline', goOffline)
    }
  }, [])

  // 쓰다 만 글은 사람·대화마다 따로. 남의 초안이 따라오지 않게 함
  useEffect(() => {
    if (!userId || !sessionId) return
    setDraft(readDraft(userId, sessionId))
  }, [userId, sessionId])

  useEffect(() => {
    if (!userId || !sessionId) return
    writeDraft(userId, sessionId, draft)
  }, [draft, userId, sessionId])

  // 로그인하면 마지막으로 보던 대화를 잇고, 없으면 새로 만듦
  useEffect(() => {
    if (!userId) return
    let cancelled = false
    const saved = localStorage.getItem(SESSION_ID_STORAGE_KEY)
    const resume = async () => {
      try {
        const found = await fetchSessions()
        const known = found.find((item) => item.session_id === saved)
        const picked = known?.session_id ?? found[0]?.session_id ?? (await createSession())
        if (!cancelled) {
          setLoadError(null)
          setSessionId(picked)
        }
      } catch {
        if (!cancelled) setLoadError('대화를 불러오지 못했어요. 새로고침 해주세요.')
      }
    }
    void resume()
    return () => {
      cancelled = true
    }
  }, [userId])

  // status가 done/error가 될 때까지 1초 간격으로 물어봄. 절대 영원히 돌지 않음
  const pollJob = useCallback(
    (jobId: string, turnId: string) => {
      haltPolling()
      const generation = pollGeneration.current
      let timer: number | undefined
      const startedAt = Date.now()

      const tick = async () => {
        // 취소·재시도·세션 전환 뒤의 좀비 tick 은 아무 것도 안 함
        if (generation !== pollGeneration.current) return

        let result: ChatJobResult
        try {
          result = await fetchChatJob(jobId)
          if (generation !== pollGeneration.current) return
          consecutiveFailures.current = 0
        } catch {
          if (generation !== pollGeneration.current) return
          consecutiveFailures.current += 1
          if (consecutiveFailures.current < MAX_CONSECUTIVE_POLL_FAILURES) {
            timer = window.setTimeout(tick, POLL_INTERVAL_MS)
            return
          }
          result = { status: 'error', error: '서버와 연결이 끊겼어요.' }
        }

        if (generation !== pollGeneration.current) return

        if (result.status === 'running') {
          if (Date.now() - startedAt > MAX_WAIT_MS) {
            result = { status: 'error', error: '답변이 너무 오래 걸려 기다리기를 멈췄어요.' }
            void cancelChat(jobId)
          } else {
            patchTurn(turnId, { step: result.step })
            timer = window.setTimeout(tick, POLL_INTERVAL_MS)
            return
          }
        }

        if (generation !== pollGeneration.current) return

        clearPendingJob()
        stopPolling.current = null
        setIsWaiting(false)
        if (result.status === 'done') {
          setIsRevealing(true)
          patchTurn(turnId, { state: 'done', text: result.text, step: null })
        } else {
          patchTurn(turnId, { state: 'error', text: result.error, step: null })
        }
      }

      timer = window.setTimeout(tick, 0)
      const stop = () => window.clearTimeout(timer)
      stopPolling.current = stop
      return stop
    },
    [haltPolling, patchTurn],
  )

  const openChat = useCallback(
    async (assistantTurnId: string) => {
      const requestedSessionId = sessionId
      setIsWaiting(true)
      consecutiveFailures.current = 0
      try {
        const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Seoul'
        const result = await startOpening(requestedSessionId, timezone)
        if (activeSession.current !== requestedSessionId) return
        if (!result.needed) {
          setTurns((prev) => prev.filter((turn) => turn.id !== assistantTurnId))
          setIsWaiting(false)
          return
        }
        localStorage.setItem(
          PENDING_JOB_STORAGE_KEY,
          JSON.stringify({ jobId: result.job_id, turnId: assistantTurnId, sessionId: requestedSessionId, kind: 'opening' }),
        )
        pollJob(result.job_id, assistantTurnId)
      } catch (err) {
        if (activeSession.current !== requestedSessionId) return
        setIsWaiting(false)
        patchTurn(assistantTurnId, {
          state: 'error',
          text: err instanceof Error ? err.message : '첫 인사를 만들지 못했어요.',
          step: null,
        })
      }
    },
    [sessionId, pollJob, patchTurn],
  )

  // 대화를 바꾸면 기록을 올리고, 이 세션의 미완료 잡이 있으면 폴링을 재개함
  useEffect(() => {
    if (!sessionId) return
    activeSession.current = sessionId
    localStorage.setItem(SESSION_ID_STORAGE_KEY, sessionId)
    haltPolling()
    setIsWaiting(false)
    let cancelled = false

    setLoadError(null)
    fetchSessionMessages(sessionId)
      .then((messages) => {
        if (cancelled) return
        const loaded: ChatTurn[] = messages.map((message) => ({
          id: newId(),
          role: message.role === 'human' ? 'user' : 'assistant',
          state: 'done' as const,
          text: message.text,
          step: null,
        }))

        const pending = readPendingJob()
        if (pending && pending.sessionId === sessionId) {
          // 서버에 아직 답이 없을 수 있어 대기 턴을 붙이고 폴링을 이어 받음
          const assistantTurnId = pending.turnId || newId()
          if (pending.kind === 'opening') {
            loaded.push({
              id: assistantTurnId,
              role: 'assistant',
              state: 'pending',
              text: '',
              step: '채팅창 여는 중…',
            })
          } else {
            loaded.push(
              {
                id: newId(),
                role: 'user',
                state: 'sent',
                text: pending.message ?? '',
                step: null,
              },
              {
                id: assistantTurnId,
                role: 'assistant',
                state: 'pending',
                text: '',
                step: null,
                source: pending.message,
              },
            )
          }
          setTurns(loaded)
          setIsWaiting(true)
          pollJob(pending.jobId, assistantTurnId)
          return
        }

        const lastTurn = loaded[loaded.length - 1]
        if (lastTurn?.role === 'user') {
          setTurns([
            ...loaded,
            {
              id: newId(),
              role: 'assistant',
              state: 'error',
              text: '답변을 이어받지 못했어요. 다시 보내주세요.',
              step: null,
              source: lastTurn.text,
            },
          ])
          return
        }

        const assistantTurnId = newId()
        setTurns([
          ...loaded,
          {
            id: assistantTurnId,
            role: 'assistant',
            state: 'pending',
            text: '',
            step: '채팅창 여는 중…',
          },
        ])
        void openChat(assistantTurnId)
      })
      .catch(() => {
        if (!cancelled) {
          setTurns([])
          setLoadError('이 대화 기록을 불러오지 못했어요.')
        }
      })

    return () => {
      cancelled = true
    }
  }, [sessionId, haltPolling, pollJob, openChat])

  // 서버 잡까지 멈춤. 폴링만 끊으면 다음 메시지가 중복 방지에 걸려 버려짐
  const handleCancel = useCallback(
    (turnId: string) => {
      const pending = readPendingJob()
      haltPolling()
      if (pending) void cancelChat(pending.jobId)
      clearPendingJob()
      setIsWaiting(false)
      patchTurn(turnId, { state: 'error', text: '기다리기를 멈췄어요.', step: null })
    },
    [haltPolling, patchTurn],
  )

  const send = useCallback(
    async (message: string, assistantTurnId: string) => {
      setIsWaiting(true)
      consecutiveFailures.current = 0
      try {
        const { job_id, accepted } = await startChat(message, sessionId)
        if (!accepted) {
          // 서버에 아직 도는 잡이 있음. 새 메시지로 착각하지 말고 그걸 이어 받음
          const existing = readPendingJob()
          if (existing && existing.jobId === job_id) {
            pollJob(job_id, existing.turnId)
            patchTurn(assistantTurnId, {
              state: 'error',
              text: '아직 이전 답변을 만들고 있어요. 잠시만요.',
            })
            setIsWaiting(true)
            return
          }
          localStorage.setItem(
            PENDING_JOB_STORAGE_KEY,
            JSON.stringify({
              jobId: job_id,
              turnId: assistantTurnId,
              message,
              sessionId,
              kind: 'chat',
            }),
          )
          pollJob(job_id, assistantTurnId)
          return
        }
        localStorage.setItem(
          PENDING_JOB_STORAGE_KEY,
          JSON.stringify({
            jobId: job_id,
            turnId: assistantTurnId,
            message,
            sessionId,
            kind: 'chat',
          }),
        )
        pollJob(job_id, assistantTurnId)
      } catch (err) {
        setIsWaiting(false)
        patchTurn(assistantTurnId, {
          state: 'error',
          text: err instanceof Error ? err.message : '보내지 못했어요.',
        })
      }
    },
    [sessionId, pollJob, patchTurn],
  )

  const handleSubmit = useCallback(
    async (message: string) => {
      const trimmed = message.trim()
      if (!trimmed || isWaiting || !sessionId) return

      setIsRevealing(false)
      setDraft('')
      const assistantTurnId = newId()
      setTurns((prev) => [
        ...prev,
        { id: newId(), role: 'user', state: 'sent', text: trimmed, step: null },
        {
          id: assistantTurnId,
          role: 'assistant',
          state: 'pending',
          text: '',
          step: null,
          source: trimmed,
        },
      ])
      await send(trimmed, assistantTurnId)
    },
    [isWaiting, sessionId, send],
  )

  // 실패한 턴 자리에서 그대로 다시 보냄. 사용자가 다시 타이핑하게 두지 않음
  const handleRetry = useCallback(
    async (turnId: string) => {
      const failed = turns.find((turn) => turn.id === turnId)
      if (!failed?.source || isWaiting) return
      haltPolling()
      patchTurn(turnId, { state: 'pending', text: '', step: null })
      await send(failed.source, turnId)
    },
    [turns, isWaiting, send, patchTurn, haltPolling],
  )

  const handleSignOut = useCallback(async () => {
    const pending = readPendingJob()
    haltPolling()
    if (pending) void cancelChat(pending.jobId)
    await logout()
    clearPendingJob()
    localStorage.removeItem(SESSION_ID_STORAGE_KEY)
    setUserId(null)
    setSessionId('')
    setTurns([])
    setDraft('')
    setIsWaiting(false)
    setOpenPanel(null)
  }, [haltPolling])

  const handleIntroDone = useCallback(() => {
    if (userId) localStorage.setItem(`${INTRO_SEEN_STORAGE_KEY}.${userId}`, '1')
    setNeedsIntro(false)
  }, [userId])

  const handleSignedIn = useCallback((found: string) => {
    setUserId(found)
    setNeedsIntro(!localStorage.getItem(`${INTRO_SEEN_STORAGE_KEY}.${found}`))
  }, [])

  const handleRevealDone = useCallback(() => setIsRevealing(false), [])

  if (isCheckingSignIn) return <div className="app-shell" />

  if (!userId) {
    return (
      <div className="app-shell">
        <VisuallyHidden as="h1">{SERVICE_NAME} 로그인</VisuallyHidden>
        <LoginGate onSignedIn={handleSignedIn} />
      </div>
    )
  }

  if (needsIntro) {
    return (
      <div className="app-shell">
        <VisuallyHidden as="h1">{SERVICE_NAME} 안내</VisuallyHidden>
        <Intro onDone={handleIntroDone} />
      </div>
    )
  }

  if (openPanel === 'memory') {
    return (
      <div className="memory-page-shell">
        <MemoryPanel onClose={() => setOpenPanel(null)} />
      </div>
    )
  }

  const isOpening = turns.some(
    (turn) => turn.role === 'assistant' && turn.state === 'pending' && turn.step === '채팅창 여는 중…',
  )
  const status = !isOnline ? '연결이 끊겼어요' : isOpening ? '채팅창 여는 중' : isWaiting ? '생각하는 중' : '듣고 있어요'

  return (
    <div className="app-shell">
      <VisuallyHidden as="h1">{SERVICE_NAME}와 대화</VisuallyHidden>
      <header className="page-header">
        <div className="page-identity">
          <Symbol size={36} isDecorative />
          <span className="page-identity-text">
            <Text type="label">{ASSISTANT_NAME}</Text>
            <Text type="supporting" color="secondary">
              {status}
            </Text>
          </span>
        </div>
        <IconButton
          icon={<Icon icon="menu" />}
          label="대화 목록"
          variant="ghost"
          tooltip="대화 목록"
          onClick={() => setOpenPanel('sessions')}
        />
        <IconButton
          icon={<Icon icon="moreHorizontal" />}
          label="더보기"
          variant="ghost"
          tooltip="더보기"
          onClick={() => setOpenPanel('more')}
        />
      </header>

      {!isOnline && (
        <Banner
          status="warning"
          title="오프라인"
          description="연결이 복구되면 다시 보낼 수 있어요."
        />
      )}
      {loadError && (
        <div className="load-error">
          <Banner status="error" title="불러오기 실패" description={loadError} />
        </div>
      )}

      <main className="chat-region">
        <ChatLog
          turns={turns}
          isBusy={isWaiting || isRevealing}
          composer={
            <Composer
              value={draft}
              onChange={setDraft}
              onSubmit={handleSubmit}
              isDisabled={isWaiting || !isOnline}
            />
          }
          onCancel={handleCancel}
          onRetry={handleRetry}
          onRevealDone={handleRevealDone}
          onPickStarter={(seed) => setDraft(seed)}
        />
      </main>

      <SessionMenu
        isOpen={openPanel === 'sessions'}
        currentId={sessionId}
        onOpenChange={(open) => setOpenPanel(open ? 'sessions' : null)}
        onPick={(id) => {
          haltPolling()
          setSessionId(id)
          setOpenPanel(null)
        }}
      />
      <MoreMenu
        isOpen={openPanel === 'more'}
        userId={userId}
        onOpenChange={(open) => setOpenPanel(open ? 'more' : null)}
        onOpenMemory={() => setOpenPanel('memory')}
        onSignOut={handleSignOut}
      />
    </div>
  )
}
