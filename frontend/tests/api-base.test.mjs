import assert from "node:assert/strict";
import test from "node:test";

import { buildLegacyApiUrl, buildMarketApiUrl, normalizeLegacyApiBaseUrl } from "../lib/api-base.ts";

test("adds the legacy prefix when API base contains only the origin", () => {
  assert.equal(
    buildLegacyApiUrl("http://127.0.0.1:8000", "/backtesting/run"),
    "http://127.0.0.1:8000/api/v1/backtesting/run",
  );
});

test("does not duplicate an existing legacy prefix", () => {
  assert.equal(
    buildLegacyApiUrl("http://127.0.0.1:8000/api/v1/", "/backtesting/run"),
    "http://127.0.0.1:8000/api/v1/backtesting/run",
  );
});

test("does not duplicate the prefix when the caller passes a fully prefixed path", () => {
  assert.equal(
    buildLegacyApiUrl("http://127.0.0.1:8000/api/v1", "/api/v1/backtesting/run"),
    "http://127.0.0.1:8000/api/v1/backtesting/run",
  );
  assert.equal(normalizeLegacyApiBaseUrl("http://127.0.0.1:8000"), "http://127.0.0.1:8000/api/v1");
});

test("uses a relative legacy prefix when no API origin is configured", () => {
  assert.equal(buildLegacyApiUrl(undefined, "/portfolios"), "/api/v1/portfolios");
  assert.equal(buildLegacyApiUrl("", "/api/v1/portfolios"), "/api/v1/portfolios");
});

test("builds database-backed asset API urls without the legacy prefix", () => {
  assert.equal(buildMarketApiUrl("http://127.0.0.1:8000", "/assets"), "http://127.0.0.1:8000/api/assets");
  assert.equal(buildMarketApiUrl("http://127.0.0.1:8000/api", "/assets/AAPL"), "http://127.0.0.1:8000/api/assets/AAPL");
  assert.equal(buildMarketApiUrl(undefined, "/api/market/AAPL/latest"), "/api/market/AAPL/latest");
});
