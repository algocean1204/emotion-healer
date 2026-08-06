import { useEffect, useState } from 'react'
import { Selector } from '@astryxdesign/core/Selector'
import { Text } from '@astryxdesign/core/Text'
import { fetchSettings, saveSettings, type ModelOption } from '../api/client'
import { SAVE_INDICATOR_CLEAR_MS } from '../constants'

type SaveState = '' | 'saving' | 'saved' | 'failed'

const SAVE_LABEL: Record<SaveState, string> = {
  '': '',
  saving: '저장 중',
  saved: '저장됨',
  failed: '실패',
}

// 모델·추론 강도. 대부분은 건드릴 일이 없어 더보기 시트 안에만 둠
export function SettingsSection() {
  const [models, setModels] = useState<ModelOption[] | null>(null)
  const [model, setModel] = useState('')
  const [effort, setEffort] = useState('')
  const [saveState, setSaveState] = useState<SaveState>('')

  useEffect(() => {
    let cancelled = false
    fetchSettings()
      .then((settings) => {
        if (cancelled) return
        setModels(settings.models)
        setModel(settings.current.model)
        setEffort(settings.current.effort)
      })
      .catch(() => {
        if (!cancelled) setSaveState('failed')
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (saveState === '' || saveState === 'saving') return
    const timer = window.setTimeout(() => setSaveState(''), SAVE_INDICATOR_CLEAR_MS)
    return () => window.clearTimeout(timer)
  }, [saveState])

  const persist = async (nextModel: string, nextEffort: string) => {
    setSaveState('saving')
    try {
      await saveSettings(nextModel, nextEffort)
      setSaveState('saved')
    } catch {
      setSaveState('failed')
    }
  }

  const handleModelChange = (nextModel: string) => {
    setModel(nextModel)
    const nextModelData = models?.find((candidate) => candidate.slug === nextModel)
    const nextEffort = nextModelData?.efforts.includes(effort)
      ? effort
      : (nextModelData?.default_effort ?? '')
    setEffort(nextEffort)
    void persist(nextModel, nextEffort)
  }

  const handleEffortChange = (nextEffort: string) => {
    setEffort(nextEffort)
    void persist(model, nextEffort)
  }

  const effortOptions = models?.find((candidate) => candidate.slug === model)?.efforts ?? []

  return (
    <div className="sheet-section">
      <div className="sheet-section-head">
        <Text type="label">응답 설정</Text>
        <span aria-live="polite">
          <Text type="supporting" color="secondary">
            {SAVE_LABEL[saveState]}
          </Text>
        </span>
      </div>
      <Text type="supporting" color="secondary">
        답이 어떤 모델로 얼마나 오래 생각하고 나올지 정합니다. 그대로 둬도 됩니다.
      </Text>
      <div className="sheet-controls">
        <Selector
          label="모델"
          size="sm"
          isDisabled={!models}
          options={(models ?? []).map((candidate) => ({
            value: candidate.slug,
            label: candidate.name,
          }))}
          value={model}
          onChange={handleModelChange}
        />
        <Selector
          label="생각 깊이"
          size="sm"
          isDisabled={!models}
          options={effortOptions}
          value={effort}
          onChange={handleEffortChange}
        />
      </div>
    </div>
  )
}
