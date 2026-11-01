/** A response may update its view only while its originating scope is current. */
export function createResponseScope(){
 let generation=0;
 return {begin:()=>++generation,invalidate:()=>{generation++},isCurrent:(ticket:number)=>ticket===generation};
}
