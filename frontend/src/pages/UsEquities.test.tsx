// @vitest-environment jsdom
import { render, screen, cleanup } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import UsEquities from './UsEquities'
import { setLocale } from '../i18n'
vi.mock('../workspace/ProjectContext',()=>({useProject:()=>({activeProject:null,reloadProjects:vi.fn()})}))
vi.mock('../api', async()=>({...await vi.importActual('../api'),api:vi.fn(async()=>({financials:[],snapshot_ids:[]}))}))
afterEach(cleanup)
it('shows an English empty state and explicit SEC configuration',async()=>{setLocale('en');render(<UsEquities/>);expect(await screen.findByText('No financial snapshot yet')).toBeTruthy();expect(screen.getByText(/SEC_USER_AGENT/)).toBeTruthy()})
it('shows Chinese labels',async()=>{setLocale('zh');render(<UsEquities/>);expect(await screen.findByText('尚无财务快照')).toBeTruthy()})
import userEvent from '@testing-library/user-event'
import { api } from '../api'
vi.mock('../components',()=>({Chart:()=> <div>price chart</div>}))
it('renders SEC fact values in millions and preserves project and snapshot save inputs',async()=>{
 setLocale('en')
 vi.mocked(api).mockImplementation(async(url)=>url.endsWith('/save')?{id:'record-one'}:{financials:[{period_end:'2025-12-31',metrics:{revenue:{value:26000000,unit:'USD',filed:'2026-02-20'}}}],snapshot_ids:['sec-fixed']})
 render(<UsEquities/> )
 expect(await screen.findByText('26')).toBeTruthy()
 await userEvent.click(screen.getByText('Save research record'))
 expect(api).toHaveBeenCalledWith('/us/company/MCD/save',{project_id:undefined,snapshot_ids:['sec-fixed']})
 expect(await screen.findByText('record-one')).toBeTruthy()
})
it('submits CSV text verbatim with the source URL',async()=>{
 setLocale('en');vi.mocked(api).mockResolvedValue({financials:[],snapshot_ids:[]});render(<UsEquities/> )
 await userEvent.click(screen.getByText('Import prices'))
 await userEvent.type(screen.getByLabelText('Source URL'),'https://example.com/prices')
 await userEvent.type(screen.getByLabelText('CSV'),'date,open,high,low,close,volume{enter}2025-01-02,1,2,1,2,10')
 await userEvent.click(screen.getByText('Save price snapshot'))
 expect(api).toHaveBeenCalledWith('/us/company/MCD/prices',{source_url:'https://example.com/prices',text:'date,open,high,low,close,volume\n2025-01-02,1,2,1,2,10'})
})
