// @vitest-environment jsdom
import {setLocale} from '../i18n';
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import type {Row} from '../api';
import Simulation from '../pages/Simulation';
import {defaultConfig,cloneConfig} from './model';

const http=vi.hoisted(()=>({request:vi.fn(),post:vi.fn(),download:vi.fn()}));
const project=vi.hoisted(()=>({current:{activeProject:null as any,projects:[] as any[],selectProject:vi.fn(),reloadProjects:vi.fn(),linkRecord:vi.fn()}}));
vi.mock('../http',()=>http);
vi.mock('../workspace/ProjectContext',()=>({useProject:()=>project.current}));
vi.mock('../components',()=>({
 Panel:({title,children,action,className}:any)=><section className={className}><h2>{title}</h2>{action}{children}</section>,
 Note:({children}:any)=><div>{children}</div>,Empty:({children}:any)=><div>{children}</div>,
 Metric:({label,value,sub}:any)=><div><span>{label}</span><strong>{value}</strong><small>{sub}</small></div>,
 Chart:({rows}:any)=><div data-testid="account-chart">{rows.length} 个账户观测</div>,
 RawTable:({rows}:any)=><div>{rows.map((row:Row,index:number)=><div key={index}>{Object.values(row).join(' ')}</div>)}</div>,
 LoadingButton:({busy,disabled,children,...props}:any)=><button {...props} disabled={busy||disabled}>{busy?'处理中…':children}</button>,
}));

let database:Record<string,Row>;
const maParameters=[{key:'fast_period',label:'快线周期',default:5,min:2,max:500},{key:'slow_period',label:'慢线周期',default:20,min:3,max:500}];
const catalog={defaults:defaultConfig,tickers:[{ticker:'000858'},{ticker:'600036'}],strategies:[
 {name:'dual_ma',label:'双均线',parameters:maParameters},
 {name:'dual_ma_volume',label:'双均线放量',description:'短期均线高于长期均线且成交量达到阈值时入场，反向退出。',parameters:[
  ...maParameters,{key:'volume_window',label:'成交量窗口',default:20,min:2,max:500},
  {key:'volume_threshold',label:'成交量倍数阈值',default:1.2,min:.01,max:500,step:.01},
 ]},
 {name:'dual_ma_volatility',label:'双均线波动控制',description:'双均线入场时用已观察的滚动波动率调整预算，保留原出场规则。',parameters:[
  ...maParameters,{key:'volatility_window',label:'波动率窗口',default:20,min:2,max:500},
  {key:'volatility_threshold',label:'日波动率阈值（小数）',default:.03,min:.001,max:1,step:.001},
  {key:'high_volatility_multiplier',label:'高波动入场预算倍率',default:.5,min:.05,max:1,step:.05},
 ]},
 {name:'buy_and_hold',label:'预算内买入持有',description:'首次观测收盘后，按配置仓位在后续可交易日开盘入场，持有至回测结束。',parameters:[]},
]};
const dates=['2024-01-02','2024-01-03','2024-01-04'];
function fixture(id='run-a',kind='backtest'):Row{
 const config={...cloneConfig(defaultConfig),name:id==='run-a'?'基线 A':'基线 B',tickers:['000858'],start_date:dates[0],end_date:dates[2]};
 const metrics={total_return:2,max_drawdown:-1,trade_count:2};
 return {id,name:config.name,status:'completed',progress:100,kind,parent_id:null,config,synthetic:true,manifest:[],result:{metrics,baseline:metrics,series:dates.map((date,index)=>({date,equity:1000000+index*10000,benchmark:1000000+index*5000})),bars:{'000858':dates.map((date,index)=>({date,open:20+index,high:22+index,low:19+index,close:21+index,volume:10000}))},trades:[{date:dates[0],signal_date:'2023-12-29',ticker:'000858',action:'buy',shares:100,price:20,fee:5,realized_pnl:0,reason:'最初买入信号',evidence:{fast_ma:20}},{date:dates[2],signal_date:dates[1],ticker:'000858',action:'sell',shares:100,price:22,fee:5,realized_pnl:190,reason:'后续退出信号',evidence:{slow_ma:21}}],decisions:[],assumptions:['测试撮合假设'],engine:{version:'2.0.0'},scenarios:[{name:'提高费用',metrics,delta_return:-1,changes:{commission_rate:.001}}],variants:[{value:5,metrics}],folds:[],parameter:'fast_period'}};
}
function list(){return Object.values(database).map(run=>({...run,metrics:run.result.metrics}))}
const pageProps={status:{datasets:[],series:[]},reload:vi.fn(),setPage:vi.fn()};
function deferred<T>(){let resolve!:(value:T)=>void;const promise=new Promise<T>(r=>{resolve=r});return {promise,resolve}}

