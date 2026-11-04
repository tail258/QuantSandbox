import {useTheme} from './theme';
import {t,useLocale} from './i18n';
import {fmt,pct,type Row} from './api';
import {Empty,Panel,Note} from './components';
const shares=(n:any)=>n==null?'—':fmt(n/1e8)+' 亿份';

export default function NationalTimeline({proof,reports}:{proof:Row;reports:Row[]}){
 useLocale();
 const terminal=useTheme()==='terminal';
 const terminalColors:Record<string,string>={'chart-equity':'#F5C542','chart-benchmark':'#6C7884','chart-grid':'#30363D','chart-text':'#959DA7','chart-tooltip-bg':'#191D21','chart-tooltip-border':'#30363D',bullish:'#E34B4B',bearish:'#31C48D',accent:'#F5C542'};
 const color=(light:string,token:string)=>terminal?`var(--${token}, ${terminalColors[token]})`:light;
 return <Panel title={t("持仓披露时间线")} action={<span className="tag">{t("原文证据")}</span>}>
 <p className="muted">{t("核心主体按明确名称识别汇金投资、汇金资管与证金；其余主体保留分类。合计为已登记的可见持仓，不代表全部账户。")}</p>
 {!proof.periods.length?<Empty>{t("尚未登记已核实持仓。下方可查询线索并登记原文，定期报告目录仍可查看。")}</Empty>:<div className="national-timeline" style={{borderColor:color("#d6e7e7","chart-tooltip-border")}}>{[...proof.periods].reverse().map((p:Row)=><article key={p.report_date}><div className="timeline-dot" style={{background:color("#137d7b","accent"),borderColor:color("#f5f9f9","chart-tooltip-bg")}}/><div className="national-period"><div><b>{p.report_date}</b><small>{t("统计期末 · 已登记记录最晚公告")}{p.publication_date}</small></div><div><strong style={{color:color("#126a70","accent")}}>{shares(p.shares)}</strong><small>{t("已识别核心主体")}{p.core_count} {t("家 · 占比合计")}{p.ratio_pct==null?'—':fmt(p.ratio_pct)+'%'}</small></div></div><div className="table-scroll" style={{borderColor:color("#e6edef","chart-tooltip-border")}}><table><thead><tr><th>{t("持有人")}</th><th>{t("持有份额")}</th><th>{t("占比")}</th><th>{t("较上次记录")}</th><th>{t("公告日 / 原文")}</th></tr></thead><tbody>{p.rows.map((r:Row)=><tr key={r.holder}><td>{r.holder}<small>{r.is_core?t("核心观察主体"):t(r.entity_type)}</small></td><td>{shares(r.shares)}</td><td>{pct(r.ratio_pct==null?null:r.ratio_pct/100)}</td><td className={r.change>0?'up':r.change<0?'down':''}>{r.change==null?t("无上次可比记录"):(r.change>0?'+':'')+shares(r.change)}{r.previous_report_date&&<small>{t("较")}{r.previous_report_date}</small>}</td><td>{r.publication_date}<small><a href={r.source_url} target="_blank" rel="noreferrer">{t("原文 ·")}{r.page||t("未标页码")}</a></small></td></tr>)}</tbody></table></div></article>)}</div>}
 <Note>{t("某主体未出现在下一份前十大名单中，只能记为未披露，不能直接填零或认定清仓。期末持仓变化不定位具体交易日。")}</Note>
 <details><summary>{t("定期报告目录 ·")}{reports.length} {t("条")}</summary><div className="table-scroll"><table><thead><tr><th>{t("统计期末")}</th><th>{t("公告日期")}</th><th>{t("报告")}</th><th>{t("核验进度")}</th></tr></thead><tbody>{reports.slice(0,12).map(r=>{const n=proof.records.filter((x:Row)=>x.report_date===r.report_date).length;return <tr key={r.report_id}><td>{r.report_date}</td><td>{r.publication_date}</td><td><a href={r.source_url} target="_blank" rel="noreferrer">{r.title}</a></td><td>{n?n+t("条原文登记"):t("目录已获取 · 原文待核实")}</td></tr>})}</tbody></table></div><p className="muted">{t("目录日期是数据商公告标签；持仓登记采用原文核对日期。目录更新不代表持仓内容已更新。")}</p></details>
 </Panel>
}
