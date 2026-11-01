// @vitest-environment jsdom
import {cleanup,render,screen} from '@testing-library/react';
import {afterEach,describe,expect,it} from 'vitest';
import MarkdownPreview from './MarkdownPreview';
afterEach(cleanup);
describe('safe Markdown reading view',()=>{
 it('escapes HTML and does not load external images or unsafe links',()=>{
  const {container}=render(<MarkdownPreview markdown={'# 安全笔记\n\n<script>alert(1)</script>\n\n![远端图片](https://example.org/image.svg)\n\n[危险地址](javascript:alert)\n'}/>);
  expect(container.querySelector('script')).toBeNull();expect(container.textContent).toContain('<script>alert(1)</script>');
  expect(container.querySelector('img')).toBeNull();expect(container.querySelector('a')).toBeNull();expect(screen.getByText(/外部图片不会自动加载/)).toBeTruthy();
 });
 it('renders only relative attachments with server SVG image data',()=>{
  const data='data:image/svg+xml;base64,PHN2Zy8+';
  const {container}=render(<MarkdownPreview markdown={'![正确](<record.assets/chart.svg>)\n\n![不匹配](../chart.svg)\n\n![非数据](other.svg)'} charts={[{path:'record.assets/chart.svg',data_url:data},{path:'../chart.svg',data_url:data},{path:'other.svg',data_url:'https://example.org/unsafe.svg'}]}/>);
  expect(container.querySelectorAll('img')).toHaveLength(1);expect(screen.getByRole('img',{name:'正确'}).getAttribute('src')).toBe(data);
 });
 it('keeps Markdown tables and result metrics readable while JSON starts collapsed',()=>{
  render(<MarkdownPreview markdown={'## 结果摘要\n\n```json\n{"total_return":12.5,"n":32}\n```\n\n| 指标 | 值 |\n| --- | --- |\n| 样本 | 32 |'}/>);
  expect(screen.getByText('12.5%')).toBeTruthy();expect(screen.getByText('有效样本')).toBeTruthy();expect(screen.getByRole('table')).toBeTruthy();expect(screen.getByText('查看完整计算明细').closest('details')?.open).toBe(false);
 });
});