beforeEach(()=>{setLocale('zh');
 localStorage.clear();location.hash='simulation?run=run-a';
 Object.defineProperty(window,'innerWidth',{value:1200,writable:true,configurable:true});
 database={'run-a':fixture(),'run-b':fixture('run-b')};
 project.current={activeProject:null,projects:[],selectProject:vi.fn(),reloadProjects:vi.fn(),linkRecord:vi.fn().mockResolvedValue(undefined)};
 http.request.mockImplementation(async(path:string)=>{
  if(path==='/catalog')return catalog;
  if(path==='/runs')return {runs:list()};
  if(path.startsWith('/notes?'))return {notes:[]};
  if(path.startsWith('/runs/'))return database[path.slice('/runs/'.length)];
  throw new Error('unexpected read '+path);
 });
 http.post.mockImplementation(async(path:string,body:Row)=>{
  if(path==='/notes')return {id:'note',...body};
  const child=fixture('created',body?.kind||'backtest');database[child.id]=child;return child;
 });
});
afterEach(()=>{cleanup();setLocale('en');vi.clearAllMocks()});

describe('Simulation workbench interactions',()=>{
 it('submits the selected catalog strategy with its own parameters',async()=>{
  render(<Simulation {...pageProps}/>);
  await screen.findByRole('tab',{name:'推演终端'});
  fireEvent.click(screen.getByRole('button',{name:'新建回测'}));
  const composer=within(screen.getByRole('dialog'));
  const strategy=composer.getByLabelText('策略');
  fireEvent.change(strategy,{target:{value:'dual_ma_volume'}});
  expect(composer.getByLabelText('成交量窗口')).toHaveProperty('value','20');
  expect(composer.getByLabelText('成交量倍数阈值')).toHaveProperty('value','1.2');
  fireEvent.change(composer.getByLabelText('成交量倍数阈值'),{target:{value:'2.5'}});
  fireEvent.change(strategy,{target:{value:'buy_and_hold'}});
  expect(composer.queryByLabelText('快线周期')).toBeNull();
  expect(composer.queryByLabelText('成交量倍数阈值')).toBeNull();
  fireEvent.change(strategy,{target:{value:'dual_ma_volatility'}});
  expect(composer.getByLabelText('日波动率阈值（小数）')).toHaveProperty('value','0.03');
  fireEvent.change(composer.getByLabelText('高波动入场预算倍率'),{target:{value:'0.25'}});
  fireEvent.click(composer.getByRole('button',{name:'提交回测'}));
  await waitFor(()=>expect(http.post).toHaveBeenCalledWith('/runs',expect.objectContaining({strategy:{
   name:'dual_ma_volatility',parameters:{fast_period:5,slow_period:20,volatility_window:20,volatility_threshold:.03,high_volatility_multiplier:.25},
  }})));
 });

 it('keeps pressure experiments and historical forks for budgeted buy and hold',async()=>{
  database['run-a'].config.strategy={name:'buy_and_hold',parameters:{}};
  render(<Simulation {...pageProps}/>);
  fireEvent.click(await screen.findByRole('tab',{name:'实验室'}));
  fireEvent.click(screen.getByRole('button',{name:'新建对照'}));
  const comparison=within(screen.getByRole('dialog'));
  expect(comparison.getAllByRole('option').map(option=>(option as HTMLOptionElement).value)).toEqual(['pressure','branch']);
  fireEvent.click(comparison.getByRole('button',{name:'提交对照'}));
  await waitFor(()=>expect(http.post).toHaveBeenCalledWith('/runs/run-a/experiments',{kind:'pressure'}));
 });

 it('keeps a dividend receivable visible before cash is credited',async()=>{
  const result=database['run-a'].result;
  result.series[0]={...result.series[0],dividend_cash_paid:0,dividend_receivables:0};
  result.series[1]={...result.series[1],dividend_cash_paid:0,dividend_receivables:25};
  result.series[2]={...result.series[2],dividend_cash_paid:25,dividend_receivables:0};
  result.dividends=[{ticker:'000858',record_date:dates[0],ex_date:dates[1],payment_date:dates[2],
   shares:100,cash_per_share:.25,gross_amount:25,credited_date:dates[2]}];
  render(<Simulation {...pageProps}/>);
  fireEvent.click(await screen.findByRole('tab',{name:'现金分红'}));
  expect(screen.getByText(new RegExp(`000858.*${dates[2]}.*${dates[2]}`))).toBeTruthy();
  const summary=screen.getByText('累计入账税前红利').parentElement!;
  expect(summary.querySelector('dd')?.textContent).toBe('25 元 CNY');
  fireEvent.click(screen.getByRole('button',{name:'上一日'}));
  expect(screen.getByText(new RegExp(`000858.*${dates[2]}.*—`))).toBeTruthy();
  expect(summary.querySelector('dd')?.textContent).toBe('0 元 CNY');
  expect(screen.getByText('期末应收税前红利').parentElement!.querySelector('dd')?.textContent).toBe('25 元 CNY');
 });

 it.each([
  {name:'dual_ma_volume',indicators:{volume_ma:1000,volume_ratio:1.5},labels:['信号成交量均值','信号成交量倍数'],displays:['1,000股','1.5×']},
  {name:'dual_ma_volatility',indicators:{realized_volatility:.0234,entry_size_multiplier:.5},labels:['信号日波动率','信号入场预算倍率'],displays:['2.34%','0.5×']},
 ])('shows $name signal evidence only at a visible replay date',async({name,indicators,labels,displays})=>{
  const run=database['run-a'];
  const evidence={strategy:name,indicators};
  run.config.strategy={name,parameters:{}};
  run.result.trades[1].evidence=evidence;
  run.result.decisions=[{id:'volume-decision',date:dates[1],ticker:'000858',status:'queued',reason:'等待策略条件',evidence}];
  render(<Simulation {...pageProps}/>);
  const inspector=within(await screen.findByRole('complementary',{name:'成交解释'}));
  for(const label of labels.filter(label=>label!=='信号入场预算倍率'))expect(inspector.getByText(label)).toBeTruthy();
  for(const display of displays.filter(display=>display!=='0.5×'))expect(inspector.getByText(display)).toBeTruthy();
  expect(inspector.queryByText('信号入场预算倍率')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'上一日'}));
  for(const label of labels)expect(inspector.queryByText(label)).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:`${dates[1]} 收盘 22`}));
  for(const display of displays)expect(inspector.getByText(display)).toBeTruthy();
 });

 it('switches labels live without losing the selected record or an edited draft',async()=>{
  render(<Simulation {...pageProps}/>);
  await screen.findByRole('tab',{name:'笔记与证据'});
  fireEvent.click(screen.getByRole('tab',{name:'笔记与证据'}));
  fireEvent.change(screen.getByLabelText('观察与结论'),{target:{value:'Keep my original 中文 research'}});
  act(()=>setLocale('en'));
  expect(screen.getByRole('heading',{name:'Strategies & replay'})).toBeTruthy();
  expect((screen.getByLabelText('Observations & conclusions') as HTMLTextAreaElement).value).toBe('Keep my original 中文 research');
  expect((screen.getByLabelText('Current strategy record') as HTMLSelectElement).value).toBe('run-a');
  act(()=>setLocale('zh'));
  expect((screen.getByLabelText('观察与结论') as HTMLTextAreaElement).value).toBe('Keep my original 中文 research');
 });
 it('shows completed pressure sample counts and every scenario change with Chinese labels and units',async()=>{
  const pressure=fixture('run-a','pressure');
  const metrics={total_return:12.34567,max_drawdown:-6.789,trade_count:8,total_fees:123.456};
  pressure.result={baseline:metrics,engine:{version:'2.0.0'},scenarios:[
   {name:'双倍费用',metrics,delta_return:1.234,changes:{commission_rate:.0006,min_commission:10,tax_rate:.001}},
   {name:'额外滑点',metrics,delta_return:1.234,changes:{slippage_bps:25}},
   {name:'执行延迟',metrics,delta_return:1.234,changes:{execution_delay:2}},
   {name:'减半仓位',metrics,delta_return:1.234,changes:{position_size:.15}},
   {name:'组合压力',metrics,delta_return:1.234,changes:{commission_rate:.0006,slippage_bps:35,execution_delay:2}},
  ]};
  database['run-a']=pressure;
  render(<Simulation {...pageProps}/>);
  expect(await screen.findByText('5 组压力情景')).toBeTruthy();
  expect(screen.queryByText('样本待计算')).toBeNull();
  const results=document.querySelector('.simulation-results')!;
  expect(results.textContent).toContain('佣金率 0.06%；最低佣金 10.00 元；卖出税率 0.10%');
  expect(results.textContent).toContain('双边滑点 25 bps');
  expect(results.textContent).toContain('执行延迟 2 个交易日');
  expect(results.textContent).toContain('单标的仓位 15.00%');
  expect(results.textContent).toContain('佣金率 0.06%；双边滑点 35 bps；执行延迟 2 个交易日');
  expect(results.textContent).toContain('12.35 -6.79 1.23 123.46');
  expect(results.textContent).not.toContain('commission_rate');
  expect(results.textContent).not.toContain('slippage_bps');
 });

 it('labels a completed parameter experiment by its actual candidates instead of pending account samples',async()=>{
  const parameter=fixture('run-a','parameter');
  delete parameter.result.series;
  parameter.result.variants=[{value:5,metrics:parameter.result.baseline},{value:10,metrics:parameter.result.baseline}];
  database['run-a']=parameter;
  render(<Simulation {...pageProps}/>);
  expect(await screen.findByText('2 个参数候选')).toBeTruthy();
  expect(screen.queryByText('样本待计算')).toBeNull();
  expect(document.querySelector('.simulation-results')?.textContent).toContain('5 个交易日');
 });

 it('opens with results, links ledger selection to evidence, and hides comparison forms until requested',async()=>{
  render(<Simulation {...pageProps}/>);
  const inspector=await screen.findByRole('complementary',{name:'成交解释'});
  expect(within(inspector).getByText('后续退出信号')).toBeTruthy();
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(screen.queryByLabelText('实验名称')).toBeNull();
  expect(http.post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('tab',{name:'成交账本（2）'}));
  fireEvent.click(screen.getByRole('button',{name:dates[0]}));
  expect(within(inspector).getByText('最初买入信号')).toBeTruthy();
  fireEvent.click(screen.getByRole('tab',{name:'实验室'}));
  expect(screen.getByText('已保存的对照实验')).toBeTruthy();
  expect(screen.queryByLabelText('对照类型')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'新建对照'}));
  expect(screen.getByRole('dialog',{name:'新建对照实验'})).toBeTruthy();
  expect(screen.getByLabelText('对照类型')).toBeTruthy();
 });

 it('keeps project securities explicit when demo data cannot support them',async()=>{
  project.current.activeProject={id:'tantalum',name:'东方钽业',symbols:['000962'],links:[]};
  render(<Simulation {...pageProps}/>);
  await screen.findByRole('complementary',{name:'成交解释'});
  fireEvent.click(screen.getByRole('button',{name:'新建回测'}));
  expect((screen.getByLabelText('证券代码（逗号分隔）') as HTMLInputElement).value).toBe('000962');
  expect((screen.getByLabelText('数据来源') as HTMLSelectElement).value).toBe('akshare');
  fireEvent.change(screen.getByLabelText('数据来源'),{target:{value:'demo'}});
  expect(screen.getByText(/没有合成演示行情/)).toBeTruthy();
  expect(screen.getByRole('button',{name:'提交回测'})).toHaveProperty('disabled',true);
  expect((screen.getByLabelText('证券代码（逗号分隔）') as HTMLInputElement).value).toBe('000962');
  expect(http.post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'关闭配置'}));
  expect(screen.getByText(/000858/,{selector:'.simulation-record-summary p span'})).toBeTruthy();
 });

 it('binds an in-flight baseline to the submitting project after the header project changes',async()=>{
  const original={id:'one',name:'项目一',symbols:['000858'],links:[]};
  project.current.activeProject=original;
  const pending=deferred<Row>();http.post.mockImplementation((path:string)=>path==='/runs'?pending.promise:Promise.reject(new Error(path)));
  const view=render(<Simulation {...pageProps}/>);
  await screen.findByRole('complementary',{name:'成交解释'});
  fireEvent.click(screen.getByRole('button',{name:'新建回测'}));
  fireEvent.click(screen.getByRole('button',{name:'提交回测'}));
  await waitFor(()=>expect(http.post).toHaveBeenCalledWith('/runs',expect.objectContaining({tickers:['000858'],source:'akshare'})));
  project.current.activeProject={id:'two',name:'项目二',symbols:['000962'],links:[]};view.rerender(<Simulation {...pageProps}/>);
  const created=fixture('created');database.created=created;
  await act(async()=>{pending.resolve(created);await pending.promise});
  await waitFor(()=>expect(project.current.linkRecord).toHaveBeenCalledWith('simulation','created','one'));
  expect((screen.getByLabelText('证券代码（逗号分隔）') as HTMLInputElement).value).toBe('000962');
  expect(location.hash).toContain('run=run-a');
 });

 it('links a new comparison to an unambiguous parent project when there is no active project',async()=>{
  project.current.projects=[{id:'parent-project',name:'原研究',links:[{kind:'simulation',run_id:'run-a'}]}];
  render(<Simulation {...pageProps}/>);
  await screen.findByRole('complementary',{name:'成交解释'});
  fireEvent.click(screen.getByRole('tab',{name:'实验室'}));
  fireEvent.click(screen.getByRole('button',{name:'新建对照'}));
  fireEvent.click(screen.getByRole('button',{name:'提交对照'}));
  await waitFor(()=>expect(http.post).toHaveBeenCalledWith('/runs/run-a/experiments',{kind:'pressure'}));
  await waitFor(()=>expect(project.current.linkRecord).toHaveBeenCalledWith('simulation','created','parent-project'));
 });

 it.each(['parameter','walk_forward','branch'])('keeps the %s comparison controls and submits their explicit parameters',async(type)=>{
  render(<Simulation {...pageProps}/>);
  await screen.findByRole('complementary',{name:'成交解释'});
  fireEvent.click(screen.getByRole('tab',{name:'实验室'}));
  fireEvent.click(screen.getByRole('button',{name:'新建对照'}));
  fireEvent.change(screen.getByLabelText('对照类型'),{target:{value:type}});
  if(type==='parameter'){
   fireEvent.change(screen.getByLabelText('参数名'),{target:{value:'fast_period'}});
   fireEvent.change(screen.getByLabelText('候选值'),{target:{value:'3,5,8'}});
  }else if(type==='walk_forward'){
   fireEvent.change(screen.getByLabelText('训练交易日'),{target:{value:'30'}});
   fireEvent.change(screen.getByLabelText('测试交易日'),{target:{value:'10'}});
  }else fireEvent.change(screen.getByLabelText('分叉日期'),{target:{value:dates[1]}});
  fireEvent.click(screen.getByRole('button',{name:'提交对照'}));
  const expected=type==='parameter'?{kind:type,parameter:'fast_period',values:[3,5,8]}:type==='walk_forward'?{kind:type,training_days:30,test_days:10}:{name:'仓位对照',fork_date:dates[1],account:{position_size:.5}};
  await waitFor(()=>expect(http.post).toHaveBeenCalledWith('/runs/run-a/'+(type==='branch'?'branch':'experiments'),expected));
 });

 it('uses the active company fixed snapshot as the new baseline input',async()=>{
  project.current.activeProject={id:'tantalum',name:'东方钽业',symbols:['000962'],links:[]};
  const snapshot={id:'a'.repeat(20),symbol:'000962',kind:'quotes',request:{adjust:'3'},start:dates[0],end:dates[2],fetched_at:'2026-11-01T00:00:00Z'};
  render(<Simulation {...pageProps} status={{datasets:[snapshot],series:[]}}/>);
  await screen.findByRole('complementary',{name:'成交解释'});
  fireEvent.click(screen.getByRole('button',{name:'新建回测'}));
  expect((screen.getByLabelText('数据来源') as HTMLSelectElement).value).toBe('snapshot');
  expect((screen.getByLabelText('证券代码（逗号分隔）') as HTMLInputElement).value).toBe('000962');
  fireEvent.click(screen.getByRole('button',{name:'提交回测'}));
  await waitFor(()=>expect(http.post).toHaveBeenCalledWith('/bridge/backtests',expect.objectContaining({snapshot_ids:[snapshot.id],project_id:'tantalum',config:expect.objectContaining({tickers:['000962'],source:'snapshot',start_date:dates[0],end_date:dates[2]})})));
 });

 it('preserves newer note text typed while a previous note is saving',async()=>{
  const pending=deferred<Row>();http.post.mockImplementation((path:string)=>path==='/notes'?pending.promise:Promise.reject(new Error(path)));
  render(<Simulation {...pageProps}/>);
  await screen.findByRole('complementary',{name:'成交解释'});
  fireEvent.click(screen.getByRole('tab',{name:'笔记与证据'}));
  fireEvent.change(screen.getByLabelText('观察与结论'),{target:{value:'第一段观察'}});
  fireEvent.click(screen.getByRole('button',{name:'保存实验笔记'}));
  fireEvent.change(screen.getByLabelText('观察与结论'),{target:{value:'尚未保存的第二段'}});
  await act(async()=>{pending.resolve({id:'saved'});await pending.promise});
  await screen.findByText('实验笔记已保存。');
  expect((screen.getByLabelText('观察与结论') as HTMLTextAreaElement).value).toBe('尚未保存的第二段');
  expect(http.post).toHaveBeenCalledWith('/notes',{run_id:'run-a',title:'实验观察',body:'第一段观察'});
 });

 it('does not re-enter blind playback when a late advance returns after exit',async()=>{
  const complete=database['run-a'].result;
  const session={id:'blind',date:dates[0],cursor:0,total_steps:3,revealed:false,result:{...complete,series:complete.series.slice(0,1),bars:{'000858':complete.bars['000858'].slice(0,1)},trades:[],metrics:{total_return:0,max_drawdown:0,trade_count:0}}};
  const pending=deferred<Row>();
  http.post.mockImplementation((path:string)=>path==='/runs/run-a/sessions'?Promise.resolve(session):path==='/sessions/blind/advance'?pending.promise:Promise.reject(new Error(path)));
  render(<Simulation {...pageProps}/>);
  await screen.findByRole('complementary',{name:'成交解释'});
  fireEvent.click(screen.getByRole('button',{name:'开始盲测'}));
  fireEvent.click(await screen.findByRole('button',{name:'推进 1 日'}));
  fireEvent.click(screen.getByRole('button',{name:'退出盲测'}));
  await act(async()=>{pending.resolve({...session,date:dates[1],cursor:1});await pending.promise});
  expect(screen.getByRole('button',{name:'开始盲测'})).toBeTruthy();
  expect(screen.queryByRole('button',{name:'退出盲测'})).toBeNull();
  expect(screen.getByRole('button',{name:'2024-01-04 收盘 23'})).toBeTruthy();
 });

 it('passes an imported evidence file through unchanged and links it to the current project',async()=>{
  project.current.activeProject={id:'one',name:'项目一',symbols:[],links:[]};
  const raw='{"price":5.0,"format":"quantsandbox-evidence-v2","sha256":"fixed"}';
  const originalRequest=http.request.getMockImplementation()!;
  http.request.mockImplementation(async(path:string,init?:RequestInit)=>{if(path==='/import'){const run=fixture('imported');database.imported=run;return run}return originalRequest(path,init)});
  render(<Simulation {...pageProps}/>);
  await screen.findByRole('complementary',{name:'成交解释'});
  fireEvent.click(screen.getByText('记录操作'));
  const file=new File([raw],'evidence.json',{type:'application/json'});Object.defineProperty(file,'text',{value:async()=>raw});
  fireEvent.change(screen.getByLabelText('导入证据包'),{target:{files:[file]}});
  await waitFor(()=>expect(http.request).toHaveBeenCalledWith('/import',{method:'POST',body:raw}));
  await waitFor(()=>expect(project.current.linkRecord).toHaveBeenCalledWith('simulation','imported','one'));
 });

 it('defaults mobile charts to sixty sessions and provides trade cards alongside the full-table control',async()=>{
  window.innerWidth=390;
  render(<Simulation {...pageProps}/>);
  await screen.findByRole('complementary',{name:'成交解释'});
  expect((screen.getByRole('combobox',{name:'显示交易日'}) as HTMLSelectElement).value).toBe('60');
  fireEvent.click(screen.getByRole('tab',{name:'成交账本（2）'}));
  expect(screen.getByRole('button',{name:'查看完整表格'})).toBeTruthy();
  expect(document.querySelectorAll('.simulation-trade-card')).toHaveLength(2);
  fireEvent.click(screen.getByRole('button',{name:'查看完整表格'}));
  expect(document.querySelector('.simulation-ledger-table')?.classList.contains('show-full')).toBe(true);
 });
});
