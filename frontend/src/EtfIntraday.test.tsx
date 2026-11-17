// @vitest-environment jsdom
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react'
import {afterEach,it,expect,vi} from 'vitest'
import EtfIntraday,{intradayEligible} from './EtfIntraday'
import {api} from './api'
import {setLocale} from './i18n'
vi.mock('./api',async()=>({...await vi.importActual('./api'),api:vi.fn()}))
afterEach(()=>{cleanup();vi.useRealTimers();vi.restoreAllMocks()})
it('keeps source quote precision in both languages and preserves old cached decimals',async()=>{
 setLocale('en');vi.mocked(api).mockResolvedValue({items:[
  {code:'510300',quote:{price:4.124,price_decimals:3}},
  {code:'159919',quote:{price:4.1,price_decimals:3}},
  {code:'510500',quote:{price:6.637}},
  {code:'588000',quote:{price:null}},
 ]})
 render(<EtfIntraday codes="510300,159919,510500,588000"/>);
 fireEvent.click(screen.getByText('Lightweight quotes'))
 expect(await screen.findByText('4.124')).toBeTruthy();expect(screen.getByText('4.100')).toBeTruthy()
 expect(screen.getByText('6.637')).toBeTruthy();expect(screen.queryByText('4.12')).toBeNull()
 setLocale('zh');expect(await screen.findByText('4.124')).toBeTruthy()
 expect(screen.getByRole('row',{name:/588000/}).textContent).toContain('—')
})
it('retains prior quotes on failure',async()=>{
 setLocale('en');vi.mocked(api).mockResolvedValue({items:[{code:'510300',quote:{price:4.12},comparison:{}}]})
 render(<EtfIntraday codes="510300"/>);fireEvent.click(screen.getByText('Lightweight quotes'));expect(await screen.findByText('4.12')).toBeTruthy()
 vi.mocked(api).mockRejectedValue(new Error('offline'));fireEvent.click(screen.getByText('Refresh lightweight quotes'))
 expect(await screen.findByRole('alert')).toBeTruthy();expect(screen.getByText('4.12')).toBeTruthy()
})
it('rejects late responses after switching codes',async()=>{
 let resolve!:(value:unknown)=>void
 vi.mocked(api).mockImplementationOnce(()=>new Promise(r=>{resolve=r})).mockResolvedValue({items:[{code:'510500'}]})
 const view=render(<EtfIntraday codes="510300"/>);view.rerender(<EtfIntraday codes="510500"/>);
 expect((await screen.findAllByText('510500')).length).toBeGreaterThan(0);resolve({items:[{code:'510300'}]});await waitFor(()=>expect(screen.queryAllByText('510300')).toHaveLength(0))
})
it('polls only visible valid sessions and resumes once',async()=>{
 vi.useFakeTimers();vi.setSystemTime(new Date('2026-11-06T10:00:00+08:00'));let visibility='visible';Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>visibility})
 vi.mocked(api).mockResolvedValue({items:[{code:'510300',quote:{session_valid:true,source_time:'2026-11-06T10:00:00+08:00'}}]})
 const {act}=await import('@testing-library/react')
 await act(async()=>{render(<EtfIntraday codes="510300"/>);await Promise.resolve()})
 fireEvent.click(screen.getByRole('checkbox'));vi.mocked(api).mockClear()
 visibility='hidden';await act(async()=>{vi.advanceTimersByTime(20000)});expect(api).not.toHaveBeenCalled()
 visibility='visible';await act(async()=>{document.dispatchEvent(new Event('visibilitychange'));await Promise.resolve()})
 expect(vi.mocked(api).mock.calls.filter(call=>call[0]==='/etf/intraday/refresh')).toHaveLength(1)
 vi.useRealTimers()
})

it('resumes after lunch using same-day source date and stops at close',()=>{
 const items=[{quote:{source_time:'2026-11-06T11:30:00+08:00',session_valid:false}}]
 expect(intradayEligible(items,new Date('2026-11-06T12:00:00+08:00'))).toBe(false)
 expect(intradayEligible(items,new Date('2026-11-06T13:00:00+08:00'))).toBe(true)
 expect(intradayEligible(items,new Date('2026-11-06T15:00:00+08:00'))).toBe(false)
})

