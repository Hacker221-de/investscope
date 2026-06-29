"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navigation = [
  ["/", "Overview", "D"],
  ["/assets", "Assets", "A"],
  ["/recommendations", "Recommendations", "R"],
  ["/portfolio", "Portfolio", "P"],
  ["/political-events", "Political events", "E"],
  ["/backtesting", "Backtesting", "B"],
  ["/settings", "Settings", "S"],
] as const;

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <Link href="/" className="brand" aria-label="InvestScope dashboard">
        <span className="brand-mark">IS</span>
        <span>
          <strong>InvestScope</strong>
          <small>Research terminal</small>
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
          <strong>Demo environment</strong>
          <small>No live market feed</small>
        </div>
      </div>
    </aside>
  );
}

