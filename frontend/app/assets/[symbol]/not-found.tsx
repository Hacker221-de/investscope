import Link from "next/link";

export default function AssetNotFound() {
  return <section className="empty-state"><span>404</span><h1>Актив не найден</h1><p>Этот тикер отсутствует в демонстрационном списке активов.</p><Link href="/assets" className="primary-button">Вернуться к активам</Link></section>;
}
