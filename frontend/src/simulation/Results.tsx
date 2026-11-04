import {t,useLocale} from '../i18n';
import type {Row} from '../api';
import {fmt} from '../api';
import {Panel,Chart,RawTable,Empty,Note} from '../components';
import {kindName,statusName,fixedMetric,describeChanges,parameterName,parameterValue,describeParameters} from './model';

export default function Results({active,result,runs,blind,onChoose}:{active:Row;result:Row;runs:Row[];blind:boolean;onChoose:(id:string)=>void}){
 useLocale();
 const related=runs.filter(r=>r.id===active.id||r.id===active.parent_id||r.parent_id===active.id||active.parent_id&&r.parent_id===active.parent_id);
 return <div className="simulation-results">
 {blind?<Note>{t("盲测期间仅显示当前账户路径，实验汇总与完整历史对照在退出盲测后可见。")}</Note>:<>
 {active.kind==='pressure'&&<Panel title={t("压力情景比较")}><p className="muted">{t("固定行情，对照各项执行假设变化后的收益与回撤。")}</p><Chart rows={result.scenarios.map((r:Row)=>({date:t(r.name),total_return:r.metrics.total_return,drawdown:r.metrics.max_drawdown}))} lines={[{key:'total_return',name:t("累计收益 %")},{key:'drawdown',name:t("最大回撤 %")}]} unit="%"/><RawTable rows={result.scenarios.map((s:Row)=>({[t("情景")]: t(s.name),[t("累计收益（%）")]: fixedMetric(s.metrics.total_return),[t("最大回撤（%）")]: fixedMetric(s.metrics.max_drawdown),[t("相对基线收益差（百分点）")]: fixedMetric(s.delta_return),[t("总费用（元）")]: fixedMetric(s.metrics.total_fees),[t("变化设置")]: describeChanges(s.changes)}))}/><p className="muted">{t(result.interpretation||'')}</p></Panel>}
 {active.kind==='parameter'&&<Panel title={t("参数敏感性")}><Chart rows={result.variants.map((r:Row)=>({date:String(r.value),total_return:r.metrics.total_return,drawdown:r.metrics.max_drawdown}))} lines={[{key:'total_return',name:t("累计收益 %")},{key:'drawdown',name:t("最大回撤 %")}]} unit={parameterName(result.parameter)}/><RawTable rows={result.variants.map((v:Row)=>({[parameterName(result.parameter)]:parameterValue(result.parameter,v.value),[t("累计收益（%）")]: fixedMetric(v.metrics.total_return),[t("最大回撤（%）")]: fixedMetric(v.metrics.max_drawdown),[t("成交次数")]: fmt(v.metrics.trade_count,0)}))}/><Note>{t(result.notice||'')}</Note></Panel>}
 {active.kind==='walk_forward'&&<Panel title={t("滚动样本外结果")}><Chart rows={result.series} lines={[{key:'equity',name:t("样本外账户权益")}]} unit={t("元 CNY")}/><RawTable rows={result.folds.map((f:Row)=>({[t("窗口")]: f.fold,[t("训练开始")]: f.train_start,[t("训练结束")]: f.train_end,[t("测试开始")]: f.test_start,[t("测试结束")]: f.test_end,[t("选定参数")]: describeParameters(f.selected_strategy.parameters),[t("测试收益（%）")]: fixedMetric(f.test_metrics.total_return)}))}/><p className="muted">{t(result.selection_objective||'')}</p></Panel>}
 <Panel title={active.kind==='branch'?t("历史路径对照"):t("已保存的对照实验")}>{related.length>1?<div className="table-scroll"><table><thead><tr><th>{t("实验")}</th><th>{t("类型")}</th><th>{t("状态")}</th><th>{t("累计收益")}</th><th>{t("最大回撤")}</th></tr></thead><tbody>{related.map(run=><tr key={run.id} className={run.id===active.id?'selected-row':''}><td><button className="text-button" onClick={()=>onChoose(run.id)}>{run.name}</button>{run.branch?.fork_date&&<small>{run.branch.fork_date}{t("收盘后分叉")}</small>}</td><td>{t(kindName[run.kind])}</td><td>{t(statusName[run.status])}</td><td>{fmt(run.metrics?.total_return)}%</td><td>{fmt(run.metrics?.max_drawdown)}%</td></tr>)}</tbody></table></div>:<Empty>{t("尚未创建对照。通过右上角“新建对照”比较同一份行情下的不同选择。")}</Empty>}</Panel>
 </>}
 </div>;
}
