import type {Row} from '../api';
import {fmt} from '../api';
import {Panel,Chart,RawTable,Empty,Note} from '../components';
import {kindName,statusName,fixedMetric,describeChanges,parameterName,parameterValue,describeParameters} from './model';

export default function Results({active,result,runs,blind,onChoose}:{active:Row;result:Row;runs:Row[];blind:boolean;onChoose:(id:string)=>void}){
 const related=runs.filter(r=>r.id===active.id||r.id===active.parent_id||r.parent_id===active.id||active.parent_id&&r.parent_id===active.parent_id);
 return <div className="simulation-results">
 {blind?<Note>盲测期间仅显示当前账户路径，实验汇总与完整历史对照在退出盲测后可见。</Note>:<>
 {active.kind==='pressure'&&<Panel title="压力情景比较"><p className="muted">固定行情，对照各项执行假设变化后的收益与回撤。</p><Chart rows={result.scenarios.map((r:Row)=>({date:r.name,total_return:r.metrics.total_return,drawdown:r.metrics.max_drawdown}))} lines={[{key:'total_return',name:'累计收益 %'},{key:'drawdown',name:'最大回撤 %'}]} unit="%"/><RawTable rows={result.scenarios.map((s:Row)=>({情景:s.name,'累计收益（%）':fixedMetric(s.metrics.total_return),'最大回撤（%）':fixedMetric(s.metrics.max_drawdown),'相对基线收益差（百分点）':fixedMetric(s.delta_return),'总费用（元）':fixedMetric(s.metrics.total_fees),变化设置:describeChanges(s.changes)}))}/><p className="muted">{result.interpretation}</p></Panel>}
 {active.kind==='parameter'&&<Panel title="参数敏感性"><Chart rows={result.variants.map((r:Row)=>({date:String(r.value),total_return:r.metrics.total_return,drawdown:r.metrics.max_drawdown}))} lines={[{key:'total_return',name:'累计收益 %'},{key:'drawdown',name:'最大回撤 %'}]} unit={parameterName(result.parameter)}/><RawTable rows={result.variants.map((v:Row)=>({[parameterName(result.parameter)]:parameterValue(result.parameter,v.value),'累计收益（%）':fixedMetric(v.metrics.total_return),'最大回撤（%）':fixedMetric(v.metrics.max_drawdown),成交次数:fmt(v.metrics.trade_count,0)}))}/><Note>{result.notice}</Note></Panel>}
 {active.kind==='walk_forward'&&<Panel title="滚动样本外结果"><Chart rows={result.series} lines={[{key:'equity',name:'样本外账户权益'}]} unit="元 CNY"/><RawTable rows={result.folds.map((f:Row)=>({窗口:f.fold,训练开始:f.train_start,训练结束:f.train_end,测试开始:f.test_start,测试结束:f.test_end,选定参数:describeParameters(f.selected_strategy.parameters),'测试收益（%）':fixedMetric(f.test_metrics.total_return)}))}/><p className="muted">{result.selection_objective}</p></Panel>}
 <Panel title={active.kind==='branch'?'历史路径对照':'已保存的对照实验'}>{related.length>1?<div className="table-scroll"><table><thead><tr><th>实验</th><th>类型</th><th>状态</th><th>累计收益</th><th>最大回撤</th></tr></thead><tbody>{related.map(run=><tr key={run.id} className={run.id===active.id?'selected-row':''}><td><button className="text-button" onClick={()=>onChoose(run.id)}>{run.name}</button>{run.branch?.fork_date&&<small>{run.branch.fork_date} 收盘后分叉</small>}</td><td>{kindName[run.kind]}</td><td>{statusName[run.status]}</td><td>{fmt(run.metrics?.total_return)}%</td><td>{fmt(run.metrics?.max_drawdown)}%</td></tr>)}</tbody></table></div>:<Empty>尚未创建对照。通过右上角“新建对照”比较同一份行情下的不同选择。</Empty>}</Panel>
 </>}
 </div>;
}
