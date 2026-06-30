"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navigation = [
  ["/", "Обзор", "О"],
  ["/assets", "Активы", "А"],
  ["/recommendations", "Аналитические рейтинги", "Р"],
  ["/portfolio", "Портфель", "П"],
  ["/political-events", "Политические события", "С"],
  ["/backtesting", "Историческое тестирование", "Т"],
  ["/settings", "Настройки", "Н"],
] as const;

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <Link href="/" className="brand" aria-label="Обзор InvestScope">
        <span className="brand-mark">IS</span>
        <span>
          <strong>InvestScope</strong>
          <small>Аналитическая платформа</small>
        </span>
      </Link>
      <nav className="nav" aria-label="Primary navigation">
        {navigation.map(([href, label, icon]) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link href={href} className={active ? "nav-link active" : "nav-link"} key={href}>
              <span className="nav-icon">{icon}</span>
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="sidebar-status">
        <span className="status-dot" />
        <div>
          <strong>Демонстрационные данные</strong>
          <small>Нет потока котировок</small>
        </div>
      </div>
    </aside>
  );
}
