import Link from "next/link";
import { ReactNode } from "react";
import ThemeControls from "@/components/ThemeControls";
import { THEME_BOOT_SCRIPT } from "@/lib/theme";
import "./globals.css";

const links = [
  { href: "/", label: "Home" },
  { href: "/strategies", label: "Strategies" },
  { href: "/backtest", label: "Backtest" },
  { href: "/tuning", label: "Tuning" },
  { href: "/alerts", label: "Alerts" },
];

export const metadata = {
  title: "Trading Lab",
  description: "Private trading strategies, backtests, tuning, and Telegram alerts",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" data-theme="forest" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body>
        <div className="shell">
          <header className="topbar">
            <div className="brand">
              <span className="brand-mark">TL</span>
              <div>
                <strong>Trading Lab</strong>
                <p>Private research workspace</p>
              </div>
            </div>
            <div className="topbar-right">
              <nav>
                {links.map((link) => (
                  <Link key={link.href} href={link.href}>
                    {link.label}
                  </Link>
                ))}
              </nav>
              <ThemeControls />
            </div>
          </header>
          <main>{children}</main>
        </div>
      </body>
    </html>
  );
}
