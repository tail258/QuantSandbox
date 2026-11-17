import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { fmt } from '../api'
import { t, useLocale } from '../i18n'
import './tracked-factors.css'

export const factorKeys = ['sma20', 'sma60', 'rsi14', 'bollinger20', 'relative_volume20'] as const
export type FactorKey = typeof factorKeys[number]

export type TrackedFactor = {
  key: FactorKey
  value: number | null
  detail?: number | null
  lower?: number | null
  as_of: string
  basis: string
}

type Props = {
  factors: readonly TrackedFactor[]
  savedKeys: readonly FactorKey[]
  onSave: (keys: FactorKey[]) => Promise<void>
  historical?: boolean
  pending?: boolean
  preferenceError?: string
  volumeUnit?: string
}

const copies = {
  en: {
    title: 'Tracked factors', empty: 'No factors selected.', loading: 'Loading saved factors…',
    historical: 'The current factor selection is calculated at this historical cutoff.',
    preferenceError: 'Saved factors could not be loaded.', insufficient: 'Insufficient history', missing: 'Value unavailable',
    edit: 'Edit selection', cancel: 'Cancel edits', select: 'Choose factors for this instrument',
    save: 'Save selection', saving: 'Saving…', saved: 'Selection saved.', saveError: 'Could not save the selection.',
    price: 'CNY', shares: 'shares', units: 'units', middle: 'Middle', upper: 'Upper', lower: 'Lower', mean: 'Prior 20-session mean',
    labels: { sma20: '20-session moving average', sma60: '60-session moving average', rsi14: '14-session RSI',
      bollinger20: '20-session Bollinger Bands', relative_volume20: 'Relative volume (20 sessions)' },
    bases: { raw_unadjusted: 'Unadjusted close', eligible_traded_sessions: 'Eligible traded sessions' },
    methods: { rsi14: 'Simple averages of gains and losses', bollinger20: '±2 population standard deviations' },
  },
  zh: {
    title: '跟踪因子', empty: '还未选择跟踪因子。', loading: '正在读取已保存的因子…',
    historical: '按当前选择，在历史截点重新计算这些因子。',
    preferenceError: '无法读取已保存的因子。', insufficient: '历史样本不足', missing: '暂无可用数值',
    edit: '编辑选择', cancel: '取消编辑', select: '选择这只证券的跟踪因子',
    save: '保存选择', saving: '正在保存…', saved: '选择已保存。', saveError: '无法保存选择。',
    price: '元', shares: '股', units: '份', middle: '中轨', upper: '上轨', lower: '下轨', mean: '此前 20 个交易日均量',
    labels: { sma20: '20 日均线', sma60: '60 日均线', rsi14: '14 日 RSI',
      bollinger20: '20 日布林带', relative_volume20: '相对成交量（20 日）' },
    bases: { raw_unadjusted: '未复权收盘价', eligible_traded_sessions: '有效成交日' },
    methods: { rsi14: '价格涨跌额的简单移动平均', bollinger20: '上下轨为中轨 ±2 个总体标准差' },
  },
}

function FactorValue({ factor, copy, volumeUnit }: {
  factor: TrackedFactor | undefined
  copy: typeof copies.en
  volumeUnit: string
}) {
  if (!factor) return <span className="tracked-factors-muted">{copy.missing}</span>
  if (factor.value === null || !Number.isFinite(factor.value)) return <span className="tracked-factors-muted">{copy.insufficient}</span>

  const { key, value, detail, lower } = factor
  if (key === 'bollinger20') return <div className="tracked-factor-bands">
    <span>{copy.middle} <strong>{fmt(value, 3)}</strong> {copy.price}</span>
    {lower != null && <span>{copy.lower} {fmt(lower, 3)} {copy.price}</span>}
    {detail != null && <span>{copy.upper} {fmt(detail, 3)} {copy.price}</span>}
  </div>

  if (key === 'relative_volume20') return <div>
    <strong>{fmt(value, 2)}×</strong>
    {detail != null && <small>{copy.mean} {fmt(detail, 2)} {volumeUnit}</small>}
  </div>

  return <span><strong>{fmt(value, key === 'rsi14' ? 2 : 3)}</strong>{key !== 'rsi14' && ` ${copy.price}`}</span>
}

