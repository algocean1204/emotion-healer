import symbol from '../assets/strong-minsu.webp'
import { ASSISTANT_NAME } from '../constants'

interface SymbolProps {
  size: number
  // 이름이 바로 옆에 이미 적혀 있으면 스크린리더에 두 번 읽히지 않게 함
  isDecorative?: boolean
}

// 상징 이미지가 나오는 곳이 넷이라 경로와 대체 텍스트를 여기 한 곳에 둠
export function Symbol({ size, isDecorative = false }: SymbolProps) {
  return (
    <img
      className="symbol"
      src={symbol}
      width={size}
      height={size}
      alt={isDecorative ? '' : ASSISTANT_NAME}
      draggable={false}
    />
  )
}
