import assert from 'node:assert/strict';
import {test} from 'node:test';
import {compareProductionUnits,movedTaskOrder,applyTaskOrder} from './productionOrder.ts';
import type {ProductionUnit} from '../../productionTypes.ts';
const unit=(id:string,date:string,manualOrder=0,isCompleted=false)=>({id,scheduledDate:date,sortTimestamp:Date.parse(date),createdAt:id,lastUpdated:id,manualOrder,isCompleted} as ProductionUnit);
test('card order defaults to date, manual positions override dates, registered cards remain last',()=>{
 const rows=[unit('b','2027-01-01',1),unit('a','2026-10-11'),unit('c','2026-01-01',2,true)];
 assert.deepEqual(rows.sort(compareProductionUnits).map(u=>u.id),['b','a','c']);
});
test('filtered drag moves relative to its target and preserves hidden task ordering',()=>{
 const rows=['a','b','c','d'].map((id,index)=>unit(id,`2026-10-${11+index}`));
 const order=movedTaskOrder(rows,'d','b','before');assert.deepEqual(order,['a','d','b','c']);
 assert.deepEqual(applyTaskOrder(rows,order).sort(compareProductionUnits).map(u=>u.id),order);
 assert.deepEqual(movedTaskOrder(rows,'d','b','after'),['a','b','d','c']);
});
