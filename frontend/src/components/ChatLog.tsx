import type { ReactNode } from 'react'
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

export function ChatLog({
  turns,
  isBusy,
  composer,
  onRevealDone,
  onCancel,
  onRetry,
  onPickStarter,
}: ChatLogProps) {
  return (
    <ChatLayout composer={composer}>
      <ChatMessageList isStreaming={isBusy} emptyState={<Greeting onPickStarter={onPickStarter} />}>
        {turns.map((turn, index) =>
          turn.role === 'user' ? (
            <ChatMessage key={turn.id} sender="user">
              <ChatMessageBubble>
                <span className="message-text">{turn.text}</span>
              </ChatMessageBubble>
            </ChatMessage>
          ) : (
            <ChatMessage key={turn.id} sender="assistant">
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
                </div>
              </div>
            </ChatMessage>
          ),
        )}
      </ChatMessageList>
    </ChatLayout>
  )
}
