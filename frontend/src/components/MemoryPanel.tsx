import { useEffect, useState } from 'react'
import { Badge } from '@astryxdesign/core/Badge'
import { Button } from '@astryxdesign/core/Button'
import { EmptyState } from '@astryxdesign/core/EmptyState'
import { Text } from '@astryxdesign/core/Text'
import { VisuallyHidden } from '@astryxdesign/core/VisuallyHidden'
import {
  editMemory,
  fetchMemory,
  quietMemory,
  retractMemory,
  type MemoryNode,
  type MemoryResponse,
} from '../api/client'
import { ASSISTANT_NAME } from '../constants'
import { OntologyGraph } from './OntologyGraph'

const CRISIS_KEEP_NOTE = '위기 상황에서 참고가 될 수 있어 남겨두는 걸 권해요.'

const SLOT_FALLBACK: Record<string, string> = {
  name: '호칭',
  day: '하루',
  people: '곁',
  want: '바람',
  boundary: '경계',
}

function nodeLabel(node: MemoryNode): string {
  return `${node.subject} ${node.predicate} ${node.object}`
}

interface MemoryPanelProps {
  onClose: () => void
}

export function MemoryPanel({ onClose }: MemoryPanelProps) {
  const [memory, setMemory] = useState<MemoryResponse | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)
  const [announcement, setAnnouncement] = useState('')
  const [draft, setDraft] = useState({ subject: '', predicate: '', object: '' })

  useEffect(() => {
    let cancelled = false
    fetchMemory()
      .then((response) => {
        if (!cancelled) setMemory(response)
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const nodes = memory?.nodes ?? []
  const selected = nodes.find((node) => node.id === selectedId) ?? null
  const slotLabels = { ...SLOT_FALLBACK, ...(memory?.slot_labels ?? {}) }

  const select = (node: MemoryNode) => {
    setSelectedId(node.id)
    setEditingId(null)
    setConfirmingId(null)
    setAnnouncement(`${nodeLabel(node)} 기억을 선택했어요.`)
  }

  const beginEdit = (node: MemoryNode) => {
    setEditingId(node.id)
    setConfirmingId(null)
    setDraft({ subject: node.subject, predicate: node.predicate, object: node.object })
  }

  const handleEdit = async (node: MemoryNode) => {
    setPendingId(node.id)
    try {
      const response = await editMemory(node.id, draft)
      setMemory(response)
      setEditingId(null)
      setAnnouncement('기억을 고치고 연결을 다시 정리했어요.')
    } catch {
      setAnnouncement('고치지 못했어요. 기억은 그대로 남아 있어요.')
    } finally {
      setPendingId(null)
    }
  }

  const handleQuiet = async (node: MemoryNode) => {
    setPendingId(node.id)
    try {
      setMemory(await quietMemory(node.id))
      setAnnouncement(`${nodeLabel(node)} 기억을 먼저 꺼내지 않게 바꿨어요.`)
    } catch {
      setAnnouncement('바꾸지 못했어요. 다시 시도해주세요.')
    } finally {
      setPendingId(null)
    }
  }

  const handleRetract = async (node: MemoryNode) => {
    setPendingId(node.id)
    try {
      setMemory(await retractMemory(node.id))
      setSelectedId(null)
      setConfirmingId(null)
      setAnnouncement(`${nodeLabel(node)} 기억을 지웠어요. 남은 연결을 다시 정리했어요.`)
    } catch {
      setAnnouncement('지우지 못했어요. 기억은 그대로 남아 있어요.')
    } finally {
      setPendingId(null)
    }
  }

  return (
    <main className="memory-workspace">
      <header className="memory-workspace-header">
        <button type="button" className="memory-back" onClick={onClose}>← 대화로</button>
        <div>
          <h1>기억 연결</h1>
          <p>{ASSISTANT_NAME}가 기억한 내용과 서로 이어진 대상을 한곳에서 볼 수 있어요.</p>
        </div>
      </header>

      {loadFailed ? (
        <EmptyState
          title="기억을 불러오지 못했어요"
          description="잠시 후 다시 열어보세요."
          isCompact
        />
      ) : memory === null ? (
        <Text type="supporting" color="secondary">불러오는 중</Text>
      ) : nodes.length === 0 ? (
        <EmptyState
          title="아직 기억한 게 없어요"
          description={`${ASSISTANT_NAME}와 몇 마디 나누면 여기에 연결이 생겨요.`}
          isCompact
        />
      ) : (
        <div className="memory-workspace-grid">
          <section className="memory-graph-region" aria-labelledby="memory-graph-title">
            <div className="memory-graph-heading">
              <div>
                <h2 id="memory-graph-title">온톨로지</h2>
                <p>{nodes.length}개의 기억이 {memory.graph.entities.length}개의 대상과 이어져 있어요.</p>
              </div>
              <div className="ontology-slots" aria-label="알고 있는 기본 정보">
                {Object.entries(memory.slots ?? {}).map(([slot, values]) => (
                  <span key={slot} className="ontology-slot-chip">
                    <b>{slotLabels[slot] ?? slot}</b> {values.join(' · ')}
                  </span>
                ))}
              </div>
            </div>
            <OntologyGraph nodes={nodes} selectedId={selectedId} onSelect={select} />
          </section>

          <aside className="memory-inspector" aria-label="선택한 기억 편집">
            {selected ? (
              <>
                <div className="memory-inspector-heading">
                  <span>선택한 기억</span>
                  <h2>{nodeLabel(selected)}</h2>
                  <div className="memory-detail-badges">
                    {selected.slot && (
                      <Badge
                        variant="info"
                        label={slotLabels[selected.slot] ?? selected.slot}
                      />
                    )}
                    <Badge
                      variant={selected.disclosure === 'proactive' ? 'info' : 'neutral'}
                      label={selected.disclosure === 'proactive' ? '먼저 꺼낼 수 있음' : '먼저 꺼내지 않음'}
                    />
                  </div>
                </div>

                {editingId === selected.id ? (
                  <form
                    className="memory-edit-form"
                    onSubmit={(event) => {
                      event.preventDefault()
                      void handleEdit(selected)
                    }}
                  >
                    <label>
                      대상
                      <input
                        value={draft.subject}
                        maxLength={160}
                        required
                        onChange={(event) => setDraft((current) => ({ ...current, subject: event.target.value }))}
                      />
                    </label>
                    <label>
                      관계
                      <input
                        value={draft.predicate}
                        maxLength={160}
                        required
                        onChange={(event) => setDraft((current) => ({ ...current, predicate: event.target.value }))}
                      />
                    </label>
                    <label>
                      내용
                      <textarea
                        value={draft.object}
                        maxLength={160}
                        required
                        rows={3}
                        onChange={(event) => setDraft((current) => ({ ...current, object: event.target.value }))}
                      />
                    </label>
                    <div className="memory-detail-actions">
                      <Button label="취소" variant="secondary" size="sm" onClick={() => setEditingId(null)} />
                      <Button
                        label={pendingId === selected.id ? '저장하는 중' : '수정 저장'}
                        variant="primary"
                        size="sm"
                        isDisabled={pendingId === selected.id}
                        type="submit"
                      />
                    </div>
                  </form>
                ) : confirmingId === selected.id ? (
                  <div className="memory-confirm" role="alert">
                    <Text type="supporting" color="secondary">
                      정말 지울까요? 되돌릴 수 없어요. {selected.crisis ? CRISIS_KEEP_NOTE : ''}
                    </Text>
                    <div className="memory-detail-actions">
                      <Button label="취소" variant="secondary" size="sm" onClick={() => setConfirmingId(null)} />
                      <Button
                        label={pendingId === selected.id ? '지우는 중' : '기억 지우기'}
                        variant="destructive"
                        size="sm"
                        isDisabled={pendingId === selected.id}
                        clickAction={() => handleRetract(selected)}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="memory-detail-actions">
                    <Button label="수정" variant="secondary" size="sm" onClick={() => beginEdit(selected)} />
                    {selected.disclosure === 'proactive' && (
                      <Button
                        label="먼저 꺼내지 않기"
                        variant="secondary"
                        size="sm"
                        isDisabled={pendingId === selected.id}
                        clickAction={() => handleQuiet(selected)}
                      />
                    )}
                    <Button label="기억 지우기" variant="destructive" size="sm" onClick={() => setConfirmingId(selected.id)} />
                  </div>
                )}
              </>
            ) : (
              <div className="memory-inspector-empty">
                <h2>기억을 선택하세요</h2>
                <p>가운데 기억 노드를 누르면 전체 문장과 수정·삭제 도구가 여기에 열려요.</p>
              </div>
            )}
            {announcement && <p className="memory-feedback">{announcement}</p>}
          </aside>
        </div>
      )}
      <VisuallyHidden as="div" aria-live="polite">{announcement}</VisuallyHidden>
    </main>
  )
}
