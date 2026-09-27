"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { fetchMarketApi } from "@/lib/api";
import type { ProviderMarketDataStatus } from "@/lib/types";

type NavItem = { href: string; label: string; icon: ReactNode };

const icons = {
  overview: (
    <>
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </>
  ),
  backtest: (
    <>
      <path d="M3 3v18h18" />
      <path d="M7 15l4-5 3 3 5-7" />
    </>
  ),
  portfolio: (
    <>
      <path d="M21 12a9 9 0 1 1-9-9" />
      <path d="M21 3v9h-9" />
    </>
  ),
  assets: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3.5-3.5" />
    </>
  ),
  events: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 10h18M8 3v4M16 3v4" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" />
    </>
  ),
};

const groups: { title: string; items: NavItem[] }[] = [
  {
    title: "Анализ",
    items: [
      { href: "/", label: "Обзор", icon: icons.overview },
      { href: "/backtesting", label: "Бэктест портфеля", icon: icons.backtest },
      { href: "/portfolio", label: "Портфели", icon: icons.portfolio },
    ],
  },
  {
    title: "Данные",
    items: [
      { href: "/assets", label: "Инструменты", icon: icons.assets },
      { href: "/political-events", label: "События рынка", icon: icons.events },
    ],
  },
];

const settingsItem: NavItem = { href: "/settings", label: "Настройки", icon: icons.settings };

const providerLabels: Record<string, string> = {
  demo: "Демо-данные",
  alpha_vantage: "Alpha Vantage",
};

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavLink({ item, pathname }: { item: NavItem; pathname: string }) {
  const active = isActive(pathname, item.href);
  return (
    <Link
      href={item.href}
      className={active ? "nav-link active" : "nav-link"}
      aria-current={active ? "page" : undefined}
    >
      <svg
        className="nav-icon"
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        focusable="false"
      >
        {item.icon}
      </svg>
      {item.label}
    </Link>
  );
}

function DataSources() {
  const [status, setStatus] = useState<ProviderMarketDataStatus | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchMarketApi<ProviderMarketDataStatus>("/providers/market-data/status")
      .then((value) => { if (!cancelled) setStatus(value); })
      .catch(() => { if (!cancelled) setError(true); });
    return () => { cancelled = true; };
  }, []);

  let row: ReactNode;
  if (error) {
    row = <div className="source-row"><span className="status-dot unknown" /><span>Статус недоступен</span></div>;
  } else if (!status) {
    row = <div className="source-row"><span className="status-dot unknown" /><span>Загрузка…</span></div>;
  } else {
    const name = providerLabels[status.configured_provider] ?? status.configured_provider;
    row = (
      <div className="source-row">
        <span className={status.available ? "status-dot" : "status-dot unavailable"} />
        <span>{name}</span>
        <em>{status.available ? "доступен" : "ограничен"}</em>
      </div>
    );
  }

  return (
    <section className="sidebar-sources" aria-label="Источники данных">
      <span className="sidebar-sources-title">Источники данных</span>
      {row}
    </section>
  );
}

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <Link href="/" className="brand" aria-label="InvestScope — Обзор">
        <svg className="brand-mark" width="30" height="30" viewBox="0 0 30 30" aria-hidden="true" focusable="false">
          <rect x="3" y="15" width="5" height="11" rx="1.5" fill="var(--accent)" />
          <rect x="11" y="9" width="5" height="17" rx="1.5" fill="var(--accent)" opacity=".85" />
          <rect x="19" y="4" width="5" height="22" rx="1.5" fill="var(--accent-hover)" />
        </svg>
        <strong>InvestScope</strong>
      </Link>
      <nav className="nav" aria-label="Основная навигация">
        {groups.map((group) => (
          <div className="nav-group" key={group.title}>
            <span className="nav-group-title">{group.title}</span>
            {group.items.map((item) => <NavLink item={item} pathname={pathname} key={item.href} />)}
          </div>
        ))}
        <div className="nav-group nav-group-bottom">
          <NavLink item={settingsItem} pathname={pathname} />
        </div>
      </nav>
      <DataSources />
    </aside>
  );
}
