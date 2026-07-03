export const LEGACY_API_PREFIX = "/api/v1";

export function normalizeLegacyApiBaseUrl(configuredUrl: string): string {
  const baseUrl = configuredUrl.trim().replace(/\/+$/, "");
  if (!baseUrl) throw new Error("NEXT_PUBLIC_API_URL must not be empty");
  return baseUrl.endsWith(LEGACY_API_PREFIX) ? baseUrl : `${baseUrl}${LEGACY_API_PREFIX}`;
}

export function buildLegacyApiUrl(configuredUrl: string, path: string): string {
  const baseUrl = normalizeLegacyApiBaseUrl(configuredUrl);
  const normalizedPath = `/${path.replace(/^\/+/, "")}`;
  const suffix = normalizedPath === LEGACY_API_PREFIX
    ? ""
    : normalizedPath.startsWith(`${LEGACY_API_PREFIX}/`)
      ? normalizedPath.slice(LEGACY_API_PREFIX.length)
      : normalizedPath;
  return `${baseUrl}${suffix}`;
}
