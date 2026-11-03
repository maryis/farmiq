'use client';
import { useEffect, useState } from 'react';
import { apiGet, apiPost } from '@/lib/api';
import type { Risk } from '@/lib/types';
import { useDemoFarm } from '@/components/demo-hook';
import { useLocale } from '@/components/locale';

export default function HealthPage() {
  const { farmId } = useDemoFarm();
  const [risks, setRisks] = useState<Risk[]>([]);
  const { locale } = useLocale();
  const load = () => farmId && apiGet<Risk[]>(`/v1/farms/${farmId}/health-risks`).then(setRisks);
  useEffect(() => { load(); const timer = window.setInterval(load, 30000); return () => window.clearInterval(timer); }, [farmId]);
  async function feedback(id:string, outcome:string) { if (!farmId) return; await apiPost(`/v1/farms/${farmId}/health-risks/${id}/feedback`, {outcome}); load(); }
  const t = locale === 'nl';
  return <div className="content"><div className="eyebrow">HealthIQ</div><h1>{t ? 'Vroege gezondheidsrisico’s' : 'Early health-risk detection'}</h1><p className="sub">{t ? 'Persoonlijke baselines + transparante regels. Geen diagnose.' : 'Personal baselines + transparent rules. Not a diagnosis.'}</p>
    <div className="card"><div className="section-head"><h2>{t ? 'Actieve waarschuwingen' : 'Active alerts'}</h2><span className="muted">{risks.length}</span></div>
      {risks.length === 0 ? <div className="muted">{t ? 'Geen actieve waarschuwingen.' : 'No active alerts.'}</div> : risks.map(r => <div key={r.id} style={{borderTop:'1px solid var(--line)', padding:'16px 0'}}>
        <div style={{display:'flex',justifyContent:'space-between',gap:12}}><div><strong>{r.cow}</strong> · <span style={{textTransform:'capitalize'}}>{r.risk_type}</span></div><span className={`badge ${r.severity}`}>{Math.round(r.score)}/100</span></div>
        <div className="muted" style={{fontSize:13,margin:'8px 0'}}>{r.evidence.map(e=>e.message).filter(Boolean).join(' · ')}</div>
        <div className="toolbar"><button className="secondary" onClick={()=>feedback(r.id,'confirmed')}>{t?'Bevestigd':'Confirmed'}</button><button className="secondary" onClick={()=>feedback(r.id,'dismissed')}>{t?'Niet correct':'Dismiss'}</button><button className="secondary" onClick={()=>feedback(r.id,'not_sure')}>{t?'Niet zeker':'Not sure'}</button></div>
      </div>)}
    </div>
  </div>;
}
