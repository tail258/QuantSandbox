// @vitest-environment jsdom
import {act,cleanup,render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import Obsidian from './Obsidian';
import {api} from '../api';
import {post,request} from '../http';

const context=vi.hoisted(()=>({activeProject:null as any}));
vi.mock('../api',()=>({api:vi.fn()}));
vi.mock('../http',()=>({request:vi.fn(),post:vi.fn()}));
vi.mock('../workspace/ProjectContext',()=>({useProject:()=>context}));
const markdown='---\napplication: QuantSandbox\n---\n\n# 库存与价格\n\n## 结果摘要\n\n配对样本 n=123；统计截止 2026-10-28。\n\n## 来源与时间\n\n- [公开来源](https://example.org/source)；单位 吨；获取 2026-10-29。\n\n## 参数\n\n```json\n{"lag":5}\n```\n\n![研究图表](<note.assets/chart.svg>)\n';
const chart='data:image/svg+xml;base64,'+btoa('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>');
const research=[{id:'research1',title:'库存与价格',params:{start:'2025-01-01',end:'2026-10-28'}},{id:'research2',title:'另一条研究'}];
const preview={markdown,title:'库存与价格',filename:'note.md',files:[{path:'note.md',size:100},{path:'note.assets/chart.svg',size:200}],charts:[{path:'note.assets/chart.svg',data_url:chart}],preview_token:'exact-token',can_publish:false};
const props={status:{},reload:async()=>{},setPage:()=>{}};
let config={enabled:false,vault_path:'',folder:'QuantSandbox'};
beforeEach(()=>{
 vi.clearAllMocks();context.activeProject=null;config={enabled:false,vault_path:'',folder:'QuantSandbox'};history.replaceState(null,'','#obsidian');
 vi.mocked(api).mockResolvedValue(research);
 vi.mocked(request).mockImplementation(async(url,options)=>{if(url==='/obsidian/config')return options?.method==='PUT'?JSON.parse(options.body as string):config;if(url==='/runs')return {runs:[{id:'simulation1',name:'基线实验',status:'completed'},{id:'pending',name:'排队实验',status:'queued'}]};throw new Error('Unexpected '+url)});
 vi.mocked(post).mockResolvedValue(preview);
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()});
async function selectResearch(user:ReturnType<typeof userEvent.setup>){await screen.findByRole('option',{name:/库存与价格/});await user.selectOptions(screen.getByLabelText('已保存记录'),'research1')}

describe('Obsidian research-note flow',()=>{
 it('keeps vault settings optional and renders a readable note, source, sample, chart and raw toggle',async()=>{
  const user=userEvent.setup();render(<Obsidian {...props}/>);
  expect(screen.queryByLabelText('笔记库绝对路径')).toBeNull();
  await selectResearch(user);await user.click(screen.getByRole('button',{name:'生成预览'}));
  const article=await screen.findByRole('article',{name:'格式化笔记预览'});
  expect(article.textContent).toContain('配对样本 n=123');expect(article.textContent).toContain('2026-10-28');
  expect(screen.getByRole('link',{name:'公开来源'}).getAttribute('href')).toBe('https://example.org/source');
  expect(screen.getByRole('img',{name:'研究图表'}).getAttribute('src')).toBe(chart);
  expect(screen.getByText('查看计算参数').closest('details')?.open).toBe(false);
  expect((screen.getByRole('button',{name:'写入本次笔记'}) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole('button',{name:'下载 Markdown 与附件'}) as HTMLButtonElement).disabled).toBe(false);
  await user.click(screen.getByRole('button',{name:'Markdown 源码'}));
  expect(screen.getByLabelText('Markdown 源码').textContent).toBe(markdown);expect(screen.queryByRole('article')).toBeNull();
  await user.click(screen.getByRole('button',{name:'阅读预览'}));expect(screen.getByRole('article')).toBeTruthy();
  await user.click(screen.getByRole('button',{name:'笔记库设置（可选）'}));expect(screen.getByLabelText('笔记库绝对路径')).toBeTruthy();
 });
 it('invalidates the exact preview immediately when a conclusion changes',async()=>{
  const user=userEvent.setup();vi.mocked(post).mockResolvedValue({...preview,can_publish:true});render(<Obsidian {...props}/>);
  await selectResearch(user);await user.click(screen.getByRole('button',{name:'生成预览'}));await screen.findByRole('article');
  expect((screen.getByRole('button',{name:'写入本次笔记'}) as HTMLButtonElement).disabled).toBe(false);
  await user.click(screen.getByText('调整标题与补充结论（可选）'));await user.type(screen.getByLabelText('补充结论'),'新增观察');
  expect(screen.queryByRole('article')).toBeNull();expect((screen.getByRole('button',{name:'写入本次笔记'}) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole('button',{name:'下载 Markdown 与附件'}) as HTMLButtonElement).disabled).toBe(true);
 });
 it('does not restore a stale preview after an edit while the response is pending',async()=>{
  const user=userEvent.setup();let resolve!:(value:any)=>void;vi.mocked(post).mockImplementation(()=>new Promise(done=>{resolve=done}));render(<Obsidian {...props}/>);
  await selectResearch(user);await user.click(screen.getByRole('button',{name:'生成预览'}));
  await user.click(screen.getByText('调整标题与补充结论（可选）'));await user.type(screen.getByLabelText('补充结论'),'已修改');
  await act(async()=>{resolve({...preview,can_publish:true})});
  await waitFor(()=>expect((screen.getByRole('button',{name:'生成预览'}) as HTMLButtonElement).disabled).toBe(false));
  expect(screen.queryByRole('article')).toBeNull();expect((screen.getByRole('button',{name:'写入本次笔记'}) as HTMLButtonElement).disabled).toBe(true);
 });
 it('filters the current project and lets the user deliberately show all records',async()=>{
  context.activeProject={id:'p1',name:'橡胶研究',conclusion:'周期观察',links:[{kind:'research',run_id:'research1'}]};
  const user=userEvent.setup();render(<Obsidian {...props}/>);await screen.findByRole('option',{name:/库存与价格/});
  expect(screen.queryByRole('option',{name:/另一条研究/})).toBeNull();
  await user.click(screen.getByLabelText('显示全部记录'));expect(screen.getByRole('option',{name:/另一条研究/})).toBeTruthy();
  await user.selectOptions(screen.getByLabelText('已保存记录'),'research2');
  await user.click(screen.getByLabelText('显示全部记录'));expect((screen.getByLabelText('已保存记录') as HTMLSelectElement).value).toBe('');
  await user.click(screen.getByText('调整标题与补充结论（可选）'));await user.click(screen.getByRole('button',{name:'填入当前项目结论'}));
  expect((screen.getByLabelText('补充结论') as HTMLTextAreaElement).value).toBe('周期观察');
 });
 it('honors a deep link to a record outside the current project',async()=>{
  context.activeProject={id:'p1',name:'项目一',links:[{kind:'research',run_id:'research1'}]};history.replaceState(null,'','#obsidian?project=p1&kind=research&run=research2');
  render(<Obsidian {...props}/>);await screen.findByRole('option',{name:/另一条研究/});
  expect((screen.getByLabelText('已保存记录') as HTMLSelectElement).value).toBe('research2');expect((screen.getByLabelText('显示全部记录') as HTMLInputElement).checked).toBe(true);
 });
 it('loads only completed simulation records when their kind is selected',async()=>{
  const user=userEvent.setup();render(<Obsidian {...props}/>);await screen.findByRole('option',{name:/库存与价格/});await user.selectOptions(screen.getByLabelText('记录类型'),'simulation');
  expect(screen.getByRole('option',{name:/基线实验/})).toBeTruthy();expect(screen.queryByRole('option',{name:/排队实验/})).toBeNull();
 });
 it('downloads the selected preview through the portable export endpoint',async()=>{
  const user=userEvent.setup(),fetchMock=vi.fn().mockResolvedValue({ok:true,blob:async()=>new Blob(['zip'])});vi.stubGlobal('fetch',fetchMock);
  const NativeURL=URL;vi.stubGlobal('URL',class extends NativeURL{static createObjectURL(){return 'blob:portable-note'}static revokeObjectURL(){}});
  const click=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
  render(<Obsidian {...props}/>);await selectResearch(user);await user.click(screen.getByRole('button',{name:'生成预览'}));await screen.findByRole('article');
  await user.click(screen.getByRole('button',{name:'下载 Markdown 与附件'}));
  expect(fetchMock).toHaveBeenCalledWith('/api/obsidian/export',expect.objectContaining({method:'POST',body:JSON.stringify({kind:'research',run_id:'research1'})}));
  expect(click).toHaveBeenCalledOnce();expect(await screen.findByRole('status')).toBeTruthy();
 });
 it('publishes only the explicit preview token and clears the preview afterward',async()=>{
  const user=userEvent.setup();vi.mocked(post).mockImplementation(async(url)=>url==='/obsidian/preview'?{...preview,can_publish:true}:{published:true,filename:'note.md'});
  render(<Obsidian {...props}/>);await selectResearch(user);await user.click(screen.getByRole('button',{name:'生成预览'}));await screen.findByRole('article');
  expect(vi.mocked(post).mock.calls.some(call=>call[0]==='/obsidian/publish')).toBe(false);
  await user.click(screen.getByRole('button',{name:'写入本次笔记'}));
  expect(post).toHaveBeenCalledWith('/obsidian/publish',{kind:'research',run_id:'research1',title:undefined,notes:undefined,preview_token:'exact-token'});
  await screen.findByText('已写入本次笔记：note.md');expect(screen.queryByRole('article')).toBeNull();
 });
});
