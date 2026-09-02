import { RecommendationsList } from "@/components/recommendations-list";
import { PageHeader } from "@/components/ui";

export const metadata = { title: "Аналитические рейтинги" };

export default function RecommendationsPage() {
  return (
    <>
      <PageHeader
        title="Аналитические рейтинги"
        description="Объяснимые оценки из backend API с привязкой к активам, сохранённым в базе данных."
        action={<span className="timestamp">Источник: backend API</span>}
      />
      <RecommendationsList />
    </>
  );
}
