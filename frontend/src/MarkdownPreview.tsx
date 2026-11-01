import {Fragment,type ReactNode} from 'react';

export type PreviewChart={path:string;data_url:string};
const svgData=/^data:image\/svg\+xml;base64,[A-Za-z0-9+/]+={0,2}$/;
const relativePath=(value:string)=>!value.startsWith('/')&&!value.includes('\\')&&!value.split('/').some(p=>p==='..')&&!/^[a-z][a-z0-9+.-]*:/i.test(value);
const cleanTarget=(value:string)=>value.startsWith('<')&&value.endsWith('>')?value.slice(1,-1):value;

function inline(text:string):ReactNode[]{
 const matcher=/(\[[^\]]+\]\((?:<[^>]+>|[^)]+)\)|\*\*[^*]+\*\*|`[^`]+`)/g;
 const nodes:ReactNode[]=[];let offset=0,index=0;
 for(const match of text.matchAll(matcher)){
  if(match.index!>offset)nodes.push(text.slice(offset,match.index));
  const token=match[0],key=index++;
  if(token.startsWith('**'))nodes.push(<strong key={key}>{token.slice(2,-2)}</strong>);
  else if(token.startsWith('`'))nodes.push(<code key={key}>{token.slice(1,-1)}</code>);
  else{const link=token.match(/^\[([^\]]+)\]\((.*)\)$/)!,target=cleanTarget(link[2]);
   if(/^https?:\/\//i.test(target)&&!/[\s<>]/.test(target))nodes.push(<a key={key} href={target} target="_blank" rel="noopener noreferrer">{link[1]}</a>);
   else if(relativePath(target))nodes.push(<span className="markdown-attachment" key={key} title="文件随下载附件包提供">{link[1]}<small>附件</small></span>);
   else nodes.push(<span key={key}>{link[1]}</span>);
  }
  offset=match.index!+token.length;
 }
 if(offset<text.length)nodes.push(text.slice(offset));return nodes;
}
const metricLabels:Record<string,string>={total_return:'累计收益',annualized_return:'年化收益',max_drawdown:'最大回撤',trade_count:'成交次数',sharpe_ratio:'夏普比率',final_equity:'期末权益',n:'有效样本',flow_n:'申赎参考样本',turnover_n:'成交参考样本',flow:'估算净申赎',shares:'ETF总份额',margin_balance:'ETF融资余额'};
function JsonBlock({text,heading}:{text:string;heading:string}){
 let summary:Record<string,unknown>|null=null;
 try{const value=JSON.parse(text);if(value&&typeof value==='object'&&!Array.isArray(value))summary=value}catch{}
 const metrics=summary?Object.keys(metricLabels).filter(k=>Object.hasOwn(summary!,k)).slice(0,6):[];
 return <>{metrics.length>0&&<dl className="markdown-metrics">{metrics.map(key=><div key={key}><dt>{metricLabels[key]}</dt><dd>{summary![key]==null?'—':typeof summary![key]==='number'?Number(summary![key]).toLocaleString('zh-CN',{maximumFractionDigits:3}):String(summary![key])}{['total_return','annualized_return','max_drawdown'].includes(key)&&summary![key]!=null?'%':''}</dd></div>)}</dl>}<details className="markdown-technical"><summary>{heading==='参数'?'查看计算参数':'查看完整计算明细'}</summary><pre><code>{text}</code></pre></details></>;
}
/** Text is escaped by React; only server-generated SVG image attachments are rendered. */
export default function MarkdownPreview({markdown,charts=[]}:{markdown:string;charts?:PreviewChart[]}){
 const lines=markdown.replace(/\r\n/g,'\n').split('\n'),nodes:ReactNode[]=[];
 const chartMap=new Map(charts.filter(c=>relativePath(c.path)&&svgData.test(c.data_url)).map(c=>[c.path,c.data_url]));
 let i=0,heading='';if(lines[0]==='---'){i=1;while(i<lines.length&&lines[i]!=='---')i++;i++}
 while(i<lines.length){
  const line=lines[i];if(!line.trim()){i++;continue}const start=i;
  if(line.startsWith('```')){const language=line.slice(3).trim(),code:string[]=[];i++;while(i<lines.length&&!lines[i].startsWith('```'))code.push(lines[i++]);i++;nodes.push(language==='json'?<JsonBlock key={start} text={code.join('\n')} heading={heading}/>:<pre key={start}><code>{code.join('\n')}</code></pre>);continue}
  const h=line.match(/^(#{1,6})\s+(.+)$/);
  if(h){heading=h[2];nodes.push(h[1].length===1?<h2 className="markdown-document-title" key={start}>{inline(h[2])}</h2>:h[1].length===2?<h3 key={start}>{inline(h[2])}</h3>:<h4 key={start}>{inline(h[2])}</h4>);i++;continue}
  const image=line.trim().match(/^!\[([^\]]*)\]\((.*)\)$/);
  if(image){const path=cleanTarget(image[2]),data=chartMap.get(path);nodes.push(<figure className="markdown-chart" key={start}>{data?<img src={data} alt={image[1]||'研究图表'}/>:<div className="markdown-image-placeholder">{image[1]||'图片'} · {relativePath(path)?'图表随附件包提供':'外部图片不会自动加载'}</div>}<figcaption>{image[1]}</figcaption></figure>);i++;continue}
  if(line.trim().startsWith('|')&&i+1<lines.length&&/^\s*\|?\s*:?-{3}/.test(lines[i+1])){const cells=(row:string)=>row.trim().replace(/^\||\|$/g,'').split('|').map(v=>v.trim());const headers=cells(line),rows:string[][]=[];i+=2;while(i<lines.length&&lines[i].trim().startsWith('|'))rows.push(cells(lines[i++]));nodes.push(<div className="table-scroll" key={start}><table><thead><tr>{headers.map((c,j)=><th key={j}>{inline(c)}</th>)}</tr></thead><tbody>{rows.map((row,j)=><tr key={j}>{row.map((c,k)=><td key={k}>{inline(c)}</td>)}</tr>)}</tbody></table></div>);continue}
  if(/^\s*[-*]\s+/.test(line)){const items:string[]=[];while(i<lines.length&&/^\s*[-*]\s+/.test(lines[i]))items.push(lines[i++].replace(/^\s*[-*]\s+/,''));nodes.push(<ul key={start}>{items.map((item,j)=><li key={j}>{inline(item)}</li>)}</ul>);continue}
  if(/^\d+\.\s+/.test(line)){const items:string[]=[];while(i<lines.length&&/^\d+\.\s+/.test(lines[i]))items.push(lines[i++].replace(/^\d+\.\s+/,''));nodes.push(<ol key={start}>{items.map((item,j)=><li key={j}>{inline(item)}</li>)}</ol>);continue}
  const paragraph=[line];i++;while(i<lines.length&&lines[i].trim()&&!/^(#{1,6}\s|```|!\[|[-*]\s|\d+\.\s|\|)/.test(lines[i]))paragraph.push(lines[i++]);nodes.push(<p key={start}>{paragraph.map((p,j)=><Fragment key={j}>{j>0&&<br/>}{inline(p)}</Fragment>)}</p>);
 }
 return <article className="markdown-document" aria-label="格式化笔记预览">{nodes}</article>;
}
