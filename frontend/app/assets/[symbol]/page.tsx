import { AssetDetailsClient } from "@/components/asset-details-client";

export const dynamicParams = true;

export default async function AssetDetailsPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  return <AssetDetailsClient symbol={symbol} />;
}
