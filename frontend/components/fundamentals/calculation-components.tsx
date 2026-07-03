import {
  formatDate,
  formatDerivationMethod,
  formatExactDecimal,
  formatFiscalPeriod,
  formatIngestionMethod,
} from "@/lib/fundamental-formatters";
import type { FundamentalMetricPoint } from "@/lib/types";

function safeFilename(value: string | null): string {
  return value?.split(/[\\/]/).at(-1) ?? "—";
}

export function CalculationComponents({ point }: { point: FundamentalMetricPoint }) {
  if (!point.derived) return null;

  return (
    <details className="fundamental-disclosure">
      <summary>Компоненты расчёта <span>{point.calculation_components.length}</span></summary>
      <div className="calculation-summary">
        <div><span>Метод</span><strong>{formatDerivationMethod(point.derivation_method)}</strong></div>
        <div><span>Формула</span><code>{point.calculation ?? "Формула не указана"}</code></div>
      </div>
      {point.calculation_components.length === 0 ? (
        <p className="audit-empty">Компоненты расчёта отсутствуют в ответе API</p>
      ) : (
        <div className="table-wrap audit-table-wrap">
          <table className="calculation-components-table">
            <thead><tr><th>Метрика</th><th>Точное значение</th><th>Период</th><th>Финансовый период</th><th>Форма / accession</th><th>Подано</th><th>Получение</th></tr></thead>
            <tbody>{point.calculation_components.map((component) => (
              <tr key={component.identity}>
                <td><strong>{component.metric}</strong>{component.is_repeated_comparative && <span className="cell-note">Comparative</span>}</td>
                <td className="audit-number">{formatExactDecimal(component.value, component.unit)}</td>
                <td>{component.start ?? "instant"} — {component.end}</td>
                <td>{formatFiscalPeriod(component.fiscal_year, component.fiscal_period)}</td>
                <td>{component.form}<span className="cell-note breakable-id">{component.accession_number}</span></td>
                <td>{formatDate(component.filed)}</td>
                <td>{formatIngestionMethod(component.ingestion_method)}<span className="cell-note breakable-id">{safeFilename(component.source_filename)}</span></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </details>
  );
}
