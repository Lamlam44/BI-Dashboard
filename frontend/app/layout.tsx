import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'BI Dashboard',
  description: 'Business Intelligence Dashboard - Sales, Trends & Analytics',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
