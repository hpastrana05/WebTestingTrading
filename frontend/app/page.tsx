import Link from "next/link";

const sections = [
  {
    href: "/strategies",
    title: "Strategies",
    text: "Create strategies with pandas-ta entry/exit rules, or use built-ins.",
  },
  {
    href: "/backtest",
    title: "Backtest",
    text: "Run historical tests with yfinance market data.",
  },
  {
    href: "/tuning",
    title: "Tuning",
    text: "Grid-search parameters to find stronger setups.",
  },
  {
    href: "/alerts",
    title: "Alerts",
    text: "Send Telegram messages and manage alert rules.",
  },
];

export default function HomePage() {
  return (
    <div>
      <section className="hero">
        <h1>Your private trading lab</h1>
        <p className="muted">
          Build strategies, backtest them, tune parameters, and push alerts to Telegram —
          all from a small stack you can host on a Raspberry Pi.
        </p>
      </section>

      <div className="grid">
        {sections.map((section) => (
          <Link key={section.href} href={section.href} className="card">
            <h2>{section.title}</h2>
            <p>{section.text}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
