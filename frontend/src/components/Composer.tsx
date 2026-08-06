import { useEffect, useRef } from 'react'
import { ChatComposer, ChatComposerInput, type ChatComposerInputHandle } from '@astryxdesign/core/Chat'
import { MAX_MESSAGE_CHARS } from '../constants'

interface ComposerProps {
  value: string
  isDisabled: boolean
  onChange: (value: string) => void
  onSubmit: (message: string) => void
}

// 입력값은 App 이 들고 있음. 시작 카드가 넣어주고, 새로고침해도 남아야 하기 때문
export function Composer({ value, isDisabled, onChange, onSubmit }: ComposerProps) {
  const inputHandle = useRef<ChatComposerInputHandle>(null)
  const wasDisabled = useRef(isDisabled)
  const over = value.length > MAX_MESSAGE_CHARS

  useEffect(() => {
    // 응답이 끝나 다시 쓸 수 있게 되면 입력창으로 포커스를 돌려줌
    if (wasDisabled.current && !isDisabled) inputHandle.current?.focus()
    wasDisabled.current = isDisabled
  }, [isDisabled])

  return (
    <div className="composer-wrap">
      <ChatComposer
        value={value}
        onChange={onChange}
        onSubmit={(message) => {
          if (message.length > MAX_MESSAGE_CHARS) return
          onSubmit(message)
        }}
        isDisabled={isDisabled || over}
        placeholder="지금 드는 생각을 적어보세요"
        input={<ChatComposerInput handleRef={inputHandle} label="메시지 입력" />}
      />
      <div className={over ? 'composer-count is-over' : 'composer-count'} aria-live="polite">
        {value.length > 0 || over
          ? `${value.length.toLocaleString('ko-KR')} / ${MAX_MESSAGE_CHARS.toLocaleString('ko-KR')}자`
          : null}
      </div>
    </div>
  )
}
