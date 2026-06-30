import { AssetsMarketTable } from "@/components/assets-market-table";
import { PageHeader } from "@/components/ui";
import { assets } from "@/lib/demo-data";

export const metadata = { title: "Активы" };

export default function AssetsPage() {
  return (
    <>
      <PageHeader title="Активы" description="Демонстрационный список активов с ценовыми и аналитическими показателями." action={<button className="primary-button">Добавить в список наблюдения</button>} />
      <section className="toolbar panel"><label className="search-box"><span>⌕</span><input aria-label="Поиск активов" placeholder="Тикер или название компании" /></label><select aria-label="Тип актива" defaultValue="all"><option value="all">Все типы активов</option><option>Акция</option><option>Биржевой фонд</option></select><select aria-label="Сектор" defaultValue="all"><option value="all">Все секторы</option><option>Технологии</option><option>Облигации</option></select><span className="result-count">4 демонстрационных актива</span></section>
      <AssetsMarketTable fixtures={assets} />
      <p className="page-note">Котировки загружаются только из сохранённых рыночных данных. Расчётная стоимость и рейтинги пока используют демонстрационные аналитические модели.</p>
    </>
  );
}
