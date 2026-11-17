// @vitest-environment jsdom
import {render,screen,fireEvent,cleanup} from '@testing-library/react'
import {afterEach,it,expect,vi} from 'vitest'
import EtfGettingStarted from './EtfGettingStarted'
import {api} from './api'
import {setLocale} from './i18n'
vi.mock('./api',async()=>({...await vi.importActual('./api'),api:vi.fn()}))
afterEach(()=>{cleanup();vi.clearAllMocks()})
it('opens an explicitly synthetic demo only on request and supports guide and language controls',async()=>{
 setLocale('en')
 vi.mocked(api).mockResolvedValue({synthetic:true,clock:'2025-03-28T10:32:00+08:00',source:'synthetic',input_sha256:'abc',inputs:{quote:{price:4.123,price_decimals:3},history:{rows:[]}},comparison:{ratio:1.5,sample_count:20}})
 render(<EtfGettingStarted/>);expect(api).not.toHaveBeenCalled()
 fireEvent.click(screen.getByText('Collapse guide'));expect(screen.queryByText(/Choose a research project/)).toBeNull()
 fireEvent.click(screen.getByText('Open guide'));expect(screen.getByText(/Choose a research project/)).toBeTruthy()
 fireEvent.click(screen.getByText('View synthetic demo'));expect(await screen.findByText('4.123')).toBeTruthy()
 expect(api).toHaveBeenCalledExactlyOnceWith('/etf/intraday-demo')
 expect(screen.getByText(/without network access/)).toBeTruthy()
 setLocale('zh');expect(await screen.findByText('合成演示 · 人工数据')).toBeTruthy()
 fireEvent.click(screen.getByText('关闭合成演示'));expect(screen.queryByText('4.123')).toBeNull()
})
