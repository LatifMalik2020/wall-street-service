# Wall Street Service Architecture

## Single-Table DynamoDB Design
Uses entity-type prefixed keys for all features in one table.

| PK Pattern | SK Pattern | Entity |
|-----------|-----------|--------|
| `CRAMER` | `PICK#{ticker}#{date}` | Cramer pick |
| `CONGRESS` | `TRADE#{date}#{id}` | Congress trade |
| `CONGRESS_MEMBER#{id}` | `PROFILE` | Member profile |
| `MOOD` | `DATE#{date}` | Market mood index |
| `USER#{userId}` | `MOOD_PREDICTION#{date}` | User mood prediction |
| `EARNINGS` | `EVENT#{date}#{ticker}` | Earnings event |
| `USER#{userId}` | `EARNINGS_PREDICTION#{ticker}` | Earnings prediction |
| `MARKET_TALK` | `EPISODE#{date}` | AI dialogue episode |
| `SUPER_INVESTOR#{cik}` | `PROFILE` | Investor profile |
| `SUPER_INVESTOR#{cik}` | `TRADE#{date}#{id}` | Investor trade |
| `STOCK#{symbol}` | `DETAIL` | Cached stock detail |
| `DAILY_BUZZ` | `DATE#{date}` | Daily buzz content |

## Data Pipeline
```
EventBridge (cron) -> Lambda -> FMP API / Quiver API
  -> Transform & validate -> DynamoDB -> Available via API
```

- Congress trades: refreshed every 6 hours
- Cramer picks: refreshed daily
- Market mood: calculated from multiple sentiment indicators
- Earnings: refreshed weekly + event-driven on earnings day

## Market Talk (AI Dialogue)
- Two AI characters discuss market events
- Generated via Bedrock/Claude with market data context
- Stored as episodes with structured dialogue format
