'use client';
import { useEffect, useState } from 'react';
import { apiGet, apiPost } from '@/lib/api';
import { useDemoFarm } from '@/components/demo-hook';
import { useLocale } from '@/components/locale';

type Group = {id:string;name:string;stage:string;target_dmi_kg:number};
type Result = {group_name:string;cost_current_eur_per_cow_day:number;cost_recommended_eur_per_cow_day:number;saving_eur_per_cow_day:number;saving_eur_per_month_group:number;items:{name:string;current_kg_dm:number;recommended_kg_dm:number;change_kg_dm:number}[];explanation:string[];disclaimer:string;totals:Record<string,number>;requirements:Record<string,number>};

export default function FeedPage(){
  const {farmId}=useDemoFarm(); const {locale}=useLocale(); const [groups,setGroups]=useState<Group[]>([]); const [groupId,setGroupId]=useState(''); const [milkPrice,setMilkPrice]=useState(.47); const [result,setResult]=useState<Result>(); const [busy,setBusy]=useState(false);
  useEffect(()=>{if(farmId) apiGet<Group[]>(`/v1/farms/${farmId}/feed/groups`).then(g=>{setGroups(g); const high=g.find(x=>x.stage==='high')||g[0]; if(high)setGroupId(high.id);});},[farmId]);
  async function run(){if(!farmId||!groupId)return;setBusy(true);try{setResult(await apiPost<Result>(`/v1/farms/${farmId}/feed/groups/${groupId}/optimize`,{milk_price_eur_per_kg:milkPrice,horizon_days:7,persist:false,price_overrides:{}}));}finally{setBusy(false)}}
  useEffect(()=>{if(groupId)run();},[groupId]); const t=locale==='nl';
  return <div className="content"><div className="eyebrow">FeedIQ</div><h1>{t?'Adaptieve rantsoenoptimalisatie':'Adaptive ration optimization'}</h1><p className="sub">{t?'Kostenefficiënt binnen expliciete voedings-, voorraad- en wijzigingsbeperkingen.':'Cost-efficient within explicit nutrition, inventory and change constraints.'}</p>
    <div className="toolbar"><select value={groupId} onChange={e=>setGroupId(e.target.value)}>{groups.map(g=><option value={g.id} key={g.id}>{g.name}</option>)}</select><label className="secondary">{t?'Melkprijs':'Milk price'} € <input style={{border:0,width:65}} type="number" step="0.01" value={milkPrice} onChange={e=>setMilkPrice(Number(e.target.value))}/></label><button className="primary" onClick={run}>{busy?'…':t?'Optimaliseer':'Optimize'}</button></div>
    {result && <><div className="grid-stats"><div className="card"><div className="stat-label">{t?'Huidige kosten':'Current cost'}</div><div className="stat-value">€{result.cost_current_eur_per_cow_day.toFixed(2)}</div></div><div className="card"><div className="stat-label">{t?'Aanbevolen':'Recommended'}</div><div className="stat-value">€{result.cost_recommended_eur_per_cow_day.toFixed(2)}</div></div><div className="card"><div className="stat-label">{t?'Besparing / koe / dag':'Saving / cow / day'}</div><div className="stat-value">€{result.saving_eur_per_cow_day.toFixed(2)}</div></div><div className="card"><div className="stat-label">{t?'Maand / groep':'Month / group'}</div><div className="stat-value">€{result.saving_eur_per_month_group.toLocaleString()}</div></div></div>
    <div className="two-col"><div className="card table-wrap"><div className="section-head"><h2>{t?'Rantsoen':'Ration'}</h2><span className="muted">kg DM / cow / day</span></div><table><thead><tr><th>{t?'Ingrediënt':'Ingredient'}</th><th>{t?'Huidig':'Current'}</th><th>{t?'Advies':'Recommended'}</th><th>{t?'Verschil':'Change'}</th></tr></thead><tbody>{result.items.map(i=><tr key={i.name}><td><strong>{i.name}</strong></td><td>{i.current_kg_dm}</td><td>{i.recommended_kg_dm}</td><td className={i.change_kg_dm<0?'danger':'good'}>{i.change_kg_dm>0?'+':''}{i.change_kg_dm}</td></tr>)}</tbody></table></div><div className="card"><h2>{t?'Waarom dit advies?':'Why this recommendation?'}</h2>{result.explanation.map(x=><p className="muted" style={{fontSize:13,lineHeight:1.5}} key={x}>{x}</p>)}<div className="callout">{result.disclaimer}</div></div></div></>}
  </div>;
}
