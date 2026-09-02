import { AssetsMarketTable } from "@/components/assets-market-table";
import { PageHeader } from "@/components/ui";

export const metadata = { title: "Активы" };

export default function AssetsPage() {
  return (
    <>
      <PageHeader title="Активы" description="Каталог активов из базы данных InvestScope со статусом сохранённых рыночных данных." action={<span className="timestamp">Источник: backend API</span>} />
      <AssetsMarketTable />
      <p className="page-note">Котировки загружаются только из сохранённых рыночных данных. Отсутствующие значения не подменяются нулями или демонстрационными активами.</p>
    </>
  );
}
