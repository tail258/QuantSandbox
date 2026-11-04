import { t, useLocale } from '../i18n'
import { useEffect, useState } from 'react'
import { Upload } from 'lucide-react'
import type { PageProps } from '../App'
import { api, fmt, type Row } from '../api'
import { Panel, Note, Metric, Chart, Source, LoadingButton, Research } from '../components'
const variables = [
  ['rubber_spot', '现货价格', '元/吨', '注明地区、胶种与含税口径'],
  ['RU0', '主力期货', '元/吨', '新浪 RU0 主力连续'],
  ['rubber_inventory', '社会库存', '吨 / 万吨', '分清地区与库存类型'],
  ['tire_utilization', '轮胎开工率', '%', '区分全钢胎与半钢胎'],
  ['rubber_production', '天然橡胶产量', '吨 / 万吨', '注明国家、频率与初值/修订值'],
]
export default function Industry({ status, reload, setPage }: PageProps) {
  useLocale()
  const [series, setSeries] = useState<Row[]>([]),
    [days, setDays] = useState('365'),
    [busy, setBusy] = useState(false),
    [msg, setMsg] = useState(''),
    [selected, setSelected] = useState<string[]>(['RU0'])
  const ids = status.series.filter(
    (s: Row) => s.kind === 'rubber' || variables.some((v) => v[0] === s.symbol),
  )
  useEffect(() => {
    Promise.all(ids.map((s: Row) => api('/series/' + s.id)))
      .then(setSeries)
      .catch((e) => setMsg(e.message))
  }, [ids.map((s: Row) => s.id).join(',')])
  const cutoff =
    days === 'all'
      ? '0000'
      : new Date(Date.now() - Number(days) * 86400000).toISOString().slice(0, 10)
  const visible = series.filter((s) => selected.includes(s.symbol))
  const dates = [...new Set<string>(visible.flatMap((s) => s.rows.map((r: Row) => r.date)))]
    .filter((d) => d >= cutoff)
    .sort()
  const rows = dates.map((date) => ({
    date,
    ...Object.fromEntries(
      visible.map((s) => [s.symbol, s.rows.find((r: Row) => r.date === date)?.value ?? null]),
    ),
  }))
  const spot = series.find((s) => s.symbol === 'rubber_spot'),
    future = series.find((s) => s.symbol === 'RU0')
  const common =
    spot && future && spot.unit === future.unit
      ? future.rows.filter((r: Row) => spot.rows.some((v: Row) => v.date === r.date)).at(-1)
      : null
  const spread = common
    ? common.value - spot!.rows.find((v: Row) => v.date === common.date).value
    : null
  return (
    <>
      <div className="page-title">
        <div>
          <h1>{t('橡胶产业周期')}</h1>
          <p>{t('价格、库存与生产的共同观察。')}</p>
        </div>
        <div className="actions">
          <button className="secondary" onClick={() => setPage('data')}>
            <Upload size={16} /> {t('导入 CSV')}{' '}
          </button>
          <LoadingButton
            busy={busy}
            onClick={async () => {
              setBusy(true)
              try {
                const r = await api('/fetch', { kind: 'rubber', force: true })
                setMsg(r.warning || '沪胶日线已更新')
                await reload()
              } catch (e: any) {
                setMsg(e.message)
              } finally {
                setBusy(false)
              }
            }}
          >
            {t('更新数据')}{' '}
          </LoadingButton>
        </div>
      </div>
      <Note tone="warn">
        {t(
          '{count} / 5 项指标已接入。未核实的数据保留缺失；RU0 换月规则由数据商决定，跨换月涨跌不代表同一合约收益。',
          { count: variables.filter(([key]) => series.some((s) => s.symbol === key)).length },
        )}{' '}
      </Note>
      {msg && <Note>{t(msg)}</Note>}
      <div className="metrics">
        {variables.slice(0, 4).map(([key, name, unit]) => {
          const s = series.find((s) => s.symbol === key),
            last = s?.rows.at(-1)
          return (
            <Metric
              key={key}
              label={t(name)}
              value={fmt(last?.value)}
              sub={
                <>
                  {s?.unit || t(unit)}
                  <br />
                  {last ? `${last.date} · ${s?.source}` : t('待接入 · 可导入来源数据')}
                </>
              }
            />
          )
        })}
      </div>
      <div className="grid-main">
        <Panel
          title={t('价格与库存')}
          action={
            <select
              aria-label={t('产业周期时间范围')}
              value={days}
              onChange={(e) => setDays(e.target.value)}
            >
              <option value="180">{t('近 6 个月')}</option>
              <option value="365">{t('近 1 年')}</option>
              <option value="1095">{t('近 3 年')}</option>
              <option value="all">{t('全部')}</option>
            </select>
          }
        >
          <Chart
            rows={rows}
            lines={visible.map((s) => ({ key: s.symbol, name: s.name }))}
            normalize={visible.length > 1}
            unit={visible[0]?.unit}
          />
          <p className="muted">
            {t(
              '选择右侧变量叠加；不同量纲以首个有效值 = 100 比较方向。按观测日期展示，无数据日期不补值。',
            )}{' '}
          </p>
        </Panel>
        <Panel title={t('数据覆盖')}>
          {variables.map(([key, name, unit, detail]) => {
            const s = series.find((s) => s.symbol === key)
            return (
              <div className="coverage" key={key}>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    disabled={!s}
                    checked={!!s && selected.includes(key)}
                    onChange={(e) =>
                      setSelected(
                        e.target.checked ? [...selected, key] : selected.filter((x) => x !== key),
                      )
                    }
                  />
                  <span>
                    {t(name)}
                    <small>{t(detail)}</small>
                  </span>
                </label>
                <span className={'tag ' + (s ? 'good' : '')}>{s ? t('可用') : t('待接入')}</span>
              </div>
            )
          })}
          <small>{t('自定义标识在数据中心导入，来源与口径必填。')}</small>
        </Panel>
      </div>
      <div className="grid-two">
        <Panel title={t('价差观察')}>
          <div className="spread">
            <span>{t('RU 主力 − 现货')}</span>
            <strong>
              {fmt(spread)}
              <small> {t('元/吨')}</small>
            </strong>
          </div>
          <p className="muted">
            {common
              ? t('共同观测日：{date}', { date: common.date })
              : t('需有相同日期、相同单位的现货与期货数据。')}
          </p>
          <Note>
            {t('此为报价差，不自动构成可套利基差；还需核对胶种、交割品质、税费、地区及合约。')}
          </Note>
        </Panel>
        <details className="workspace-details">
          <summary>{t('变量标识与导入口径')}</summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('变量')}</th>
                  <th>{t('标准标识')}</th>
                  <th>{t('频率建议')}</th>
                </tr>
              </thead>
              <tbody>
                {variables.map(([key, name], i) => (
                  <tr key={key}>
                    <td>{t(name)}</td>
                    <td>
                      <code>{key}</code>
                    </td>
                    <td>{i < 2 ? t('日度') : i === 4 ? t('月度') : t('周度')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </div>
      <details className="workspace-details">
        <summary>{t('补充行业数据的检索任务')}</summary>
        <Research topic="天然橡胶现货价格、社会库存、主产国产量、全钢/半钢轮胎开工率。优先协会、统计部门与交易所，记录地区胶种单位和发布日期" />
      </details>
      {series.map((s) => (
        <Source key={s.id} s={s} />
      ))}
    </>
  )
}
