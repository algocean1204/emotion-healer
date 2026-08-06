import { useCallback, useEffect, useRef, useState } from 'react'
import { ChatMessageBubble } from '@astryxdesign/core/Chat'
import { Text } from '@astryxdesign/core/Text'
import { Banner } from '@astryxdesign/core/Banner'
import { Button } from '@astryxdesign/core/Button'
import type { ChatTurn } from '../App'
import { LONG_WAIT_NOTICE_MS, TYPING_CHAR_INTERVAL_MS } from '../constants'

function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

interface StepIndicatorProps {
  turn: ChatTurn
  onRevealDone: () => void
  onCancel: (turnId: string) => void
  onRetry: (turnId: string) => void
}

// 답이 40~150초 걸림. 그동안 무엇을 하는 중인지, 얼마나 지났는지 계속 말해줌
function Waiting({ turn, onCancel }: { turn: ChatTurn; onCancel: (turnId: string) => void }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const startedAt = Date.now()
    const timer = window.setInterval(
      () => setElapsed(Math.floor((Date.now() - startedAt) / 1000)),
      1000,
    )
    return () => window.clearInterval(timer)
  }, [turn.id])

  return (
    <ChatMessageBubble variant="ghost">
      <div className="waiting">
        <div className="waiting-line">
          <span className="waiting-dots" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <Text type="supporting" color="secondary">
            {turn.step || '생각하는 중'}
          </Text>
          <span className="waiting-elapsed">
            <Text type="supporting" color="secondary">
              {`${elapsed}초`}
            </Text>
          </span>
        </div>
        {elapsed * 1000 >= LONG_WAIT_NOTICE_MS && (
          <Text type="supporting" color="secondary" textWrap="pretty">
            보통 1~2분 걸려요. 창을 닫았다 와도 이어서 받을 수 있어요.
          </Text>
        )}
        <Button label="그만 기다리기" variant="ghost" size="sm" onClick={() => onCancel(turn.id)} />
      </div>
    </ChatMessageBubble>
  )
}

// 어시스턴트 턴 하나의 대기·완성본·에러를 그림
export function StepIndicator({ turn, onRevealDone, onCancel, onRetry }: StepIndicatorProps) {
  const [shownLength, setShownLength] = useState(0)
  const [didCopy, setDidCopy] = useState(false)
  const revealedTurnId = useRef<string | null>(null)
  const typingTimer = useRef<number | undefined>(undefined)

  const finishTyping = useCallback(() => {
    window.clearInterval(typingTimer.current)
    typingTimer.current = undefined
    setShownLength(turn.text.length)
    onRevealDone()
  }, [turn.text.length, onRevealDone])

  useEffect(() => {
    if (turn.state !== 'done') return
    if (revealedTurnId.current === turn.id) return
    revealedTurnId.current = turn.id

    if (prefersReducedMotion() || turn.text.length === 0) {
      setShownLength(turn.text.length)
      onRevealDone()
      return
    }

    setShownLength(0)
    let shown = 0
    typingTimer.current = window.setInterval(() => {
      shown += 1
      setShownLength(shown)
      if (shown >= turn.text.length) {
        window.clearInterval(typingTimer.current)
        typingTimer.current = undefined
        onRevealDone()
      }
    }, TYPING_CHAR_INTERVAL_MS)
    return () => window.clearInterval(typingTimer.current)
  }, [turn.state, turn.id, turn.text, onRevealDone])

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(turn.text)
    setDidCopy(true)
    window.setTimeout(() => setDidCopy(false), 1500)
  }, [turn.text])

  if (turn.state === 'error') {
    return (
      <Banner
        status="error"
        title="답변을 받지 못했어요"
        description={turn.text}
        endContent={
          turn.source ? (
            <Button
              label="다시 보내기"
              variant="secondary"
              size="sm"
              onClick={() => onRetry(turn.id)}
            />
          ) : undefined
        }
      />
    )
  }

  if (turn.state === 'pending') {
    return <Waiting turn={turn} onCancel={onCancel} />
  }

  const isTyping = shownLength < turn.text.length
  return (
    <div className="answer">
      <ChatMessageBubble>
        <span className="message-text">{turn.text.slice(0, shownLength)}</span>
      </ChatMessageBubble>
      <div className="answer-actions">
        {isTyping ? (
          // 연출이 읽기를 늦추면 안 됨. 건너뛸 수 있다는 걸 알려주고 실제로 건너뜀
          <Button label="한 번에 보기" variant="ghost" size="sm" onClick={finishTyping} />
        ) : (
          <Button
            label={didCopy ? '복사됨' : '복사'}
            variant="ghost"
            size="sm"
            clickAction={handleCopy}
          />
        )}
      </div>
    </div>
  )
}
