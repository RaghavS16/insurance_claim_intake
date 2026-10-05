import type { Metadata } from "next";
import "./globals.css";
export const metadata:Metadata={title:"Flowa Insurance Claims",description:"Production insurance claim intake and adjuster workspace"};
const themeScript = `
(function() {
  try {
    var saved = localStorage.getItem('flowa-theme') || 'system';
    var isDark = saved === 'dark' || (saved === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    if (saved !== 'system') {
      document.documentElement.setAttribute('data-theme', saved);
    }
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  } catch (e) {}
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
