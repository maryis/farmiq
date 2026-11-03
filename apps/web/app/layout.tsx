import type { Metadata } from 'next';
import './globals.css';
import { LocaleProvider } from '@/components/locale';
import { Shell } from '@/components/shell';

export const metadata: Metadata = {
  title: 'FarmIQ — Dairy intelligence',
  description: 'FeedIQ, HealthIQ and Ask-IQ for dairy farms',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><LocaleProvider><Shell>{children}</Shell></LocaleProvider></body></html>;
}
