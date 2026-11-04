import {useTheme} from './theme';
import {serializeChart} from './chart-export';
import {t,useLocale} from './i18n';
import {ComposedChart,Line,XAxis,YAxis,Tooltip,CartesianGrid,ResponsiveContainer,Legend,ReferenceLine,Brush} from 'recharts';
import {Download} from 'lucide-react';
import {download,fmt,type Row} from './api';

export default function NationalChart({rows,events=[],mode='shares',onSelect}:{rows:Row[];events?:Row[];mode?:'shares'|'margin';onSelect?:(date:string)=>void}){
 useLocale();
 const terminal=useTheme()==='terminal';
 const terminalColors:Record<string,string>={'chart-equity':'#F5C542','chart-benchmark':'#6C7884','chart-grid':'#30363D','chart-text':'#959DA7','chart-tooltip-bg':'#191D21','chart-tooltip-border':'#30363D',bullish:'#E34B4B',bearish:'#31C48D',accent:'#F5C542'};
 const color=(light:string,token:string)=>terminal?`var(--${token}, ${terminalColors[token]})`:light;
 const margin=mode==='margin';
 const data=rows.map(r=>({...r,shares_yi:r.shares==null?null:r.shares/1e8,etf_balance_yi:r.margin_balance==null?null:r.margin_balance/1e8,component_balance_yi:r.component_balance==null?null:r.component_balance/1e8}));
 const left=margin?'component_balance_yi':'price',right=margin?'etf_balance_yi':'shares_yi';
 return <div className="chart-wrap"><div className="chart-caption"><span>{margin?t("左轴：固定名单成分股融资（亿元） · 右轴：ETF融资（亿元）"):t("左轴：ETF不复权价格（元） · 右轴：总份额（亿份）")}</span><button className="text-button" onClick={e=>{const svg=e.currentTarget.closest('.chart-wrap')?.querySelector('.recharts-wrapper > svg.recharts-surface');if(svg)download('national-'+mode+'.svg',serializeChart(svg),'image/svg+xml')}}><Download size={14}/> {t("导出图表")}</button></div>
 <ResponsiveContainer width="100%" height={340}><ComposedChart data={data} margin={{top:24,right:4,bottom:4,left:4}} onClick={(state:any)=>{if(state?.activeLabel)onSelect?.(String(state.activeLabel))}}><CartesianGrid stroke={color("#edf0f2","chart-grid")} vertical={false}/><XAxis dataKey="date" minTickGap={65} tick={{fontSize:10,fill:color("#666","chart-text")}}/><YAxis yAxisId="left" width={58} tick={{fontSize:10}} tickFormatter={v=>fmt(v,margin?0:2)} domain={['auto','auto']}/><YAxis yAxisId="right" orientation="right" width={58} tick={{fontSize:10}} tickFormatter={v=>fmt(v,0)} domain={['auto','auto']}/><Tooltip contentStyle={{fontSize:12,borderRadius:8,border:`1px solid ${color('#dce5e9','chart-tooltip-border')}`,background:color('white','chart-tooltip-bg'),color:color('#333','chart-text')}} formatter={(v:any)=>fmt(v)}/><Legend wrapperStyle={{fontSize:11}}/>
 <Line yAxisId="left" dataKey={left} name={margin?t("成分股融资余额（左轴）"):t("ETF价格（左轴）")} stroke={color("#6c8ca4","chart-benchmark")} strokeWidth={1.6} dot={false} isAnimationActive={false} connectNulls={false}/><Line yAxisId="right" dataKey={right} name={margin?t("ETF融资余额（右轴）"):t("ETF总份额（右轴）")} stroke={color("#087d79","chart-equity")} strokeWidth={1.8} dot={false} isAnimationActive={false} connectNulls={false}/>
 {!margin&&events.filter(e=>e.plot_date).map((e,i)=><ReferenceLine key={e.report_date} x={e.plot_date} yAxisId="left" stroke={color("#b28b49","accent")} strokeDasharray="4 4" label={{value:t("披露")+e.report_date,position:'insideTopLeft',fontSize:10,fill:color('#9d783b','accent'),dy:i%2*16}}/>)}<Brush dataKey="date" height={22} stroke={color("#a7bdc7","chart-benchmark")} fill={color("#f4f7f8","chart-tooltip-bg")} travellerWidth={8}/></ComposedChart></ResponsiveContainer>
 <p className="muted">{margin?t("两条线使用各自纵轴，只比较变化节奏；每日覆盖在下表显示。缺记录保持断线。"):t("竖线标在公告发布后的首个交易日，报告期末另列。点击图中日期查看当天指标；拖动底部滑块缩放。")}</p></div>
}
