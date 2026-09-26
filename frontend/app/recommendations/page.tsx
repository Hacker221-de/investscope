import { RecommendationsList } from "@/components/recommendations-list";
import { PageHeader } from "@/components/ui";

export const metadata = { title: "Демонстрационные рейтинги" };

export default function RecommendationsPage() {
  return (
    <>
      <PageHeader
        title="Демонстрационные рейтинги"
        description="Фиксированные примеры аналитических оценок для знакомства с интерфейсом. Они не пересчитываются по текущим данным компаний."
        action={<span className="timestamp">ДЕМО · Примеры рейтингов</span>}
      />
      <RecommendationsList />
    </>
  );
}
