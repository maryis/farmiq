'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ArrowUpRight, Milk, TriangleAlert, Users, WalletCards } from 'lucide-react';
import { apiGet } from '@/lib/api';
import type { Dashboard } from '@/lib/types';
import { useDemoFarm } from '@/components/demo-hook';
import { AskPanel } from '@/components/ask-panel';
import { useLocale } from '@/components/locale';

export default function TodayPage() {
  const { farmId, error } = useDemoFarm();
  const [data, setData] = useState<Dashboard>();
  const { locale } = useLocale();
  useEffect(() => { if (!farmId) return; const load = () => apiGet<Dashboard>(`/v1/farms/${farmId}/dashboard`).then(setData); load(); const timer = window.setInterval(load, 30000); return () => window.clearInterval(timer); }, [farmId]);
  if (error) return <div className="content"><div className="error">{error}</div></div>;
  if (!data) return <div className="loading">Loading live demo farm…</div>;
  const t = locale === 'nl';
  return <div className="content">
    <div className="eyebrow">{t ? 'Vandaag' : 'Today'}</div>
    <h1>{t ? 'Wat heeft vandaag je aandacht nodig?' : 'What needs your attention today?'}</h1>
    <p className="sub">{t ? 'Live overzicht van gezondheid, voeding en voorraad.' : 'Live view of health, feeding and inventory.'}</p>

    <div className="grid-stats">
      <div className="card"><div className="stat-label">{t ? 'Koeien' : 'Cows'}</div><div className="stat-value">{data.stats.animals}</div><div className="stat-note">{t ? 'actief in kudde' : 'active in herd'}</div></div>
      <div className="card"><div className="stat-label">{t ? 'Actieve waarschuwingen' : 'Active alerts'}</div><div className="stat-value">{data.stats.active_alerts}</div><div className="stat-note">{data.stats.high_alerts} {t ? 'hoog risico' : 'high risk'}</div></div>
      <div className="card"><div className="stat-label">{t ? 'Melk vs gisteren' : 'Milk vs yesterday'}</div><div className="stat-value">+{data.stats.milk_change_pct}%</div><div className="stat-note">{t ? 'demo kudde' : 'demo herd'}</div></div>
      <div className="card"><div className="stat-label">{t ? 'FeedIQ kans' : 'FeedIQ opportunity'}</div><div className="stat-value">€{data.feed_opportunity?.saving_eur_per_cow_day.toFixed(2) ?? '—'}</div><div className="stat-note">{t ? 'per koe / dag' : 'per cow / day'}</div></div>
    </div>

    <div className="two-col">
      <div className="card">
        <div className="section-head"><h2>{t ? 'Heeft aandacht nodig' : 'Needs attention'}</h2><Link href="/health">HealthIQ <ArrowUpRight size={14}/></Link></div>
        {data.risks.slice(0, 5).map((risk) => <div className="risk-row" key={risk.id}>
          <div className="cow-id">{risk.cow}</div>
          <div><div className="risk-name">{risk.risk_type}</div><div className="risk-evidence">{risk.evidence[0]?.message || (t ? 'Persoonlijke baseline afwijking' : 'Personal baseline anomaly')}</div></div>
          <span className={`badge ${risk.severity}`}>{Math.round(risk.score)}</span>
        </div>)}
      </div>
      <div className="card">
        <div className="section-head"><h2>FeedIQ</h2><Link href="/feed">{t ? 'Open' : 'Open'} <ArrowUpRight size={14}/></Link></div>
        <div className="muted">{data.feed_opportunity?.group_name}</div>
        <div className="feed-saving">€{data.feed_opportunity?.saving_eur_per_month_group.toLocaleString() ?? '—'}</div>
        <div className="muted">{t ? 'geschatte maandelijkse groepsbesparing' : 'estimated monthly group saving'}</div>
        <div className="callout" style={{marginTop:16}}>{t ? 'FeedIQ optimaliseert met DM, VEM, DVE, NDF, OEB, voorraad en beperkte dagelijkse rantsoenwijzigingen.' : 'FeedIQ optimizes with DM, VEM, DVE, NDF, OEB, inventory and bounded daily ration changes.'}</div>
      </div>
    </div>

    <div className="two-col">
      <div className="card">
        <div className="section-head"><h2>{t ? 'Voorraad' : 'Inventory'}</h2><Link href="/inventory">{t ? 'Alles bekijken' : 'View all'}</Link></div>
        {data.inventory.slice(0, 4).map((item) => <div className="inventory-row" key={item.name}>
          <div className="inventory-top"><strong>{item.name}</strong><span className={item.warning ? 'danger' : ''}>{item.days_remaining} {t ? 'dagen' : 'days'}</span></div>
          <div className="progress"><div style={{width: `${Math.min(100, item.days_remaining / 35 * 100)}%`}}/></div>
        </div>)}
      </div>
      <div className="card chat-box"><div className="section-head"><h2>Ask-IQ</h2><span className="muted">Qwen-ready + RAG</span></div>{farmId && <AskPanel farmId={farmId} compact />}</div>
    </div>
  </div>;
}
