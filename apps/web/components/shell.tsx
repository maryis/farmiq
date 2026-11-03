'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Activity, Bot, Boxes, HeartPulse, Home, PlugZap, Salad, Settings, Users } from 'lucide-react';
import { useLocale } from './locale';

const links = [
  ['/', 'Today', Home],
  ['/herd', 'Herd', Users],
  ['/health', 'HealthIQ', HeartPulse],
  ['/feed', 'FeedIQ', Salad],
  ['/inventory', 'Inventory', Boxes],
  ['/ask', 'Ask-IQ', Bot],
  ['/integrations', 'Integrations', PlugZap],
] as const;

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { locale, toggle } = useLocale();
  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">IQ</span><span>FarmIQ</span></div>
      <nav className="nav">
        {links.map(([href, label, Icon]) => <Link key={href} className={path === href ? 'active' : ''} href={href}><Icon size={18}/><span>{label}</span></Link>)}
      </nav>
      <div className="sidebar-foot">Decision support for dairy farms.<br/>Not a veterinary diagnosis.</div>
    </aside>
    <main className="main">
      <header className="topbar">
        <div className="topbar-title">Green Meadow Dairy</div>
        <div className="top-actions"><span className="demo-pill">LIVE DEMO</span><button className="lang" onClick={toggle}>{locale === 'en' ? 'NL' : 'EN'}</button></div>
      </header>
      {children}
    </main>
  </div>;
}
