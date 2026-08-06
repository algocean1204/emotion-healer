// 한 곳에 모아두는 튜닝 값들

// 서비스 이름. 화면에 나오는 모든 곳이 여기를 봄
export const SERVICE_NAME = '내 친구 민수'
export const ASSISTANT_NAME = '스트롱 민수'

// 진행 상태를 물어보는 간격
export const POLL_INTERVAL_MS = 1000

// 완성본을 한 글자씩 흘려 보이는 속도
export const TYPING_CHAR_INTERVAL_MS = 15

// 설정 저장 결과 표시(저장됨/실패)를 지우기까지의 시간
export const SAVE_INDICATOR_CLEAR_MS = 2000

// 네트워크가 잠깐 끊겨도 바로 에러로 접지 않고 봐주는 연속 실패 횟수
export const MAX_CONSECUTIVE_POLL_FAILURES = 3

// 잡이 running에 갇혀도 화면이 영원히 돌지 않도록 두는 상한.
// 실측 최악 경로 152초의 약 두 배로 설정
export const MAX_WAIT_MS = 300_000

// 한 턴 실측 48~152초. 이만큼 지나면 오래 걸린다고 먼저 말함
export const LONG_WAIT_NOTICE_MS = 20_000

// 서버 max_message_chars 와 맞춤. 보내기 전에 알려 주기 위함
export const MAX_MESSAGE_CHARS = 4000

// 새로고침해도 진행 중인 응답과 보던 대화를 이어받기 위한 localStorage 키
export const PENDING_JOB_STORAGE_KEY = 'healer.pendingJob'
export const SESSION_ID_STORAGE_KEY = 'healer.sessionId'
// 쓰다 만 글은 새로고침해도 남김. 감정을 적다 날리면 다시 안 씀
export const DRAFT_STORAGE_KEY = 'healer.draft'
// 인트로는 사람마다 한 번만. 키 뒤에 user_id 를 붙여 씀
export const INTRO_SEEN_STORAGE_KEY = 'healer.introSeen'

// 빈 화면에서 먼저 건네는 말. 누르면 입력창에 들어가고 이어서 쓸 수 있음
export const CONVERSATION_STARTERS = [
  { label: '오늘 있었던 일', seed: '오늘 이런 일이 있었어. ' },
  { label: '요즘 반복되는 생각', seed: '요즘 자꾸 이 생각이 들어. ' },
  { label: '그냥 답답해', seed: '뭐라고 해야 할지 모르겠는데 그냥 답답해. ' },
  { label: '조언이 필요해', seed: '어떻게 하면 좋을지 모르겠어. ' },
]

// 모델이 안내를 빼먹어도 화면에는 항상 있음. 서버 healer_crisis.json 과 같은 번호
export const CRISIS_RESOURCES = [
  { name: '자살예방상담전화', number: '109', note: '24시간' },
  { name: '정신건강위기상담전화', number: '1577-0199', note: '24시간' },
  { name: '여성긴급전화', number: '1366', note: '가정·성폭력 · 24시간' },
  { name: '긴급신고', number: '112', note: '아동학대 등' },
  { name: '청소년 상담', number: '1388', note: '' },
]
