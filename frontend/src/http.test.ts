import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {request} from './http';
beforeEach(()=>{vi.stubGlobal('window',globalThis)});afterEach(()=>{vi.unstubAllGlobals()});
describe('API transport boundaries',()=>{
 it('keeps evidence import text unchanged',async()=>{const raw='{\"price\":5.0,\"sha256\":\"fixed\"}';const fetcher=vi.fn().mockResolvedValue(new Response('{\"id\":\"replay\"}',{status:202}));vi.stubGlobal('fetch',fetcher);expect(await request('/import',{method:'POST',body:raw})).toEqual({id:'replay'});expect(fetcher.mock.calls[0][0]).toBe('/api/import');expect(fetcher.mock.calls[0][1].body).toBe(raw)});
 it('reports validation fields rather than hiding request failures',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:[{loc:['body','start_date'],msg:'outside snapshot'}]}),{status:422})));await expect(request('/bridge/backtests',{method:'POST',body:'{}'})).rejects.toThrow('start_date：outside snapshot')});
 it('does not turn cancelled stale requests into data or source fallback',async()=>{const controller=new AbortController();controller.abort();vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new DOMException('Cancelled','AbortError')));await expect(request('/runs/old',{signal:controller.signal})).rejects.toMatchObject({name:'AbortError'})});
 it('rejects HTML instead of pretending that a service returned an empty archive',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('<html>frontend fallback</html>')));await expect(request('/runs')).rejects.toThrow('服务未返回有效数据')});
});
