import { ProviderStatus } from "@/components/provider-status";
import { PageHeader } from "@/components/ui";

export const metadata = { title: "Настройки" };

export default function SettingsPage() {
  return (
    <>
      <PageHeader title="Настройки" description="Параметры отображения, анализа и источников данных." />
      <section className="settings-layout"><nav className="panel settings-nav"><a href="#general" className="active">Основные</a><a href="#risk">Параметры анализа</a><a href="#data">Источники данных</a><a href="#system">Система</a></nav><div className="settings-content"><article className="panel settings-section" id="general"><div><p className="eyebrow">Рабочее пространство</p><h2>Основные настройки</h2><p>Параметры отображения на страницах и в аналитических отчётах.</p></div><label>Базовая валюта<select defaultValue="USD"><option>USD</option><option>EUR</option><option>GBP</option></select></label><label>Часовой пояс<select defaultValue="UTC"><option>UTC</option></select><small>В API даты и время хранятся в UTC.</small></label><label>Формат чисел<select defaultValue="en-US"><option value="en-US">1,234.56</option><option value="de-DE">1.234,56</option></select></label></article><article className="panel settings-section" id="risk"><div><p className="eyebrow">Параметры анализа</p><h2>Отображение сценариев</h2><p>Параметры влияют только на представление аналитических результатов.</p></div><label>Уровень риска для отображения сценариев<select defaultValue="moderate"><option value="conservative">Низкий</option><option value="moderate">Средний</option><option value="growth">Высокий</option></select></label><label>Горизонт анализа<select defaultValue="12"><option value="6">6 месяцев</option><option value="12">12 месяцев</option><option value="36">3 года</option></select></label></article><article className="panel settings-section" id="data"><div><p className="eyebrow">Входные данные</p><h2>Источники данных</h2><p>Статус настроенного read-only провайдера. API-ключ не передаётся в интерфейс.</p></div><ProviderStatus /></article><article className="panel settings-section" id="system"><div><p className="eyebrow">Среда</p><h2>Система</h2></div><dl className="system-grid"><div><dt>Frontend</dt><dd>Next.js / TypeScript</dd></div><div><dt>API</dt><dd>FastAPI / Python</dd></div><div><dt>База данных</dt><dd>PostgreSQL</dd></div><div><dt>Режим данных</dt><dd>Read-only аналитика</dd></div></dl><button className="secondary-button">Проверить доступность API</button></article></div></section>
    </>
  );
}
