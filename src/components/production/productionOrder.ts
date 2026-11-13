import type { ProductionUnit } from '../../productionTypes';
export function compareProductionUnits(a:ProductionUnit,b:ProductionUnit):number{
  if(a.isCompleted!==b.isCompleted)return a.isCompleted?1:-1;
  const rank=(u:ProductionUnit)=>(u.manualOrder||0)>0?u.manualOrder!:Number.MAX_SAFE_INTEGER;
  return rank(a)-rank(b)||a.sortTimestamp-b.sortTimestamp||(a.createdAt||a.lastUpdated).localeCompare(b.createdAt||b.lastUpdated)||a.id.localeCompare(b.id);
}
export function movedTaskOrder(units:ProductionUnit[],source:string,target:string,placement:'before'|'after'):string[]{
  const order=[...units].filter(u=>!u.isCompleted).sort(compareProductionUnits).map(u=>u.id);
  if(source===target||!order.includes(source)||!order.includes(target))return order;
  order.splice(order.indexOf(source),1);order.splice(order.indexOf(target)+(placement==='after'?1:0),0,source);return order;
}
export function applyTaskOrder(units:ProductionUnit[],order:string[]):ProductionUnit[]{
  const ranks=new Map(order.map((id,index)=>[id,index+1]));
  return units.map(unit=>!unit.isCompleted&&ranks.has(unit.id)?{...unit,manualOrder:ranks.get(unit.id)}:unit);
}
