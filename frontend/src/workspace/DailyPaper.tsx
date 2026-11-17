import { useEffect, useState } from 'react'
import { fmt, type Row } from '../api'
import { Note, Panel } from '../components'
import { post, request } from '../http'
import { t, useLocale } from '../i18n'

export default function DailyPaper({ projectId, datasets }: { projectId: string; datasets: Row[] }) {
  useLocale()
  const [record, setRecord] = useState<Row | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const path = `/projects/${projectId}/daily-paper`

  useEffect(() => {
    const controller = new AbortController()
    request<{ records: Row[] }>(path, { signal: controller.signal }).then(({ records }) => {
      const latest = records.reduce<Row | null>((best, item) => !best || item.as_of > best.as_of ? item : best, null)
      if (!controller.signal.aborted) setRecord(latest)
    }).catch((reason) => {
      if (!controller.signal.aborted) setError(reason.message)
    })
    return () => controller.abort()
  }, [path])

  if (!record) return error ? <Note tone="warn">{t(error)}</Note> : null
  const candidate = datasets.find(item => item.symbol === record.symbol && item.end === record.plan.next_session &&
    item.execution_history?.calendar?.next_session)
  const action = record.plan.action === 'buy' ? '买入' : record.plan.action === 'sell' ? '卖出' : '保持现状'

  async function advance() {
    if (!candidate || !record) return
    setBusy(true)
    setError('')
    try {
      setRecord(await post<Row>(`${path}/${record.id}/advance`, { snapshot_id: candidate.id, as_of: candidate.end }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '逐日模拟未能推进。')
    } finally {
      setBusy(false)
    }
  }

  return <Panel title={t('逐日模拟')}>
    <p>{t('双均线 5/20 · 最新计划')}</p>
    <div className="project-summary">
      <span>{t('信号日')} {record.plan.signal_date}</span>
      <span>{t('下一交易日')} {record.plan.next_session}</span>
      <strong>{t(action)}</strong>
    </div>
    <p>{t('快线')} {fmt(record.plan.fast_ma, 3)} · {t('慢线')} {fmt(record.plan.slow_ma, 3)}</p>
    <p>{t('模拟权益（元）')} {fmt(record.receipt?.state.equity ?? record.account.initial_cash, 2)}</p>
    {record.receipt && <p>{t('模拟成交')} {record.receipt.trades.length} · {t('未成交或顺延')} {record.receipt.blocked.length}</p>}
    <small>{t('快照 {id}', { id: record.snapshot_id })}</small>
    {' '}
    <small>{candidate ? t('新日线已导入，可核对并推进一个交易日。') : t('等待下一交易日收盘及核验快照，手动推进。')}</small>
    {candidate && <div className="actions"><button className="secondary" disabled={busy} onClick={advance}>{t('推进逐日模拟')}</button></div>}
    {error && <Note tone="warn">{t(error)}</Note>}
  </Panel>
}
