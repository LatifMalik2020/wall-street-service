# Data reliability — findings & fix plan (2026-09-05)

User mandate: shadowing + congress trades need RELIABLE data. Audit findings
below; the pipeline wasn't unreliable — it was **dead since January** and
nothing alarmed.

## Findings (all verified live tonight)

1. **Congress ingestion silently failing nightly.** EventBridge rule fires
   daily at 23:00 UTC and completes with `saved: 0, total: 0` every run.
2. **Quiver fallback is doubly broken**: env `QUIVER_QUANT_API_KEY` is EMPTY on
   the Lambda, and the coded endpoint
   `api.quiverquant.com/beta/historical/congresstrading` now returns **404**
   (Quiver retired/moved the beta API).
3. **FMP "primary" has NO key anywhere in AWS** — checked all 48 Lambdas: no
   `FMP_API_KEY` set on any function. Our own `ENVIRONMENT_VARIABLES.md`
   documents the exact symptom: missing FMP key → "Congress, earnings, Cramer
   data all empty."
4. **Earnings ingestion also saves 0** (same root cause — FMP-keyless).
5. **Stored data is stale since ~2026-01-20**; live API returns 0 items.
6. **No freshness alarm exists** — months of zero-saves, zero pages.

## Fix plan

### Immediate (needs user)
- [ ] **FMP API key** — retrieve from the financialmodelingprep.com dashboard
      (already paying $25/mo) and approve setting `FMP_API_KEY` on
      `tradestreak-wall-street` (prod env change → explicit go-ahead per the
      current no-prod-changes caution). This alone revives congress + earnings
      + Cramer.
- [ ] **Quiver decision**: paying $10/mo for a 404ing integration — either fix
      the endpoint path to their current API or cancel the subscription.
      Recommendation: with FMP primary + the alarm below, Quiver is optional.

### Reliability layer (the "perfect it")
- [ ] CloudWatch **metric filter + alarm**: ingestion log `"saved": 0` for
      2 consecutive daily runs → `tradestreak-alarms` SNS. Never silent again.
- [ ] Ingestion runs write a `lastSuccessfulIngestAt` heartbeat item; the API
      surfaces `asOf` so the app can show data age instead of implying live.
- [ ] Cross-source spot-check job (weekly): compare FMP counts vs primary
      sources; large divergence → alarm.

### Shadowing data source (decided, proven)
- **13F / famous investors → SEC EDGAR, primary source, FREE.** Verified live:
  `data.sec.gov/submissions/CIK0001067983.json` returns Berkshire's filing
  index current through 2026-08-14; holdings come from the 13F information
  tables per accession. Quarterly cadence (filed ≤45 days after quarter end) —
  perfect for shadow portfolios, zero vendor risk, no key, no cost.
  Requirements: User-Agent header, ≤10 req/s. Candidate roster: Berkshire,
  Scion (Burry), Pershing Square, Appaloosa, Bridgewater, Duquesne family
  office, Renaissance.
- **Congress → FMP (once keyed) as primary**, with the House/Senate clerk
  e-filing sites as the authoritative cross-check. Quiver only if repaired.

## Sequence
1. User supplies FMP key + go-ahead → set env, re-run ingestion, verify fresh
   rows land, backfill.
2. Ship the alarm + heartbeat (small code change to scheduler).
3. Build the EDGAR 13F ingester (new module, local-first) → shadow-portfolio
   data model → Shadow Portfolios feature on the paper engine.
