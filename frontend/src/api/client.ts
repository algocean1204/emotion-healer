// 서버와 주고받는 모든 fetch와 응답 타입은 여기 한 곳에서만 정의함

export interface ModelOption {
  slug: string
  name: string
  efforts: string[]
  default_effort: string
}

export interface SettingsResponse {
  current: { model: string; effort: string }
  models: ModelOption[]
}

export type ChatJobResult =
  | { status: 'running'; step: string | null; notice?: string | null }
  | { status: 'done'; text: string }
  | { status: 'error'; error: string }

export type OpeningStart =
  | { needed: false }
  | { needed: true; job_id: string; accepted: boolean }

export interface MemoryNode {
  id: string
  subject: string
  predicate: string
  object: string
  disclosure: 'quiet' | 'proactive'
  crisis: boolean
  status?: string
  slot?: string | null
}

export interface MemoryGraph {
  entities: { id: string; label: string }[]
  statements: MemoryNode[]
}

export interface MemoryResponse {
  nodes: MemoryNode[]
  graph: MemoryGraph
  slots: Record<string, string[]>
  slot_labels: Record<string, string>
}

async function readErrorDetail(res: Response): Promise<string> {
  const body = await res.json().catch(() => null)
  return body?.detail ?? `요청이 실패했어요 (${res.status})`
}

export async function fetchSettings(): Promise<SettingsResponse> {
  const res = await fetch('/api/settings')
  if (!res.ok) throw new Error(await readErrorDetail(res))
  return res.json()
}

export async function saveSettings(
  model: string,
  effort: string,
): Promise<{ model: string; effort: string }> {
  const res = await fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, effort }),
  })
  if (!res.ok) throw new Error(await readErrorDetail(res))
  return res.json()
}

export async function startChat(
  message: string,
): Promise<{ job_id: string; accepted: boolean }> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
  if (!res.ok) throw new Error(await readErrorDetail(res))
  const body = await res.json()
  // 옛 서버는 accepted 가 없을 수 있음. 없으면 새로 받은 것으로 봄
  return { job_id: body.job_id, accepted: body.accepted !== false }
}

export async function startOpening(timezone: string): Promise<OpeningStart> {
  const res = await fetch('/api/conversation/opening', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ timezone }),
  })
  if (!res.ok) throw new Error(await readErrorDetail(res))
  const body = await res.json()
  if (!body.needed) return { needed: false }
  return { needed: true, job_id: body.job_id, accepted: body.accepted !== false }
}

// --- 인증 --------------------------------------------------------------
// 토큰은 HttpOnly 쿠키라 JS 가 만지지 않음. 여기서는 로그인 여부만 앎

export async function whoAmI(): Promise<string | null> {
  const res = await fetch('/api/auth/me')
  if (!res.ok) return null
  return (await res.json()).user_id
}

async function submitCredentials(
  path: 'login' | 'register',
  userId: string,
  password: string,
  code: string,
): Promise<string> {
  const res = await fetch(`/api/auth/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, password, code }),
  })
  if (!res.ok) throw new Error(await readErrorDetail(res))
  return (await res.json()).user_id
}

export const login = (userId: string, password: string, code: string) =>
  submitCredentials('login', userId, password, code)
export const register = (userId: string, password: string, code: string) =>
  submitCredentials('register', userId, password, code)

export async function logout(): Promise<void> {
  await fetch('/api/auth/logout', { method: 'POST' }).catch(() => undefined)
}

// --- 하나의 영구 채팅방 -------------------------------------------------

export async function fetchConversationId(): Promise<string> {
  const res = await fetch('/api/conversation')
  if (!res.ok) throw new Error(await readErrorDetail(res))
  return (await res.json()).conversation_id
}

export async function fetchSessionMessages(
  _sessionId: string,
): Promise<{ role: string; text: string; created_at: string | null }[]> {
  const res = await fetch('/api/conversation?limit=500')
  if (!res.ok) throw new Error(await readErrorDetail(res))
  return (await res.json()).messages
}

// 서버 잡까지 실제로 멈춤. 안 그러면 다음 메시지가 중복 방지에 걸려 버려짐
export async function cancelChat(jobId: string): Promise<void> {
  await fetch(`/api/chat/${jobId}/cancel`, { method: 'POST' }).catch(() => undefined)
}

// 모르는 job_id(404)도 폴링을 멈출 수 있게 error 결과로 접어서 돌려줌
export async function fetchChatJob(jobId: string): Promise<ChatJobResult> {
  const res = await fetch(`/api/chat/${jobId}`)
  if (res.status === 404) {
    return { status: 'error', error: '이어서 받을 답변을 찾지 못했어요. 다시 보내주세요.' }
  }
  // 프록시가 잠깐 응답을 못 받아도 서버 잡은 계속 실행. App의 연속 실패 재시도에 맡김
  if ([502, 503, 504].includes(res.status)) {
    throw new Error(`temporary gateway error: ${res.status}`)
  }
  if (!res.ok) {
    return { status: 'error', error: await readErrorDetail(res) }
  }
  return res.json()
}

export async function fetchMemory(): Promise<MemoryResponse> {
  const res = await fetch('/api/memory')
  if (!res.ok) throw new Error(await readErrorDetail(res))
  return res.json()
}

async function postMemoryAction(
  nodeId: string,
  action: 'retract' | 'quiet' | 'edit',
  body?: object,
): Promise<MemoryResponse> {
  const res = await fetch(`/api/memory/${encodeURIComponent(nodeId)}/${action}`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(await readErrorDetail(res))
  return res.json()
}

export const retractMemory = (nodeId: string) => postMemoryAction(nodeId, 'retract')
export const quietMemory = (nodeId: string) => postMemoryAction(nodeId, 'quiet')
export const editMemory = (
  nodeId: string,
  memory: Pick<MemoryNode, 'subject' | 'predicate' | 'object'>,
) => postMemoryAction(nodeId, 'edit', memory)
