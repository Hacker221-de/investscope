export const LEGACY_API_PREFIX = "/api/v1";

export function normalizeLegacyApiBaseUrl(configuredUrl: string | undefined): string {
  const baseUrl = (configuredUrl ?? "").trim().replace(/\/+$/, "");
  if (!baseUrl) return LEGACY_API_PREFIX;
  return baseUrl.endsWith(LEGACY_API_PREFIX) ? baseUrl : `${baseUrl}${LEGACY_API_PREFIX}`;
}

export function buildLegacyApiUrl(configuredUrl: string | undefined, path: string): string {
  const baseUrl = normalizeLegacyApiBaseUrl(configuredUrl);
  const normalizedPath = `/${path.replace(/^\/+/, "")}`;
  const suffix = normalizedPath === LEGACY_API_PREFIX
    ? ""
    : normalizedPath.startsWith(`${LEGACY_API_PREFIX}/`)
      ? normalizedPath.slice(LEGACY_API_PREFIX.length)
      : normalizedPath;
  return `${baseUrl}${suffix}`;
}
