import Link from "next/link";
import { ReactNode } from "react";
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
    <html lang="en">
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
            <nav>
              {links.map((link) => (
                <Link key={link.href} href={link.href}>
                  {link.label}
                </Link>
              ))}
            </nav>
          </header>
          <main>{children}</main>
        </div>
      </body>
    </html>
  );
}
