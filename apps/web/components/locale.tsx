'use client';

import { createContext, useContext, useEffect, useState } from 'react';

type Locale = 'en' | 'nl';
const LocaleContext = createContext<{ locale: Locale; toggle: () => void }>({ locale: 'en', toggle: () => {} });

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocale] = useState<Locale>('en');
  useEffect(() => {
    const saved = localStorage.getItem('farmiq-locale');
    if (saved === 'nl' || saved === 'en') setLocale(saved);
  }, []);
  const toggle = () => setLocale((current) => {
    const next = current === 'en' ? 'nl' : 'en';
    localStorage.setItem('farmiq-locale', next);
    return next;
  });
  return <LocaleContext.Provider value={{ locale, toggle }}>{children}</LocaleContext.Provider>;
}

export const useLocale = () => useContext(LocaleContext);
