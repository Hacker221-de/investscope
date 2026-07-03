import { BacktestingWorkbench } from "@/components/backtesting-workbench";
import { PageHeader } from "@/components/ui";

export const metadata = { title: "Историческое тестирование" };

export default function BacktestingPage() {
  return (
    <>
      <PageHeader
        title="Историческое тестирование"
        description="Проверка аналитических сигналов на фиксированных исторических данных без моделирования реальных сделок."
        action={<span className="timestamp">Детерминированный демонстрационный ряд</span>}
      />
      <div className="backtest-disclaimer">Результаты показывают историческое поведение аналитических сигналов. Они не являются симуляцией поручений или реального исполнения.</div>
      <BacktestingWorkbench />
    </>
  );
}
