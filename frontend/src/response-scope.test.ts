import {describe,expect,it} from 'vitest';
import {createResponseScope} from './response-scope';
describe('blind-session response ownership',()=>{
 it('discards a delayed reveal response after leaving the session',async()=>{const scope=createResponseScope();const ticket=scope.begin();let resolve!:(value:string)=>void;let visibleSession:string|null=null;const response=new Promise<string>(done=>{resolve=done}).then(value=>{if(scope.isCurrent(ticket))visibleSession=value});scope.invalidate();resolve('revealed old session');await response;expect(visibleSession).toBeNull()});
 it('accepts only the new record session when responses arrive out of order',async()=>{const scope=createResponseScope();const old=scope.begin();scope.invalidate();const current=scope.begin();let session='new record';await Promise.resolve().then(()=>{if(scope.isCurrent(old))session='old record'});expect(session).toBe('new record');expect(scope.isCurrent(current)).toBe(true)});
});