export default function TrackedFactors({ factors, savedKeys, onSave, historical = false, pending = false,
  preferenceError, volumeUnit = '' }: Props) {
  const copy = copies[useLocale()]
  const editorId = useId()
  const editButton = useRef<HTMLButtonElement>(null)
  const [draft, setDraft] = useState<FactorKey[] | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const selected = factorKeys.filter(key => savedKeys.includes(key))
  const currentFactors = new Map(factors.map(factor => [factor.key, factor]))
  const canEdit = !historical && !pending && !preferenceError
  const changed = draft !== null && (draft.length !== selected.length || draft.some(key => !selected.includes(key)))
  const unit = volumeUnit === 'shares' || volumeUnit === 'units' ? copy[volumeUnit] : volumeUnit

  useEffect(() => {
    if (saved) editButton.current?.focus()
  }, [saved])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!draft || !changed || !canEdit || saving) return
    setSaving(true)
    setSaveError(null)
    try {
      await onSave(factorKeys.filter(key => draft.includes(key)))
      setDraft(null)
      setSaved(true)
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : '')
      setSaved(false)
    } finally {
      setSaving(false)
    }
  }

  return <details className="tracked-factors">
    <summary>{copy.title}{!pending && !preferenceError && ` (${selected.length})`}</summary>
    {pending && <p className="tracked-factors-muted" role="status">{copy.loading}</p>}
    {preferenceError && <p className="tracked-factors-error" role="alert">{copy.preferenceError} {t(preferenceError)}</p>}
    {historical && !pending && !preferenceError && <p className="tracked-factors-muted">{copy.historical}</p>}
    {!pending && !preferenceError && (selected.length ? <ul className="tracked-factors-list">
      {selected.map(key => {
        const factor = currentFactors.get(key)
        const basis = factor && copy.bases[factor.basis as keyof typeof copy.bases]
        const method = key === 'rsi14' || key === 'bollinger20' ? copy.methods[key] : null
        return <li key={key}>
          <span className="tracked-factor-label"><strong>{copy.labels[key]}</strong>{(basis || method) && <small>{[basis, method].filter(Boolean).join(' · ')}</small>}</span>
          <div className="tracked-factor-value"><FactorValue factor={factor} copy={copy} volumeUnit={unit} /></div>
          {factor && <time dateTime={factor.as_of}>{factor.as_of}</time>}
        </li>
      })}
    </ul> : <p className="tracked-factors-muted">{copy.empty}</p>)}
    {canEdit && <>
      <button ref={editButton} className="secondary tracked-factor-edit" type="button" aria-expanded={draft !== null} aria-controls={editorId}
        disabled={saving} onClick={() => { setDraft(draft ? null : selected); setSaved(false); setSaveError(null) }}>
        {draft ? copy.cancel : copy.edit}
      </button>
      <div id={editorId}>
        {draft && <form className="tracked-factors-editor" onSubmit={submit}>
          <fieldset disabled={saving}>
            <legend>{copy.select}</legend>
            {factorKeys.map(key => <label key={key}>
              <input type="checkbox" checked={draft.includes(key)} onChange={event => {
                const checked = event.target.checked
                setDraft(previous => previous && (checked ? [...previous, key] : previous.filter(item => item !== key)))
              }} />{copy.labels[key]}
            </label>)}
          </fieldset>
          <button type="submit" disabled={!changed || saving}>{saving ? copy.saving : copy.save}</button>
          {saveError !== null && <p className="tracked-factors-error" role="alert">{copy.saveError} {t(saveError)}</p>}
        </form>}
      </div>
      {saved && <p className="tracked-factors-muted" role="status">{copy.saved}</p>}
    </>}
  </details>
}
