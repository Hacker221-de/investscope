import {
  formatDateTimeUtc,
  formatExactDecimal,
  formatIngestionMethod,
} from "@/lib/fundamental-formatters";
import type { FundamentalMetricPoint, FundamentalProvenanceFact } from "@/lib/types";

function safeFilename(value: string | null): string {
  return value?.split(/[\\/]/).at(-1) ?? "—";
}

function ProvenanceTable({
  facts,
  usedIds,
}: {
  facts: FundamentalProvenanceFact[];
  usedIds: Set<number>;
}) {
  return (
    <div className="table-wrap audit-table-wrap">
      <table className="provenance-table">
        <thead><tr><th>Значение</th><th>SEC concept</th><th>Период</th><th>Форма</th><th>Accession number</th><th>Публикация</th><th>Роль</th><th>Получение</th></tr></thead>
        <tbody>{facts.map((fact) => (
          <tr key={fact.id}>
            <td className="audit-number">{formatExactDecimal(fact.value, fact.unit)}</td>
            <td>{fact.taxonomy}:{fact.concept}</td>
            <td>{fact.period_start ?? "instant"} — {fact.period_end}</td>
            <td>{fact.filing_url ? <a className="text-link" href={fact.filing_url} target="_blank" rel="noopener noreferrer">{fact.form}</a> : fact.form}{fact.is_amendment && <span className="cell-note">Поправка</span>}</td>
            <td className="breakable-id">{fact.accession_number}</td>
            <td>{formatDateTimeUtc(fact.acceptance_datetime ?? fact.filed_at)}</td>
            <td>{usedIds.has(fact.id) ? <span className="quality-badge positive">В расчёте</span> : <span className="quality-badge neutral">Только аудит</span>}</td>
            <td>{formatIngestionMethod(fact.ingestion_method)}<span className="cell-note breakable-id">{safeFilename(fact.source_filename)}</span></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

export function MetricProvenance({ point }: { point: FundamentalMetricPoint }) {
  const selected = point.selected_fact ? [point.selected_fact] : [];
  const usedIds = new Set(point.calculation_components.map((component) => component.id));
  if (!point.derived && point.selected_fact) usedIds.add(point.selected_fact.id);
  const count = selected.length + point.alternative_facts.length + point.source_facts.length;

  if (count === 0) return null;
  return (
    <details className="fundamental-disclosure">
      <summary>Источники и аудит <span>{count}</span></summary>
      <div className="audit-groups">
        {selected.length > 0 && <section><h5>Выбранный SEC-факт</h5><ProvenanceTable facts={selected} usedIds={usedIds} /></section>}
        {point.alternative_facts.length > 0 && <section><h5>Альтернативные факты</h5><ProvenanceTable facts={point.alternative_facts} usedIds={usedIds} /></section>}
        {point.source_facts.length > 0 && <section><h5>Полный аудиторский список</h5><p>Содержит рассмотренные факты, в том числе не вошедшие в формулу.</p><ProvenanceTable facts={point.source_facts} usedIds={usedIds} /></section>}
      </div>
    </details>
  );
}
