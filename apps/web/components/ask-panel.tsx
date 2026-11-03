'use client';

import { FormEvent, useState } from 'react';
import { Send } from 'lucide-react';
import { apiPost } from '@/lib/api';
import { useLocale } from './locale';

export function AskPanel({ farmId, compact = false }: { farmId: string; compact?: boolean }) {
  const { locale } = useLocale();
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<{ role: 'user' | 'assistant'; text: string; sources?: {title:string;url:string}[] }[]>([
    { role: 'assistant', text: locale === 'nl' ? 'Vraag mij naar je kudde, gezondheidsrisico’s of voer.' : 'Ask me about your herd, health risks or feed.' }
  ]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput('');
    setMessages((m) => [...m, { role: 'user', text }]);
    setBusy(true);
    try {
      const result = await apiPost<{ answer: string; sources: {title:string;url:string}[] }>('/v1/chat', { farm_id: farmId, message: text, language: locale });
      setMessages((m) => [...m, { role: 'assistant', text: result.answer, sources: result.sources }]);
    } catch {
      setMessages((m) => [...m, { role: 'assistant', text: locale === 'nl' ? 'Ask-IQ is tijdelijk niet beschikbaar.' : 'Ask-IQ is temporarily unavailable.' }]);
    } finally { setBusy(false); }
  }

  return <div className={compact ? '' : 'card'}>
    {!compact && <div className="section-head"><h2>Ask-IQ</h2><span className="muted">NL / EN</span></div>}
    <div className="chat-log">
      {messages.map((m, i) => <div key={i} className={`message ${m.role}`}>
        {m.text}
        {m.sources?.length ? <div className="source-list">{m.sources.map((s) => <div key={s.url}><a href={s.url} target="_blank">{s.title}</a></div>)}</div> : null}
      </div>)}
      {busy && <div className="message assistant">…</div>}
    </div>
    <form className="chat-input" onSubmit={submit}>
      <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={locale === 'nl' ? 'Vraag iets over je kudde…' : 'Ask anything about your herd…'} />
      <button className="primary" aria-label="Send"><Send size={17}/></button>
    </form>
  </div>;
}
