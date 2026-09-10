import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Short Fiction Library',
  description: 'A searchable library of individual stories and short works.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
