import { Text } from '@astryxdesign/core/Text'
import { Symbol } from './Symbol'
import { ASSISTANT_NAME, CONVERSATION_STARTERS } from '../constants'

// 빈 화면에서 먼저 말을 건넴. "항목 없음" 대신 시작할 거리를 제시함
export function Greeting({ onPickStarter }: { onPickStarter: (seed: string) => void }) {
  return (
    <div className="greeting">
      <Symbol size={104} isDecorative />
      <Text type="display-3" textWrap="balance">
        {`야, 나 ${ASSISTANT_NAME}야`}
      </Text>
      <Text type="body" color="secondary" textWrap="pretty">
        정리 안 해도 돼. 떠오르는 대로 적어 봐.
      </Text>

      <div className="starters">
        {CONVERSATION_STARTERS.map((starter) => (
          <button
            key={starter.label}
            type="button"
            className="starter"
            onClick={() => onPickStarter(starter.seed)}
          >
            {starter.label}
          </button>
        ))}
      </div>

      <Text type="supporting" color="secondary">
        답장까지 보통 1~2분 걸려
      </Text>
    </div>
  )
}
