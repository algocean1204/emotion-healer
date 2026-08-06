import { useMemo } from 'react'
import { Text } from '@astryxdesign/core/Text'
import type { MemoryNode } from '../api/client'

interface OntologyGraphProps {
  nodes: MemoryNode[]
  selectedId: string | null
  onSelect: (node: MemoryNode) => void
}

interface Point {
  x: number
  y: number
}

const WIDTH = 1080
const ENTITY_WIDTH = 176
const ENTITY_HEIGHT = 52
const MEMORY_WIDTH = 304
const MEMORY_HEIGHT = 76
const LEFT_X = 42
const MEMORY_X = (WIDTH - MEMORY_WIDTH) / 2
const RIGHT_X = WIDTH - ENTITY_WIDTH - 42
const TOP = 40
const ROW_GAP = 108

function unique(values: string[]): string[] {
  return [...new Set(values)]
}

/** 노드 수에 따라 세로 공간만 늘림. 같은 데이터는 항상 같은 위치라 재구성도 흔들리지 않음. */
function layout(nodes: MemoryNode[]) {
  const subjects = unique(nodes.map((node) => node.subject))
  const subjectSet = new Set(subjects)
  const objects = unique(nodes.map((node) => node.object).filter((item) => !subjectSet.has(item)))
  const rowCount = Math.max(nodes.length, subjects.length, objects.length, 3)
  const height = TOP * 2 + rowCount * ROW_GAP

  const spread = (labels: string[], x: number) =>
    Object.fromEntries(
      labels.map((label, index) => [
        label,
        {
          x,
          y: ((index + 1) * height) / (labels.length + 1) - ENTITY_HEIGHT / 2,
        },
      ]),
    ) as Record<string, Point>

  const left = spread(subjects, LEFT_X)
  const right = spread(objects, RIGHT_X)
  const entityPositions = { ...right, ...left }
  const statements = Object.fromEntries(
    nodes.map((node, index) => [
      node.id,
      {
        x: MEMORY_X,
        y: TOP + index * ROW_GAP + (ROW_GAP - MEMORY_HEIGHT) / 2,
      },
    ]),
  ) as Record<string, Point>

  return { height, subjects, objects, entityPositions, statements }
}

function edge(
  from: Point,
  to: Point,
  fromWidth: number,
  fromHeight: number,
  toWidth: number,
  toHeight: number,
): string {
  const fromCenter = { x: from.x + fromWidth / 2, y: from.y + fromHeight / 2 }
  const toCenter = { x: to.x + toWidth / 2, y: to.y + toHeight / 2 }
  const goesRight = fromCenter.x < toCenter.x
  const startX = goesRight ? from.x + fromWidth : from.x
  const endX = goesRight ? to.x : to.x + toWidth
  const distance = Math.abs(endX - startX) * 0.48
  return `M ${startX} ${fromCenter.y} C ${startX + (goesRight ? distance : -distance)} ${fromCenter.y}, ${endX + (goesRight ? -distance : distance)} ${toCenter.y}, ${endX} ${toCenter.y}`
}

export function OntologyGraph({ nodes, selectedId, onSelect }: OntologyGraphProps) {
  const graph = useMemo(() => layout(nodes), [nodes])

  if (nodes.length === 0) {
    return (
      <Text type="supporting" color="secondary">
        아직 연결된 기억이 없어요. 대화가 쌓이면 여기에 관계가 그려져요.
      </Text>
    )
  }

  return (
    <section className="ontology-graph" aria-label="기억 온톨로지 그래프">
      <div className="ontology-legend" aria-hidden="true">
        <span><i className="is-entity" />대상</span>
        <span><i className="is-memory" />기억</span>
      </div>
      <div className="ontology-canvas" tabIndex={0} aria-label="가로로 이동할 수 있는 기억 그래프">
        <svg
          className="ontology-svg"
          viewBox={`0 0 ${WIDTH} ${graph.height}`}
          role="img"
          aria-label={`${nodes.length}개의 기억과 연결된 대상`}
        >
          <g className="ontology-edges" aria-hidden="true">
            {nodes.flatMap((node) => {
              const statement = graph.statements[node.id]
              const subject = graph.entityPositions[node.subject]
              const object = graph.entityPositions[node.object]
              const selected = node.id === selectedId ? ' is-selected' : ''
              return [
                <path
                  key={`${node.id}-subject`}
                  className={`ontology-edge${selected}`}
                  d={edge(subject, statement, ENTITY_WIDTH, ENTITY_HEIGHT, MEMORY_WIDTH, MEMORY_HEIGHT)}
                />,
                <path
                  key={`${node.id}-object`}
                  className={`ontology-edge${selected}`}
                  d={edge(statement, object, MEMORY_WIDTH, MEMORY_HEIGHT, ENTITY_WIDTH, ENTITY_HEIGHT)}
                />,
              ]
            })}
          </g>

          {[...graph.subjects, ...graph.objects].map((label) => {
            const point = graph.entityPositions[label]
            return (
              <foreignObject
                key={`entity-${label}`}
                x={point.x}
                y={point.y}
                width={ENTITY_WIDTH}
                height={ENTITY_HEIGHT}
              >
                <div className="ontology-entity-node" title={label}>{label}</div>
              </foreignObject>
            )
          })}

          {nodes.map((node) => {
            const point = graph.statements[node.id]
            const sentence = `${node.subject} ${node.predicate} ${node.object}`
            return (
              <foreignObject
                key={node.id}
                x={point.x}
                y={point.y}
                width={MEMORY_WIDTH}
                height={MEMORY_HEIGHT}
              >
                <button
                  type="button"
                  className={selectedId === node.id ? 'ontology-memory-node is-selected' : 'ontology-memory-node'}
                  aria-pressed={selectedId === node.id}
                  title={sentence}
                  onClick={() => onSelect(node)}
                >
                  <span>{node.predicate}</span>
                  <small>{node.subject} → {node.object}</small>
                </button>
              </foreignObject>
            )
          })}
        </svg>
      </div>
      <Text type="supporting" color="secondary">
        기억 노드를 누르면 전체 문장을 확인하고 고치거나 지울 수 있어요.
      </Text>
    </section>
  )
}
