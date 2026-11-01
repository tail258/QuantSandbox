import { useEffect, useState } from 'react'
import type { PageProps } from '../App'
import { api, fmt, pct, type Row } from '../api'
import { useProject } from '../workspace/ProjectContext'
import { Panel, Note, Metric, RawTable, Source, Research, LoadingButton } from '../components'
export default function Evidence({ status, reload }: PageProps) {
  const { activeProject } = useProject()
  const [rows, setRows] = useState<Row[]>([]),
    [symbol, setSymbol] = useState(activeProject?.symbols[0] || '600519'),
    [holder, setHolder] = useState<Row | null>(null),
    [busy, setBusy] = useState(false),
    [msg, setMsg] = useState('')
  useEffect(() => {
    Promise.all(
      status.datasets
        .filter((s: Row) => s.kind === 'quotes')
        .map((s: Row) => api('/snapshot/' + s.id)),
    )
      .then((all) =>
        setRows(
          all.map((s) => {
            const r = s.rows.at(-1),
              tail = s.rows.slice(-20),
              avg = (key: string) =>
                tail.reduce((a: number, r: Row) => a + (r[key] ?? 0), 0) / tail.length
            return {
              ...r,
              symbol: s.symbol,
              above20: tail.length === 20 ? r.close > avg('close') : null,
              amountRatio: avg('amount') ? r.amount / avg('amount') : null,
            }
          }),
        ),
      )
      .catch((e) => setMsg(e.message))
  }, [status.datasets.map((s: Row) => s.id).join(',')])
  useEffect(() => {
    if (activeProject?.symbols[0]) setSymbol(activeProject.symbols[0])
    setHolder(null)
  }, [activeProject?.id])
  const date = rows
    .map((r) => r.date)
    .sort()
    .at(-1)
  const same = rows.filter((r) => r.date === date && r.pctChg != null),
    up = same.filter((r) => r.pctChg > 0).length
  return (
    <>
      <div className="page-title">
        <div>
          <h1>筹码与情绪</h1>
          <p>先看可观测的证据，再判断资金行为。</p>
        </div>
        <span className="tag">证据分层</span>
      </div>
      <Note tone="warn">
        下方仅统计本地缓存股票，共 {same.length} 只同日样本，不代表全 A
        股。大单不等于机构，小单不等于散户；价格与成交量不能确认“国家队”。
      </Note>
      <div className="metrics">
        <Metric
          label="样本上涨占比"
          value={same.length ? pct(up / same.length) : '—'}
          sub={`${date || '—'} · n = ${same.length}`}
        />
        <Metric
          label="样本处于 MA20 之上"
          value={same.filter((r) => r.above20 === true).length}
          sub={`有效样本 ${same.filter((r) => r.above20 !== null).length}`}
        />
        <Metric label="可核实的身份" value="公开披露" sub="名称、持仓路径、统计日与公告日" />
        <Metric label="未披露账户" value="未知" sub="不以交易规模代替身份" />
      </div>
      <Panel title="成交热度 · 缓存样本">
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>代码</th>
                <th>行情日期</th>
                <th>涨跌幅</th>
                <th>换手率</th>
                <th>成交额 / 近20日均额</th>
                <th>MA20</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.symbol}>
                  <td>{r.symbol}</td>
                  <td>{r.date}</td>
                  <td className={r.pctChg > 0 ? 'up' : 'down'}>
                    {r.pctChg > 0 ? '+' : ''}
                    {fmt(r.pctChg)}%
                  </td>
                  <td>{fmt(r.turn)}%</td>
                  <td>{fmt(r.amountRatio)} 倍</td>
                  <td>{r.above20 == null ? '不足20日' : r.above20 ? '上方' : '下方'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted">
          均额包含当日；缓存股票是自选样本。初版不计算全市场涨跌停、连板、融资或北向净流入。
        </p>
      </Panel>
      <Panel title="股东结构">
        <div className="controls">
          <label>
            股票代码
            <input value={symbol} maxLength={6} onChange={(e) => setSymbol(e.target.value)} />
          </label>
          <LoadingButton
            busy={busy}
            onClick={async () => {
              setBusy(true)
              try {
                const r = await api('/fetch', { kind: 'holders', symbol })
                setHolder(r)
                setMsg(r.warning || r.cache_status)
                await reload()
              } catch (e: any) {
                setMsg(e.message)
              } finally {
                setBusy(false)
              }
            }}
          >
            查询股东户数
          </LoadingButton>
        </div>
        {msg && <Note>{msg}</Note>}
        {holder && (
          <>
            <RawTable rows={holder.rows} />
            <Source s={holder} />
          </>
        )}
      </Panel>
      <details className="workspace-details">
        <summary>资金身份的识别边界</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>对象</th>
                <th>可以确认的证据</th>
                <th>不能据此确认</th>
                <th>初版处理</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>外资</td>
                <td>披露的境外实体名称 / 持股渠道</td>
                <td>香港结算名义持仓对应单一外资；实时北向净买入</td>
                <td>保留名称与原公告</td>
              </tr>
              <tr>
                <td>散户</td>
                <td>披露中的自然人股东类别</td>
                <td>小单 = 散户；未披露剩余持股 = 散户</td>
                <td>无法确认则未知</td>
              </tr>
              <tr>
                <td>机构</td>
                <td>基金、保险等披露实体；龙虎榜机构席位类别</td>
                <td>从匿名席位识别具体基金</td>
                <td>区分实体与席位</td>
              </tr>
              <tr>
                <td>国家队</td>
                <td>汇金等明确主体的公告与持仓披露</td>
                <td>ETF 放量、尾盘拉升 = 救市买入</td>
                <td>原文核验后记录</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="muted">
          地域、实体类型、持股渠道、特殊身份为不同维度，可以重叠。初版提供证据查询与检索，不自动生成身份结论。
        </p>
      </details>
      <details className="workspace-details">
        <summary>补充资金身份证据的检索任务</summary>
        <Research
          topic={`${symbol} 最新股东、基金/保险/境外主体持仓与汇金相关公开证据。分别记录名称、类型、渠道、统计截止日、公告日、原文页码；区分直接持股与ETF间接敞口，避免重复计算`}
        />
      </details>
    </>
  )
}
