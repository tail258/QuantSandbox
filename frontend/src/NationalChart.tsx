import {ComposedChart,Line,XAxis,YAxis,Tooltip,CartesianGrid,ResponsiveContainer,Legend,ReferenceLine,Brush} from 'recharts';
import {Download} from 'lucide-react';
import {download,fmt,type Row} from './api';

export default function NationalChart({rows,events=[],mode='shares',onSelect}:{rows:Row[];events?:Row[];mode?:'shares'|'margin';onSelect?:(date:string)=>void}){
 const margin=mode==='margin';
 const data=rows.map(r=>({...r,shares_yi:r.shares==null?null:r.shares/1e8,etf_balance_yi:r.margin_balance==null?null:r.margin_balance/1e8,component_balance_yi:r.component_balance==null?null:r.component_balance/1e8}));
 const left=margin?'component_balance_yi':'price',right=margin?'etf_balance_yi':'shares_yi';
 return <div className="chart-wrap"><div className="chart-caption"><span>{margin?'左轴：固定名单成分股融资（亿元） · 右轴：ETF融资（亿元）':'左轴：ETF不复权价格（元） · 右轴：总份额（亿份）'}</span><button className="text-button" onClick={e=>{const svg=e.currentTarget.closest('.chart-wrap')?.querySelector('.recharts-wrapper > svg.recharts-surface');if(svg)download('national-'+mode+'.svg',new XMLSerializer().serializeToString(svg),'image/svg+xml')}}><Download size={14}/> 导出图表</button></div>
 <ResponsiveContainer width="100%" height={340}><ComposedChart data={data} margin={{top:24,right:4,bottom:4,left:4}} onClick={(state:any)=>{if(state?.activeLabel)onSelect?.(String(state.activeLabel))}}><CartesianGrid stroke="#edf0f2" vertical={false}/><XAxis dataKey="date" minTickGap={65} tick={{fontSize:10}}/><YAxis yAxisId="left" width={58} tick={{fontSize:10}} tickFormatter={v=>fmt(v,margin?0:2)} domain={['auto','auto']}/><YAxis yAxisId="right" orientation="right" width={58} tick={{fontSize:10}} tickFormatter={v=>fmt(v,0)} domain={['auto','auto']}/><Tooltip contentStyle={{fontSize:12,borderRadius:8,border:'1px solid #dce5e9'}} formatter={(v:any)=>fmt(v)}/><Legend wrapperStyle={{fontSize:11}}/>
 <Line yAxisId="left" dataKey={left} name={margin?'成分股融资余额（左轴）':'ETF价格（左轴）'} stroke="#6c8ca4" strokeWidth={1.6} dot={false} isAnimationActive={false} connectNulls={false}/><Line yAxisId="right" dataKey={right} name={margin?'ETF融资余额（右轴）':'ETF总份额（右轴）'} stroke="#087d79" strokeWidth={1.8} dot={false} isAnimationActive={false} connectNulls={false}/>
 {!margin&&events.filter(e=>e.plot_date).map((e,i)=><ReferenceLine key={e.report_date} x={e.plot_date} yAxisId="left" stroke="#b28b49" strokeDasharray="4 4" label={{value:'披露 '+e.report_date,position:'insideTopLeft',fontSize:10,fill:'#9d783b',dy:i%2*16}}/>)}<Brush dataKey="date" height={22} stroke="#a7bdc7" fill="#f4f7f8" travellerWidth={8}/></ComposedChart></ResponsiveContainer>
 <p className="muted">{margin?'两条线使用各自纵轴，只比较变化节奏；每日覆盖在下表显示。缺记录保持断线。':'竖线标在公告发布后的首个交易日，报告期末另列。点击图中日期查看当天指标；拖动底部滑块缩放。'}</p></div>
}
