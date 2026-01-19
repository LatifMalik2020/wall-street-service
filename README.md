# Wall Street Service

TradeStreak's Wall Street Experience backend service providing:

- **Cramer Tracker**: Track Jim Cramer's stock picks and compare "Follow vs Inverse" performance
- **Congress Tracker**: Monitor congressional stock trades from public disclosures
- **Market Mood Meter**: Fear & Greed index with prediction game
- **Earnings Predictions**: Predict BEAT/MEET/MISS for upcoming earnings
- **Beat Congress Game**: Challenge Congress members to a virtual trading competition
- **Market Talk**: AI-generated market commentary (text-based MVP)

## Architecture

- **Runtime**: Python 3.12 on AWS Lambda (containerized)
- **Database**: DynamoDB (single-table design)
- **API**: API Gateway with Cognito authentication
- **Events**: EventBridge for scheduled tasks
- **Infrastructure**: Terraform

## Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Run linting
ruff check src/
black src/

# Type checking
mypy src/ --ignore-missing-imports
```

## API Endpoints

### Cramer Tracker
- `GET /wall-street/cramer/picks` - Get Cramer picks (paginated)
- `GET /wall-street/cramer/picks/{ticker}` - Get pick detail
- `GET /wall-street/cramer/stats` - Get performance statistics

### Congress Tracker
- `GET /wall-street/congress/trades` - Get trades (filterable)
- `GET /wall-street/congress/trades/{tradeId}` - Get trade detail
- `GET /wall-street/congress/members` - Get members list
- `GET /wall-street/congress/members/{memberId}` - Get member detail
- `GET /wall-street/congress/members/{memberId}/trades` - Get member's trades

### Market Mood
- `GET /wall-street/mood` - Get current Fear & Greed index
- `POST /wall-street/mood/predict` - Submit mood prediction (auth required)
- `GET /wall-street/mood/predictions` - Get user's predictions (auth required)

### Earnings Predictions
- `GET /wall-street/earnings/upcoming` - Get upcoming earnings events
- `GET /wall-street/earnings/events/{eventId}` - Get event detail
- `POST /wall-street/earnings/predict` - Submit prediction (auth required)
- `GET /wall-street/earnings/predictions` - Get user's predictions (auth required)
- `GET /wall-street/earnings/stats` - Get user's stats (auth required)

### Beat Congress
- `GET /wall-street/beat-congress/games` - Get user's games (auth required)
- `POST /wall-street/beat-congress/games` - Create new game (auth required)
- `GET /wall-street/beat-congress/games/{gameId}` - Get game detail (auth required)
- `GET /wall-street/beat-congress/leaderboard` - Get leaderboard
- `GET /wall-street/beat-congress/members` - Get challengeable members (auth required)

### Market Talk
- `GET /wall-street/market-talk/episodes` - Get episodes
- `GET /wall-street/market-talk/latest` - Get latest exchange
- `GET /wall-street/market-talk/episodes/{episodeId}` - Get episode detail
- `POST /wall-street/market-talk/generate` - Generate new episode

## Deployment

Deployment is automated via GitHub Actions on push to `main`.

Manual deployment:
```bash
# Build Docker image
docker build -t wall-street-service .

# Tag and push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com
docker tag wall-street-service:latest <account>.dkr.ecr.us-east-1.amazonaws.com/tradestreak-wall-street:latest
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/tradestreak-wall-street:latest

# Update Lambda
aws lambda update-function-code --function-name tradestreak-wall-street --image-uri <account>.dkr.ecr.us-east-1.amazonaws.com/tradestreak-wall-street:latest
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Environment name | `dev` |
| `LOG_LEVEL` | Logging level | `info` |
| `DYNAMODB_TABLE` | DynamoDB table name | `tradestreak-wall-street` |
| `QUIVER_QUANT_API_KEY` | QuiverQuant API key | - |
| `ALPHA_VANTAGE_API_KEY` | Alpha Vantage API key | - |

## Data Sources

- **Congress Trades**: [QuiverQuant](https://www.quiverquant.com/) (free tier)
- **Fear & Greed Index**: CNN API (unofficial)
- **Stock Prices & Earnings**: [Alpha Vantage](https://www.alphavantage.co/) (25 req/day free)
- **Cramer Picks**: Manual entry (future: CNBC scraping)
