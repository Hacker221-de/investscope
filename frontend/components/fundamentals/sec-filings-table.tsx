"use client";

import { useEffect, useState } from "react";

import { getFundamentalErrorMessage, getFundamentalFilings } from "@/lib/fundamentals-api";
import { formatDate } from "@/lib/fundamental-formatters";
import type { FundamentalFiling } from "@/lib/types";

export function SecFilingsTable({ symbol }: { symbol: string }) {
  const [filings, setFilings] = useState<FundamentalFiling[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getFundamentalFilings(symbol, { limit: 8 })
      .then((response) => {
        if (active) setFilings(response);
      })
      .catch((reason: unknown) => {
        if (active) setError(getFundamentalErrorMessage(reason, "Не удалось загрузить отчётность SEC"));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [symbol]);

  return (
    <section className="panel wide-panel sec-filings" aria-labelledby="sec-filings-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">SEC EDGAR</p>
          <h2 id="sec-filings-title">Последняя отчётность</h2>
        </div>
        <span className="timestamp">До 8 последних документов</span>
      </div>
      {loading && <div className="fundamental-inline-state" role="status">Загрузка отчётности…</div>}
      {!loading && error && <div className="fundamental-inline-state error" role="alert">{error}</div>}
      {!loading && !error && filings?.length === 0 && <div className="fundamental-inline-state">Отчётности SEC пока не загружены</div>}
      {!loading && !error && filings && filings.length > 0 && (
        <div className="table-wrap">
          <table className="sec-filings-table">
            <thead><tr><th>Форма</th><th>Дата подачи</th><th>Отчётный период</th><th>Accession number</th><th>Документ</th><th>Статус</th></tr></thead>
            <tbody>{filings.map((filing) => (
              <tr key={filing.id}>
                <td><strong>{filing.form}</strong></td>
                <td>{formatDate(filing.filing_date)}</td>
                <td>{formatDate(filing.report_date)}</td>
                <td className="breakable-id">{filing.accession_number}</td>
                <td>
                  {filing.filing_url ? (
                    <a className="text-link" href={filing.filing_url} target="_blank" rel="noopener noreferrer">
                      {filing.primary_document ?? "Открыть в SEC"}
                    </a>
                  ) : filing.primary_document ?? "—"}
                </td>
                <td>{filing.is_amendment ? <span className="quality-badge warning">Поправка</span> : "Исходный"}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}
