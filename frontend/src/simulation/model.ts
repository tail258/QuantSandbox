import {t} from '../i18n';
import type {Row} from '../api';

export const kindName:Row={backtest:'基线回测',branch:'历史分叉',pressure:'压力实验',parameter:'参数敏感性',walk_forward:'滚动样本外'};
export const statusName:Row={queued:'排队中',running:'计算中',completed:'已完成',failed:'失败',cancelled:'已取消'};
export const defaultConfig:Row={name:'双均线 · 基线研究',tickers:['000858','600036'],start_date:'2024-01-01',end_date:'2025-12-31',source:'demo',strategy:{name:'dual_ma',parameters:{fast_period:5,slow_period:20}},account:{initial_cash:1000000,commission_rate:.0003,tax_rate:.0005,min_commission:5,slippage_bps:5,position_size:.3}};
export const cloneConfig=(config:Row)=>JSON.parse(JSON.stringify(config)) as Row;
export const parseTickers=(value:string)=>value.split(/[,，\s]+/).filter(Boolean);
export const queryRun=()=>new URLSearchParams(location.hash.split('?')[1]||'').get('run')||'';
export const isSimulation=(run:Row|null)=>!!run&&['backtest','branch'].includes(run.kind);

export function initialDraft(catalog:Row|null,project:Row|null,quoteSets:Row[]){
 const config=cloneConfig(catalog?.defaults||defaultConfig);
 let snapshots:string[]=[];
 if(project?.symbols?.length){
  config.name=project.name+' · 基线研究';config.tickers=[...project.symbols];
  const chosen=project.symbols.map((symbol:string)=>quoteSets.filter(s=>s.symbol===symbol).sort((a,b)=>String(b.fetched_at).localeCompare(String(a.fetched_at)))[0]);
  if(chosen.every(Boolean)){
   snapshots=chosen.map((s:Row)=>s.id);config.source='snapshot';
   config.start_date=chosen.map((s:Row)=>s.start).sort().at(-1);
   config.end_date=chosen.map((s:Row)=>s.end).sort()[0];
  }else config.source='akshare';
 }
 return {config,tickers:config.tickers.join(','),snapshots};
}

/** A child belongs to the explicitly active project, or one unambiguous parent owner. */
export function projectForChild(activeProject:Row|null,projects:Row[],runId?:string){
 if(activeProject)return activeProject.id as string;
 const owners=projects.filter(p=>p.links?.some((link:Row)=>link.kind==='simulation'&&link.run_id===runId));
 return owners.length===1?owners[0].id as string:'';
}

export function sourceName(run:Row){
 return run.synthetic?'合成演示行情':run.config.source==='snapshot'?'固定研究快照':'真实行情';
}

export function sampleCaption(run:Row,session?:Row|null){
 if(session)return t("{v0} 个当前可见交易日", {v0:session.result?.series?.length??0});
 if(['queued','running'].includes(run.status))return '样本待计算';
 if(run.status!=='completed')return '未生成结果';
 const result=run.result||{};
 if(run.kind==='pressure')return Array.isArray(result.scenarios)?t("{v0} 组压力情景", {v0:result.scenarios.length}):'情景数量未记录';
 if(run.kind==='parameter')return Array.isArray(result.variants)?t("{v0} 个参数候选", {v0:result.variants.length}):'候选数量未记录';
 return Array.isArray(result.series)?t("{v0} 个{v1}交易日", {v0:result.series.length,v1:t(run.kind==='walk_forward'?'样本外':'账户')}):'样本数量未记录';
}

export function fixedMetric(value:unknown){
 return typeof value==='number'&&Number.isFinite(value)?value.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}):'—';
}

const changeLabels:Record<string,(value:any)=>string>={
 commission_rate:value=>t("佣金率 {v0}%", {v0:(value*100).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:4})}),
 min_commission:value=>t("最低佣金 {v0} 元", {v0:fixedMetric(value)}),
 tax_rate:value=>t("卖出税率 {v0}%", {v0:(value*100).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:4})}),
 slippage_bps:value=>t("双边滑点 {v0} bps", {v0:value}),
 execution_delay:value=>t("执行延迟 {v0} 个交易日", {v0:value}),
 position_size:value=>t("单标的仓位 {v0}%", {v0:fixedMetric(value*100)}),
 initial_cash:value=>t("初始资金 {v0} 元", {v0:fixedMetric(value)}),
 lot_size:value=>t("每手 {v0} 股", {v0:value}),
 t_plus_one:value=>t("T+1 {v0}", {v0:t(value?'开启':'关闭')}),
};

/** Each scenario has a complete caption even when its changed fields differ. */
export function describeChanges(changes:Row){
 const rows=Object.entries(changes||{});
 const known=rows.filter(([key])=>key in changeLabels).map(([key,value])=>changeLabels[key](value));
 if(rows.some(([key])=>!(key in changeLabels)))known.push(t('其他设置详见原始证据'));
 return known.length?known.join(t('；')):t('沿用基线设置');
}

const parameterNames:Row={fast_period:'快线周期',slow_period:'慢线周期',window:'观察周期',std_dev:'标准差倍数',buy_threshold:'买入 RSI 阈值',sell_threshold:'卖出 RSI 阈值',threshold:'动量阈值'};
export const parameterName=(key:string)=>t(parameterNames[key]||'策略参数');
export function parameterValue(key:string,value:number){
 if(['fast_period','slow_period','window'].includes(key))return t("{v0} 个交易日", {v0:value});
 if(key==='threshold')return `${fixedMetric(value*100)}%`;
 return fixedMetric(value);
}
export const describeParameters=(parameters:Row)=>Object.entries(parameters||{}).map(([key,value])=>`${parameterName(key)} ${parameterValue(key,value)}`).join('；');

export function partialMetrics(result:Row,visibleSeries:Row[],trades:Row[],initial:number,full:boolean){
 if(full)return result.metrics||result.baseline||{};
 let peak=initial,drawdown=0;
 for(const row of visibleSeries){peak=Math.max(peak,row.equity);drawdown=Math.min(drawdown,(row.equity/peak-1)*100)}
 return {total_return:((visibleSeries.at(-1)?.equity??initial)/initial-1)*100,max_drawdown:drawdown,trade_count:trades.length};
}
