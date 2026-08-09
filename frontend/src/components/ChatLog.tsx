import { Fragment, type ReactNode } from 'react'
import { ChatLayout, ChatMessageList, ChatMessage, ChatMessageBubble } from '@astryxdesign/core/Chat'
import type { ChatTurn } from '../App'
import { Greeting } from './Greeting'
import { StepIndicator } from './StepIndicator'
import { Symbol } from './Symbol'
import { ASSISTANT_NAME } from '../constants'

interface ChatLogProps {
  turns: ChatTurn[]
  isBusy: boolean
  composer: ReactNode
  onRevealDone: () => void
  onCancel: (turnId: string) => void
  onRetry: (turnId: string) => void
  onPickStarter: (seed: string) => void
}

const dateFormatter = new Intl.DateTimeFormat('ko-KR', {
  year: 'numeric',
  month: 'long',
  day: 'numeric',
  weekday: 'long',
})

const timeFormatter = new Intl.DateTimeFormat('ko-KR', {
  hour: 'numeric',
  minute: '2-digit',
  hour12: true,
})

function messageDate(createdAt: string | null) {
  if (!createdAt) return { key: 'legacy', label: '이전 대화' }
  const date = new Date(createdAt)
  if (Number.isNaN(date.getTime())) return { key: 'legacy', label: '이전 대화' }
  return {
    key: `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`,
    label: dateFormatter.format(date),
  }
}

function messageTime(createdAt: string | null) {
  if (!createdAt) return null
  const date = new Date(createdAt)
  return Number.isNaN(date.getTime()) ? null : timeFormatter.format(date)
}

export function ChatLog({
  turns,
  isBusy,
  composer,
  onRevealDone,
  onCancel,
  onRetry,
  onPickStarter,
}: ChatLogProps) {
  const dates = turns.reduce<ReturnType<typeof messageDate>[]>((found, turn) => {
    const previous = found[found.length - 1]
    const date =
      turn.createdAt || turn.state === 'done' || !previous ? messageDate(turn.createdAt) : previous
    found.push(date)
    return found
  }, [])

  return (
    <ChatLayout composer={composer}>
      <ChatMessageList isStreaming={isBusy} emptyState={<Greeting onPickStarter={onPickStarter} />}>
        {turns.map((turn, index) => {
          const date = dates[index] ?? messageDate(null)
          const previousDate = index > 0 ? dates[index - 1] : null
          const time = messageTime(turn.createdAt)
          return (
            <Fragment key={turn.id}>
              {date.key !== previousDate?.key && (
                <div className="chat-date-divider" role="separator" aria-label={date.label}>
                  <span>{date.label}</span>
                </div>
              )}
              {turn.role === 'user' ? (
                <ChatMessage sender="user">
                  <div className="user-turn">
                    <ChatMessageBubble>
                      <span className="message-text">{turn.text}</span>
                    </ChatMessageBubble>
                    {time && (
                      <time className="message-time" dateTime={turn.createdAt ?? undefined}>
                        {time}
                      </time>
                    )}
                  </div>
                </ChatMessage>
              ) : (
                <ChatMessage sender="assistant">
                  <div className="assistant-turn">
                    {/* 연속된 답변에는 아바타를 한 번만. 매번 붙이면 목록이 시끄러움 */}
                    {turns[index - 1]?.role === 'assistant' ? (
                      <span className="assistant-avatar-gap" aria-hidden="true" />
                    ) : (
                      <Symbol size={30} isDecorative />
                    )}
                    <div className="assistant-body">
                      {turns[index - 1]?.role !== 'assistant' && (
                        <span className="assistant-name">{ASSISTANT_NAME}</span>
                      )}
                      <StepIndicator
                        turn={turn}
                        onRevealDone={onRevealDone}
                        onCancel={onCancel}
                        onRetry={onRetry}
                      />
                      {time && (
                        <time className="message-time" dateTime={turn.createdAt ?? undefined}>
                          {time}
                        </time>
                      )}
                    </div>
                  </div>
                </ChatMessage>
              )}
            </Fragment>
          )
        })}
      </ChatMessageList>
    </ChatLayout>
  )
}
