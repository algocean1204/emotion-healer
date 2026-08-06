import { useState, type FormEvent } from 'react'
import { Button } from '@astryxdesign/core/Button'
import { Banner } from '@astryxdesign/core/Banner'
import { Text } from '@astryxdesign/core/Text'
import { login, register } from '../api/client'
import { Symbol } from './Symbol'
import { ASSISTANT_NAME, SERVICE_NAME } from '../constants'

// 지인 테스트용 최소 인증. 인증코드는 언제나 물어봄
export function LoginGate({ onSignedIn }: { onSignedIn: (userId: string) => void }) {
  const [isNewAccount, setIsNewAccount] = useState(false)
  const [userId, setUserId] = useState('')
  const [password, setPassword] = useState('')
  const [isPasswordShown, setIsPasswordShown] = useState(false)
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [isBusy, setIsBusy] = useState(false)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setIsBusy(true)
    try {
      const signIn = isNewAccount ? register : login
      onSignedIn(await signIn(userId.trim(), password, code.trim()))
    } catch (err) {
      setError(err instanceof Error ? err.message : '들어가지 못했어요.')
    } finally {
      setIsBusy(false)
    }
  }

  return (
    <form className="login-gate" onSubmit={handleSubmit}>
      <div className="login-hero">
        <Symbol size={168} isDecorative />
      </div>

      <div className="login-copy">
        <Text type="display-3" textWrap="balance">
          {SERVICE_NAME}
        </Text>
        <Text type="body" color="secondary" textWrap="pretty">
          {isNewAccount
            ? `${ASSISTANT_NAME}와 처음 만나시네요. 아이디만 정하면 바로 시작해요.`
            : `${ASSISTANT_NAME}가 기다리고 있었어요.`}
        </Text>
      </div>

      {error && <Banner status="error" title={error} />}

      <label className="login-field">
        <span className="login-label">
          <Text type="label">아이디</Text>
          {isNewAccount && (
            <Text type="supporting" color="secondary">
              영문 소문자·숫자 3~20자
            </Text>
          )}
        </span>
        <input
          className="login-input"
          aria-label="아이디"
          value={userId}
          onChange={(event) => setUserId(event.target.value)}
          autoComplete="username"
          autoCapitalize="none"
          required
        />
      </label>

      <label className="login-field">
        <span className="login-label">
          <Text type="label">비밀번호</Text>
          <button
            type="button"
            className="login-reveal"
            onClick={() => setIsPasswordShown(!isPasswordShown)}
          >
            {isPasswordShown ? '숨기기' : '보기'}
          </button>
        </span>
        <input
          className="login-input"
          aria-label="비밀번호"
          type={isPasswordShown ? 'text' : 'password'}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete={isNewAccount ? 'new-password' : 'current-password'}
          required
        />
      </label>

      <label className="login-field">
        <span className="login-label">
          <Text type="label">인증코드</Text>
        </span>
        <input
          className="login-input"
          aria-label="인증코드"
          inputMode="numeric"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          required
        />
        <Text type="supporting" color="secondary">
          아는 사람만 들어오도록 둔 4자리 숫자예요. 초대해준 사람에게 받으세요.
        </Text>
      </label>

      <Button
        label={isNewAccount ? '시작하기' : '들어가기'}
        type="submit"
        variant="primary"
        width="100%"
        isDisabled={isBusy}
        isLoading={isBusy}
      />
      <Button
        label={isNewAccount ? '이미 계정이 있어요' : '계정 만들기'}
        variant="ghost"
        size="sm"
        width="100%"
        onClick={() => {
          setIsNewAccount(!isNewAccount)
          setError('')
        }}
      />
    </form>
  )
}
