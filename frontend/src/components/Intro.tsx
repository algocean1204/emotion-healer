import { useState } from 'react'
import { Button } from '@astryxdesign/core/Button'
import { Text } from '@astryxdesign/core/Text'
import { Symbol } from './Symbol'
import { ASSISTANT_NAME, SERVICE_NAME } from '../constants'

// 감정 기록을 다루니 "기억이 남는다"와 "지울 수 있다"는 쓰기 전에 알려야 함
const SLIDES = [
  {
    title: `${ASSISTANT_NAME}예요`,
    body: '정리되지 않은 채로 적어도 괜찮아요. 무슨 마음인지 같이 풀어보고, 지금 필요한 게 위로인지 방법인지 제가 판단해서 답할게요.',
  },
  {
    title: '나눈 얘기를 기억해요',
    body: '다음에 다시 왔을 때 처음부터 설명하지 않아도 되도록, 중요한 것만 골라 남겨둡니다. 대화 전체를 통째로 들고 있지는 않아요.',
  },
  {
    title: '기억은 언제든 지울 수 있어요',
    body: '무엇을 기억했는지 목록으로 볼 수 있고, 마음에 걸리는 건 지우거나 먼저 꺼내지 않게 잠글 수 있어요. 오른쪽 위 ⋯ 에 있습니다.',
  },
]

export function Intro({ onDone }: { onDone: () => void }) {
  const [index, setIndex] = useState(0)
  const slide = SLIDES[index]
  const isLast = index === SLIDES.length - 1

  return (
    <section className="intro" aria-label={`${SERVICE_NAME} 안내`}>
      <div className="intro-art">
        <Symbol size={132} isDecorative />
      </div>

      {/* 슬라이드마다 다시 마운트해서 교차 페이드가 걸리게 함 */}
      <div className="intro-copy" key={index}>
        <Text type="display-3" textWrap="balance">
          {slide.title}
        </Text>
        <Text type="body" color="secondary" textWrap="pretty">
          {slide.body}
        </Text>
      </div>

      <div className="intro-dots" aria-hidden="true">
        {SLIDES.map((item, dot) => (
          <span key={item.title} className={dot === index ? 'intro-dot is-on' : 'intro-dot'} />
        ))}
      </div>

      <div className="intro-actions">
        <Button
          label={isLast ? '시작하기' : '다음'}
          variant="primary"
          width="100%"
          onClick={() => (isLast ? onDone() : setIndex(index + 1))}
        />
        {!isLast && <Button label="건너뛰기" variant="ghost" size="sm" onClick={onDone} />}
      </div>

      <Text type="supporting" color="secondary">
        {`${index + 1} / ${SLIDES.length}`}
      </Text>
    </section>
  )
}
