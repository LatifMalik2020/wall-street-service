# Shadow Portfolios — design (2026-09-05)

Paper-first mirroring of famous investors' disclosed books. Data layer is done
(EDGAR 13F ingester + diff + CUSIP→ticker, all tested); this doc fixes the
product semantics and storage so the engine can't sprawl like the removed v1
features. Principles: primary-source data, honest "as-of" labeling, paper-only
until the broker path is approved, every mechanic testable as a pure function.

## Semantics

**Follow** — user picks a filer (Berkshire, Scion, Pershing…) and a virtual
allocation (default $10,000 paper). We replicate the filer's latest disclosed
book **proportionally by value weight**, capped to the **top 20 positions**
(long tail adds noise, not signal), at current market prices. Fractional
shares allowed (it's paper).

**Rebalance-on-filing** — when a new 13F is ingested, apply the diff to every
follower: `opened` → buy to the new weight; `exited` → sell all; `increased` /
`decreased` → trade to the new weight. Each action writes a **shadow trade**
with provenance (accession + change kind + filer) — the raw material for
Ticker's explanations ("Buffett trimmed Kroger 22%; your shadow sold 3 shares").

**Lazy rebalance** — no fan-out infra. The filer snapshot stores
`latestAccession`; a user's shadow stores `appliedAccession`. On portfolio
read, if they differ, apply the pending diff then serve. One quarterly filing +
lazy application = zero queues, zero cron fan-out.

**Honesty layer** — 13Fs are filed up to 45 days after quarter end. Every
shadow surface shows `Based on filings as of {filingDate}` and teaches WHY the
lag exists (a lesson tie-in, not a fine-print apology).

**Scorecard** — shadow P/L vs the user's own paper portfolio vs SPY, from the
existing price infra. This comparison ("Buffett's shadow beat your picks by
4.2% this quarter") is the retention loop and the Ticker conversation starter.

**Stale-filer guard** — 13Fs are due 45 days after quarter end; >135 days
without a new filing means the fund likely deregistered (Scion, 2025-11).
Stale filers: existing shadows keep working but show a prominent warning;
the filer is removed from the "start following" roster. Mapping cost guard:
only map CUSIPs in the top 2×N by value — Bridgewater files ~1,000 positions
but only 20 can enter a shadow.

## Storage (existing tradestreak-wall-street table patterns)

| pk | sk | body |
|---|---|---|
| `SHADOWFILER#{cik}` | `PROFILE` | name, roster metadata, latestAccession, latestFilingDate |
| `SHADOWFILER#{cik}` | `HOLDINGS#{accession}` | parsed top-N holdings (ticker, weight, value) |
| `SHADOWFILER#{cik}` | `DIFF#{accession}` | the change list (renderable feed + rebalance input) |
| `USER#{id}` | `SHADOW#{cik}` | allocatedCash, positions[], appliedAccession, createdAt |
| `USER#{id}` | `SHADOWTRADE#{ts}` | symbol, side, qty, price, provenance{accession, kind, filer} |

## Jobs
Daily EventBridge check per roster filer (5 filers ≈ 10 EDGAR requests/day):
new accession? → parse, diff, persist snapshot + diff, bump latestAccession.
Freshness heartbeat + saved:0-style alarm from day one (the lesson of the
congress pipeline).

## Congress shadowing (phase 2, post-FMP-key)
Same model, different provenance: PTR disclosures dribble in daily and give
amount *ranges*, not share counts → represent as weight nudges sized to the
range midpoint, provenance = disclosure id. The engine below is already
agnostic to the source of a `TargetWeights` update.

## Compliance
Educational simulation; not advice; delayed-data disclosure everywhere; no
real-money mirroring until the Alpaca production agreement (then it becomes a
routing question through the existing alpaca-adapter — same engine).
