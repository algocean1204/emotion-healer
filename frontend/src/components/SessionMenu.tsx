import { useCallback, useEffect, useState } from 'react'
import { Button } from '@astryxdesign/core/Button'
import { Dialog, DialogHeader } from '@astryxdesign/core/Dialog'
import { EmptyState } from '@astryxdesign/core/EmptyState'
import { List, ListItem } from '@astryxdesign/core/List'
import { Text } from '@astryxdesign/core/Text'
import { VisuallyHidden } from '@astryxdesign/core/VisuallyHidden'
import { createSession, deleteSession, fetchSessions, type SessionSummary } from '../api/client'

// 오늘·어제는 시각만. 어젯밤 얘기인지 지난달 얘기인지가 알고 싶은 것임
function whenLabel(isoTime: string): string {
  const made = new Date(isoTime)
  if (Number.isNaN(made.getTime())) return ''
  const days = Math.floor((Date.now() - made.getTime()) / 86_400_000)
  const clock = made.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
  if (days < 1) return `오늘 ${clock}`
  if (days < 2) return `어제 ${clock}`
  return made.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' })
}

interface SessionMenuProps {
  isOpen: boolean
  currentId: string
  onOpenChange: (open: boolean) => void
  onPick: (sessionId: string) => void
}

// 대화 목록과 새 대화. 세션은 사람마다 여러 개고, 기억만 사람을 따라감
export function SessionMenu({ isOpen, currentId, onOpenChange, onPick }: SessionMenuProps) {
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [announcement, setAnnouncement] = useState('')

  const close = (open: boolean) => {
    onOpenChange(open)
    if (!open) setConfirmingId(null)
  }

  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    setSessions(null)
    setLoadFailed(false)
    fetchSessions()
      .then((found) => !cancelled && setSessions(found))
      .catch(() => !cancelled && setLoadFailed(true))
    return () => {
      cancelled = true
    }
  }, [isOpen])

  const handleNew = useCallback(async () => {
    try {
      onPick(await createSession())
      onOpenChange(false)
    } catch {
      setLoadFailed(true)
    }
  }, [onPick, onOpenChange])

  const handleDelete = async (item: SessionSummary) => {
    try {
      await deleteSession(item.session_id)
      setSessions((prev) => prev?.filter((one) => one.session_id !== item.session_id) ?? prev)
      setConfirmingId(null)
      setAnnouncement('대화만 지웠어요. 민수가 기억한 사실은 기억 화면에 그대로 남아 있어요.')
      // 보고 있던 대화를 지웠으면 갈 곳이 없음. 새로 하나 만들어줌
      if (item.session_id === currentId) await handleNew()
    } catch {
      setAnnouncement('지우지 못했어요. 다시 시도해주세요.')
    }
  }

  return (
    <Dialog isOpen={isOpen} onOpenChange={close} width="min(28rem, calc(100vw - 2rem))">
      <DialogHeader title="대화" onOpenChange={close} />
      <Button label="새 대화 시작" variant="primary" width="100%" clickAction={handleNew} />
      {loadFailed ? (
        <EmptyState
          title="목록을 불러오지 못했어요"
          description="잠시 후 다시 열어보세요."
          isCompact
        />
      ) : sessions === null ? (
        <Text type="supporting" color="secondary">
          불러오는 중
        </Text>
      ) : sessions.length === 0 ? (
        <EmptyState
          title="아직 대화가 없어요"
          description="위 버튼으로 첫 대화를 시작해보세요."
          isCompact
        />
      ) : (
        <List hasDividers>
          {sessions.map((item) =>
            confirmingId === item.session_id ? (
              <ListItem
                key={item.session_id}
                label={item.preview || '아직 아무 말도 없는 대화'}
                description={
                  <Text type="supporting" color="secondary">
                    주고받은 말만 지울까요? 민수가 기억한 사실은 남고, 기억 화면에서 따로 지울 수 있어요.
                  </Text>
                }
                endContent={
                  <div className="memory-item-actions">
                    <Button
                      label="취소"
                      variant="secondary"
                      size="sm"
                      onClick={() => setConfirmingId(null)}
                    />
                    <Button
                      label="지우기"
                      variant="destructive"
                      size="sm"
                      clickAction={() => handleDelete(item)}
                    />
                  </div>
                }
              />
            ) : (
              <ListItem
                key={item.session_id}
                label={item.preview || '아직 아무 말도 없는 대화'}
                description={`${whenLabel(item.created_at)} · ${item.turns}번 주고받음`}
                endContent={
                  <div className="memory-item-actions">
                    {item.session_id === currentId ? (
                      <Text type="supporting" color="secondary">
                        보는 중
                      </Text>
                    ) : (
                      <Button
                        label="열기"
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          onPick(item.session_id)
                          onOpenChange(false)
                        }}
                      />
                    )}
                    <Button
                      label="지우기"
                      variant="ghost"
                      size="sm"
                      onClick={() => setConfirmingId(item.session_id)}
                    />
                  </div>
                }
              />
            ),
          )}
        </List>
      )}
      <VisuallyHidden as="div" aria-live="polite">
        {announcement}
      </VisuallyHidden>
    </Dialog>
  )
}
