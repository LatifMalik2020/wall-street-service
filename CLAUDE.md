# Wall Street Service

## Overview
Financial data aggregation service powering the Wall Street Experience. Cramer tracker, Congress trades, Market Mood (Fear & Greed), Earnings predictions, Beat Congress game, Market Talk (AI dialogue), Super Investors, Daily Buzz, Stock Detail, and IPOs.

## Tech Stack
- **Runtime:** Python 3.12 on AWS Lambda (Docker container)
- **Database:** DynamoDB (single-table design)
- **Data Sources:** FMP API ($25/mo), Quiver Quantitative ($10/mo)
- **Scheduling:** EventBridge for data refresh
- **Deploy:** Docker -> ECR -> Lambda via GitHub Actions

## Dev Environment
```bash
pip install -r requirements.txt
pytest tests/ -v
ruff check src/
black src/
mypy src/
```

## Project Structure
```
src/
  index.py              # Lambda entry (src.index.lambda_handler)
  routes/               # Route handlers by feature
  services/             # Business logic
  repositories/         # DynamoDB operations
tests/
.github/workflows/      # CI/CD pipeline
```

## API Routes
| Method | Path | Description |
|--------|------|-------------|
| GET | `/wall-street/cramer/picks` | Cramer stock picks |
| GET | `/wall-street/cramer/picks/{ticker}` | Cramer pick detail |
| GET | `/wall-street/congress/trades` | Congress trades (paginated) |
| GET | `/wall-street/congress/members` | Congress members list |
| GET | `/wall-street/congress/members/{id}` | Member detail + trades |
| GET | `/wall-street/mood` | Market mood index |
| POST | `/wall-street/mood/predict` | Submit mood prediction |
| GET | `/wall-street/mood/predictions` | Prediction history |
| GET | `/wall-street/earnings/upcoming` | Upcoming earnings |
| POST | `/wall-street/earnings/predict/{ticker}` | Submit earnings prediction |
| GET | `/wall-street/earnings/predictions` | Earnings prediction history |
| GET | `/wall-street/beat-congress/games` | Active games |
| POST | `/wall-street/beat-congress/create/{memberId}` | Create game |
| GET | `/wall-street/beat-congress/leaderboard` | Game leaderboard |
| GET | `/wall-street/market-talk/episodes` | AI market dialogue episodes |
| GET | `/wall-street/market-talk/latest` | Latest episode |
| GET | `/wall-street/super-investors` | Super investor list |
| GET | `/wall-street/super-investors/{cik}/trades` | Investor trades |
| GET | `/wall-street/stocks/{symbol}` | Stock detail |
| GET | `/wall-street/stocks/{symbol}/ratios` | Financial ratios |
| GET | `/wall-street/stocks/{symbol}/financials` | Financial statements |
| GET | `/wall-street/stocks/{symbol}/short-interest` | Short interest |
| GET | `/wall-street/stocks/{symbol}/technicals` | Technical indicators |
| GET | `/wall-street/stocks/{symbol}/filings` | SEC filings |
| GET | `/wall-street/ipos` | Upcoming IPOs |
| GET | `/wall-street/market-status` | Market open/closed |
| GET | `/wall-street/indices/comparison` | Index comparison |
| GET | `/wall-street/etfs/featured` | Featured ETFs |
| GET | `/wall-street/daily-buzz` | Daily market buzz |

## Testing
```bash
pytest tests/ -v          # Unit tests
ruff check src/           # Linting
black --check src/        # Formatting
mypy src/                 # Type checking
```

## Common Pitfalls
- FMP API rate limits: respect 300 calls/min limit
- Congress data: FMP is primary, Quiver is backfill — never rely on a single source
- EventBridge schedules refresh data overnight — stale data during market hours is expected
- Capitol Trades is the UI reference standard for congress member detail pages
