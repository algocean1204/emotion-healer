import { Button } from '@astryxdesign/core/Button'
import { Dialog, DialogHeader } from '@astryxdesign/core/Dialog'
import { Text } from '@astryxdesign/core/Text'
import { SettingsSection } from './SettingsSection'
import { ASSISTANT_NAME, CRISIS_RESOURCES } from '../constants'

interface MoreMenuProps {
  isOpen: boolean
  userId: string
  onOpenChange: (open: boolean) => void
  onOpenMemory: () => void
  onSignOut: () => void
}

// 자주 안 쓰는 것들을 여기 모음. 헤더에 다 늘어놓으면 좁은 화면에서 줄이 넘침
export function MoreMenu({
  isOpen,
  userId,
  onOpenChange,
  onOpenMemory,
  onSignOut,
}: MoreMenuProps) {
  return (
    <Dialog isOpen={isOpen} onOpenChange={onOpenChange} width="min(28rem, calc(100vw - 2rem))">
      <DialogHeader title="더보기" onOpenChange={onOpenChange} />

      <div className="sheet-section">
        <Text type="label">기억</Text>
        <Text type="supporting" color="secondary">
          {`${ASSISTANT_NAME}가 무엇을 기억하고 있는지 보고, 지우거나 잠글 수 있어요.`}
        </Text>
        <Button
          label="기억 보기"
          variant="secondary"
          width="100%"
          onClick={() => {
            onOpenChange(false)
            onOpenMemory()
          }}
        />
      </div>

      <SettingsSection />

      <div className="sheet-section crisis-resources">
        <Text type="label">도움이 필요할 때</Text>
        <Text type="supporting" color="secondary">
          위급하거나 혼자 버티기 힘들 때는 아래 번호로 바로 연락하세요. 대화와 별도로 항상
          여기에 있습니다.
        </Text>
        <ul className="crisis-list">
          {CRISIS_RESOURCES.map((item) => (
            <li key={item.number}>
              <span className="crisis-name">{item.name}</span>
              <a className="crisis-number" href={`tel:${item.number.replace(/-/g, '')}`}>
                {item.number}
              </a>
              {item.note ? <span className="crisis-note">{item.note}</span> : null}
            </li>
          ))}
        </ul>
      </div>

      <div className="sheet-section">
        <Text type="label">계정</Text>
        <Text type="supporting" color="secondary">
          {`${userId} 로 로그인되어 있어요.`}
        </Text>
        <Button label="나가기" variant="ghost" width="100%" clickAction={onSignOut} />
      </div>
    </Dialog>
  )
}
