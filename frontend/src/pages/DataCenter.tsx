import { t, useLocale } from '../i18n'
import { useEffect, useMemo, useState } from 'react'
import { Upload, ArrowUpRight, Database, Download, Search } from 'lucide-react'
import type { PageProps } from '../App'
import { api, today, fmt, download, type Row } from '../api'
import { Panel, Note, Chart, RawTable, Source, Research, LoadingButton, Empty } from '../components'
import { useProject } from '../workspace/ProjectContext'
import Dialog from '../workspace/Dialog'
const kindLabels: Row = {
  quotes: '股票行情与估值',
  finance: '财务报表',
  rubber: '期货行情',
  import: '导入序列',
  announcements: '公司公告',
  holders: '股东户数',
  etf_dashboard: 'ETF资金分析',
  etf_evidence: '原文持仓证据',
  national_dashboard: '资金足迹',
  verification: '交叉核验',
  closing_snapshot: '盘后快照',
}
export default function DataCenter({ status, reload }: PageProps) {
  useLocale()
  const { activeProject } = useProject()
  const [kind, setKind] = useState('quotes')
  const [symbol, setSymbol] = useState(activeProject?.symbols[0] || '600519')
  const [start, setStart] = useState('2023-01-01')
  const [end, setEnd] = useState(today)
  const [adjust, setAdjust] = useState('3')
  const [force, setForce] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [result, setResult] = useState<Row | null>(null)
  const [showFetch, setShowFetch] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [text, setText] = useState('')
  const [meta, setMeta] = useState<Row>({
    name: '',
    symbol: 'rubber_spot',
    unit: '元/吨',
    source: '',
    source_url: '',
    method: '',
  })
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const [projectOnly, setProjectOnly] = useState(!!activeProject)
  useEffect(() => {
    const first = activeProject?.symbols[0]
    if (first) setSymbol(first)
    setProjectOnly(!!activeProject)
    setResult(null)
  }, [activeProject?.id])
  async function fetchData() {
    setBusy(true)
    setMessage('')
    try {
      const next = await api('/fetch', { kind, symbol, start, end, adjust, force })
      setResult(next)
      setMessage(next.warning || next.cache_status)
      await reload()
      setShowFetch(false)
    } catch (e: any) {
      setMessage(e.message)
    } finally {
      setBusy(false)
    }
  }
  async function importData() {
    setBusy(true)
    setMessage('')
    try {
      const next = await api('/import', { text, meta })
      setResult(next)
      await reload()
      setMessage('已导入，来源与可用日期随快照保存。')
      setShowImport(false)
    } catch (e: any) {
      setMessage(e.message)
    } finally {
      setBusy(false)
    }
  }
  const datasets = useMemo(
    () =>
      status.datasets.filter(
        (s: Row) =>
          (!projectOnly || !activeProject || activeProject.symbols.includes(s.symbol)) &&
          (filter === 'all' || s.kind === filter) &&
          (!search ||
            (s.name + ' ' + s.symbol + ' ' + s.source)
              .toLowerCase()
              .includes(search.toLowerCase())),
      ),
    [status.datasets, projectOnly, activeProject, filter, search],
  )
  return (
    <>
      <div className="page-title">
        <div>
          <h1>{t('数据中心')}</h1>
          <p>{t('先查看已有数据，需要补充时再获取或导入。')}</p>
        </div>
        <div className="actions">
          <button className="secondary" onClick={() => setShowImport(true)}>
            <Upload size={15} />
            {t('导入 CSV')}{' '}
          </button>
          <button onClick={() => setShowFetch(true)}>
            <Download size={15} />
            {t('获取数据')}{' '}
          </button>
        </div>
      </div>
      <div className="data-directory-summary">
        <span>{t('{count} 个本地数据集', { count: status.datasets.length })} </span>
        <span>{t('{count} 条可分析序列', { count: status.series.length })} </span>
        <span>{t('来源、日期与历史快照保留')}</span>
      </div>
      {message && <Note tone={/失败|错误|超时/.test(message) ? 'warn' : 'info'}>{t(message)}</Note>}
      {result && (
        <Panel
          title={
            result.name ||
            (result.symbol ? result.symbol + ' · ' : '') + t(kindLabels[result.kind] || '研究数据')
          }
          action={
            <button className="text-button" onClick={() => setResult(null)}>
              {t('收起预览')}{' '}
            </button>
          }
        >
          {['quotes', 'rubber', 'import'].includes(result.kind) ? (
            <Chart
              rows={result.rows}
              lines={[
                {
                  key: result.kind === 'quotes' ? 'close' : 'value',
                  name: result.name || result.symbol,
                },
              ]}
              unit={result.unit}
            />
          ) : result.kind === 'announcements' ? (
            <div className="announcements">
              {result.rows.length ? (
                result.rows.map((row: Row, i: number) => (
                  <a key={i} href={row['公告链接']} target="_blank" rel="noreferrer">
                    <span>{row['公告标题']}</span>
                    <small>
                      {String(row['公告时间']).slice(0, 10)} <ArrowUpRight size={14} />
                    </small>
                  </a>
                ))
              ) : (
                <Note>{t('接口未返回公告，空返回不证明期间没有公告，请核对巨潮原文。')}</Note>
              )}
            </div>
          ) : (
            <details className="workspace-details">
              <summary>{t('查看数据明细')}</summary>
              <RawTable rows={result.rows?.slice().reverse() || []} />
            </details>
          )}
          <Source s={result} />
        </Panel>
      )}
      <Panel title={t('本地数据目录')}>
        <div className="controls wrap">
          <label className="grow">
            {t('搜索数据')}{' '}
            <input
              aria-label={t('搜索数据集')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('名称、代码或来源')}
            />
          </label>
          <label>
            {t('类型')}{' '}
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="all">{t('全部类型')}</option>
              {Object.entries(kindLabels).map(([key, label]) => (
                <option value={key} key={key}>
                  {t(String(label))}
                </option>
              ))}
            </select>
          </label>
          {activeProject && (
            <label className="checkbox">
              <input
                type="checkbox"
                checked={projectOnly}
                onChange={(e) => setProjectOnly(e.target.checked)}
              />
              {t('仅当前项目证券')}{' '}
            </label>
          )}
        </div>
        {status.loading ? (
          <Empty>{t('正在读取本地数据目录…')}</Empty>
        ) : datasets.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('数据集')}</th>
                  <th>{t('来源')}</th>
                  <th>{t('覆盖区间')}</th>
                  <th>{t('记录数')}</th>
                  <th>{t('获取时间（UTC）')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {datasets.map((s: Row) => (
                  <tr key={s.id}>
                    <td>
                      <Database size={13} /> {s.name || s.symbol}
                      <small>{t(kindLabels[s.kind] || '其他研究数据')}</small>
                    </td>
                    <td>{s.source}</td>
                    <td>
                      {s.start || '—'}
                      <small>
                        {t('至')} {s.end || '—'}
                      </small>
                    </td>
                    <td>{fmt(s.count, 0)}</td>
                    <td>{s.fetched_at?.slice(0, 16).replace('T', ' ') || '—'}</td>
                    <td>
                      <button
                        className="text-button"
                        onClick={() =>
                          api('/snapshot/' + s.id)
                            .then(setResult)
                            .catch((e) => setMessage(e.message))
                        }
                      >
                        {t('查看')} <Search size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>
            {projectOnly
              ? t('当前项目证券没有匹配的数据，可查看全部类型或手动获取。')
              : t('暂无匹配的数据集。')}
          </Empty>
        )}
      </Panel>
      <details className="workspace-details">
        <summary>{t('数据补充与接口说明')}</summary>
        <p>
          {t(
            '同请求缓存通常保留 24 小时，可手动强制刷新。免费来源失败时保留错误与旧缓存，不用零值代替缺失。',
          )}{' '}
        </p>
        <Research topic={`${symbol} ${kind} 数据缺失；需要核实来源、日期与口径`} />
      </details>
      {showFetch && (
        <Dialog title={t('获取公开数据')} onClose={() => setShowFetch(false)}>
          <div className="controls wrap">
            <label>
              {t('数据类型')}{' '}
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                <option value="quotes">{t('A 股日线 / 估值')}</option>
                <option value="finance">{t('三大财务报表')}</option>
                <option value="announcements">{t('公司公告')}</option>
                <option value="rubber">{t('橡胶主力连续')}</option>
                <option value="holders">{t('股东户数')}</option>
              </select>
            </label>
            <label>
              {t('股票代码')}{' '}
              <input
                value={symbol}
                disabled={kind === 'rubber'}
                maxLength={6}
                onChange={(e) => setSymbol(e.target.value)}
              />
            </label>
            <label>
              {t('开始日期')}{' '}
              <input
                type="date"
                value={start}
                onInput={(e) => setStart(e.currentTarget.value)}
                onChange={(e) => setStart(e.target.value)}
              />
            </label>
            <label>
              {t('结束日期')}{' '}
              <input
                type="date"
                value={end}
                onInput={(e) => setEnd(e.currentTarget.value)}
                onChange={(e) => setEnd(e.target.value)}
              />
            </label>
            {kind === 'quotes' && (
              <label>
                {t('价格口径')}{' '}
                <select value={adjust} onChange={(e) => setAdjust(e.target.value)}>
                  <option value="3">{t('不复权')}</option>
                  <option value="2">{t('前复权')}</option>
                  <option value="1">{t('后复权')}</option>
                </select>
              </label>
            )}
          </div>
          <label className="checkbox">
            <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
            {t('强制刷新已有缓存')}{' '}
          </label>
          <p className="muted">
            {t('财报、股东户数获取接口可提供的全部历史。上游访问最长 55 秒，错误将明确显示。')}{' '}
          </p>
          {message && <Note>{t(message)}</Note>}
          <div className="dialog-actions">
            <button className="secondary" onClick={() => setShowFetch(false)}>
              {t('取消')}{' '}
            </button>
            <LoadingButton busy={busy} onClick={fetchData}>
              {t('获取并保存快照')}{' '}
            </LoadingButton>
          </div>
        </Dialog>
      )}
      {showImport && (
        <Dialog title={t('导入有来源的序列')} onClose={() => setShowImport(false)}>
          <Note>
            {t(
              'UTF-8 CSV 必须包含 date,value,available_date。可用日期填写真实发布日期，缺失行请删除，不填零。',
            )}{' '}
          </Note>
          <div className="controls wrap">
            {[
              ['name', t('序列名称')],
              ['symbol', t('唯一标识')],
              ['unit', t('单位')],
              ['source', t('来源名称')],
              ['source_url', t('原文 URL')],
              ['method', t('口径 / 地区 / 品种')],
            ].map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  value={meta[key]}
                  onChange={(e) => setMeta({ ...meta, [key]: e.target.value })}
                />
              </label>
            ))}
          </div>
          <input
            aria-label={t('选择 CSV 文件')}
            type="file"
            accept=".csv"
            onChange={async (e) => {
              const file = e.target.files?.[0]
              if (file) setText(await file.text())
            }}
          />
          <button
            className="text-button"
            onClick={() => download('series-template.csv', 'date,value,available_date\n')}
          >
            {t('下载空白模板')}{' '}
          </button>
          {message && <Note>{t(message)}</Note>}
          <div className="dialog-actions">
            <button className="secondary" onClick={() => setShowImport(false)}>
              {t('取消')}{' '}
            </button>
            <LoadingButton busy={busy} disabled={!text} onClick={importData}>
              {t('验证并导入')}{' '}
            </LoadingButton>
          </div>
        </Dialog>
      )}
    </>
  )
}