it('recovers overnight sources at five-minute intervals and pauses on weekends',async()=>{
 setLocale('en');vi.useFakeTimers();vi.setSystemTime(new Date('2026-11-06T14:59:00+08:00'))
 Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>'visible'})
 vi.mocked(api).mockImplementation(async url=>url==='/etf/intraday/refresh'?{id:'done',status:'completed'}:{items:[{code:'510300',stale:true,quote:{source_time:'2026-11-06T14:59:00+08:00'}}]})
 const {act}=await import('@testing-library/react')
 await act(async()=>{render(<EtfIntraday codes="510300"/>);await Promise.resolve()})
 fireEvent.click(screen.getByRole('checkbox'));vi.mocked(api).mockClear()
 vi.setSystemTime(new Date('2026-11-07T10:00:00+08:00'))
 await act(async()=>{vi.advanceTimersByTime(60000)});expect(api).not.toHaveBeenCalled()
 vi.setSystemTime(new Date('2026-11-09T10:00:00+08:00'))
 await act(async()=>{vi.advanceTimersByTime(20000);await Promise.resolve()})
 expect(vi.mocked(api).mock.calls.filter(c=>c[0]==='/etf/intraday/refresh')).toHaveLength(1)
 await act(async()=>{vi.advanceTimersByTime(280000);await Promise.resolve()})
 expect(vi.mocked(api).mock.calls.filter(c=>c[0]==='/etf/intraday/refresh')).toHaveLength(1)
 await act(async()=>{vi.advanceTimersByTime(20000);await Promise.resolve()})
 expect(vi.mocked(api).mock.calls.filter(c=>c[0]==='/etf/intraday/refresh')).toHaveLength(2)
 expect(intradayEligible([{quote:{source_time:'2026-11-07T10:00:00+08:00'}}],new Date('2026-11-07T10:00:00+08:00'))).toBe(false)
})

it('tracks queued jobs and refreshes cache after completion',async()=>{
 vi.useFakeTimers();const {act}=await import('@testing-library/react')
 vi.mocked(api).mockImplementation(async url=>url==='/etf/intraday/refresh'?{id:'quote-job',status:'queued'}:url==='/etf/intraday/jobs/quote-job'?{id:'quote-job',status:'completed',bar_job_id:'bars'}:url==='/etf/intraday/jobs/bars'?{id:'bars',status:'completed'}:{items:[]})
 await act(async()=>{render(<EtfIntraday codes="510300"/>);await Promise.resolve()})
 await act(async()=>{fireEvent.click(screen.getByText('Refresh lightweight quotes'));await Promise.resolve()})
 expect(screen.getByRole('status').textContent).toContain('Queued')
 await act(async()=>{vi.advanceTimersByTime(2000);await Promise.resolve()})
 expect(api).toHaveBeenCalledWith('/etf/intraday/jobs/quote-job')
 await act(async()=>{vi.advanceTimersByTime(2000);await Promise.resolve()})
 expect(api).toHaveBeenCalledWith('/etf/intraday/jobs/bars');vi.useRealTimers()
})
it('shows actual window, sample dates, zero and missing amounts independently',async()=>{
 setLocale('en');vi.mocked(api).mockResolvedValue({items:[{code:'510300',comparison:{ratio:0,current_amount:0,historical_mean_amount:null,sample_count:1,window_start:'2026-10-08',window_end:'2026-11-05',sample_dates:['2026-10-19'],calendar_status:'unverified'}}]})
 render(<EtfIntraday codes="510300"/>);expect(await screen.findByText(/2026-10-08/)).toBeTruthy()
 fireEvent.click(screen.getByText('Samples, gaps and source evidence'))
 expect(screen.getByText(/Previous 20 source dates/)).toBeTruthy();fireEvent.click(screen.getByText('Actual valid sample dates'))
 expect(screen.getByText('2026-10-19')).toBeTruthy()
 const row=screen.getByRole('row',{name:/510300/});expect(row.textContent).toContain('0');expect(row.textContent).toContain('—')
 setLocale('zh');expect(await screen.findByText(/此前20个来源日期（日历未核验）/)).toBeTruthy()
})
