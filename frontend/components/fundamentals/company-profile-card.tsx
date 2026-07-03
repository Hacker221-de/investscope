"use client";

import { useEffect, useState } from "react";

import { getFundamentalErrorMessage, getFundamentalProfile } from "@/lib/fundamentals-api";
import {
  formatDateTimeUtc,
  formatIngestionMethod,
  formatProvider,
} from "@/lib/fundamental-formatters";
import type { FundamentalCompanyProfile } from "@/lib/types";

export function CompanyProfileCard({ symbol }: { symbol: string }) {
  const [profile, setProfile] = useState<FundamentalCompanyProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getFundamentalProfile(symbol)
      .then((response) => {
        if (active) setProfile(response);
      })
      .catch((reason: unknown) => {
        if (active) setError(getFundamentalErrorMessage(reason, "Не удалось загрузить профиль компании"));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [symbol]);

  if (loading) {
    return <section className="panel fundamental-state fundamental-profile-state" role="status">Загрузка профиля компании…</section>;
  }
  if (error) {
    return <section className="panel fundamental-state fundamental-profile-state error" role="alert">{error}</section>;
  }
  if (!profile) {
    return <section className="panel fundamental-state fundamental-profile-state">Профиль компании пока не загружен</section>;
  }

  const sourceTime = profile.imported_at ?? profile.received_at;
  return (
    <section className="panel fundamental-profile" aria-labelledby="company-profile-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Профиль эмитента</p>
          <h2 id="company-profile-title">{profile.legal_name}</h2>
        </div>
        <span className="source-badge">{formatProvider(profile.provider)}</span>
      </div>
      <div className="fundamental-profile-grid">
        <div><span>Тикер</span><strong>{profile.tickers.join(", ") || symbol.toUpperCase()}</strong></div>
        <div><span>Биржа</span><strong>{profile.exchanges.join(", ") || "—"}</strong></div>
        <div><span>CIK</span><strong>{profile.cik}</strong></div>
        <div><span>SIC</span><strong>{[profile.sic, profile.sic_description].filter(Boolean).join(" · ") || "—"}</strong></div>
        <div><span>Конец финансового года</span><strong>{profile.fiscal_year_end || "—"}</strong></div>
        <div><span>Источник обновлён</span><strong>{formatDateTimeUtc(sourceTime)}</strong></div>
      </div>
      <p className="fundamental-source-note">{formatIngestionMethod(profile.ingestion_method)}</p>
    </section>
  );
}
