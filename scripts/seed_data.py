"""Seed data script for Wall Street service."""

import boto3
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
table = dynamodb.Table("tradestreak-wall-street")


def seed_cramer_picks():
    """Seed Cramer picks with realistic data."""
    picks = [
        # Recent BUY recommendations
        {
            "ticker": "NVDA",
            "companyName": "NVIDIA Corporation",
            "recommendation": "BUY",
            "priceAtPick": 138.50,
            "currentPrice": 142.80,
            "showName": "Mad Money",
            "notes": "AI chip demand remains strong, data center growth accelerating",
            "daysAgo": 5,
        },
        {
            "ticker": "SOFI",
            "companyName": "SoFi Technologies",
            "recommendation": "BUY",
            "priceAtPick": 14.25,
            "currentPrice": 13.80,
            "showName": "Mad Money",
            "notes": "Fintech disruption, student loan refinancing leader",
            "daysAgo": 3,
        },
        {
            "ticker": "META",
            "companyName": "Meta Platforms",
            "recommendation": "BUY",
            "priceAtPick": 590.00,
            "currentPrice": 612.50,
            "showName": "Squawk Box",
            "notes": "AI monetization, Reels growth, cost discipline",
            "daysAgo": 7,
        },
        {
            "ticker": "PLTR",
            "companyName": "Palantir Technologies",
            "recommendation": "BUY",
            "priceAtPick": 72.50,
            "currentPrice": 78.20,
            "showName": "Mad Money",
            "notes": "Government contracts, AI platform expansion",
            "daysAgo": 10,
        },
        # SELL recommendations
        {
            "ticker": "COIN",
            "companyName": "Coinbase Global",
            "recommendation": "SELL",
            "priceAtPick": 285.00,
            "currentPrice": 268.50,
            "showName": "Mad Money",
            "notes": "Regulatory headwinds, trading volume concerns",
            "daysAgo": 4,
        },
        {
            "ticker": "RIVN",
            "companyName": "Rivian Automotive",
            "recommendation": "SELL",
            "priceAtPick": 12.80,
            "currentPrice": 14.20,
            "showName": "Squawk Box",
            "notes": "Cash burn rate, production challenges",
            "daysAgo": 8,
        },
        # HOLD recommendations
        {
            "ticker": "AAPL",
            "companyName": "Apple Inc.",
            "recommendation": "HOLD",
            "priceAtPick": 228.00,
            "currentPrice": 230.50,
            "showName": "Mad Money",
            "notes": "iPhone sales steady but China concerns persist",
            "daysAgo": 2,
        },
        {
            "ticker": "GOOGL",
            "companyName": "Alphabet Inc.",
            "recommendation": "HOLD",
            "priceAtPick": 195.00,
            "currentPrice": 192.30,
            "showName": "Mad Money",
            "notes": "Search dominance intact, AI competition heating up",
            "daysAgo": 6,
        },
        # More BUY picks for variety
        {
            "ticker": "AMD",
            "companyName": "Advanced Micro Devices",
            "recommendation": "BUY",
            "priceAtPick": 118.50,
            "currentPrice": 125.80,
            "showName": "Mad Money",
            "notes": "MI300 AI chip gaining market share vs NVIDIA",
            "daysAgo": 12,
        },
        {
            "ticker": "CRWD",
            "companyName": "CrowdStrike Holdings",
            "recommendation": "BUY",
            "priceAtPick": 355.00,
            "currentPrice": 362.20,
            "showName": "Mad Money",
            "notes": "Cybersecurity leader, platform consolidation",
            "daysAgo": 14,
        },
    ]

    for pick_data in picks:
        pick_date = datetime.utcnow() - timedelta(days=pick_data["daysAgo"])
        price_at_pick = pick_data["priceAtPick"]
        current_price = pick_data["currentPrice"]
        return_percent = ((current_price - price_at_pick) / price_at_pick) * 100
        inverse_return = -return_percent

        item = {
            "PK": "CRAMER",
            "SK": f"PICK#{pick_date.strftime('%Y-%m-%d')}#{pick_data['ticker']}",
            "id": str(uuid.uuid4())[:8],
            "ticker": pick_data["ticker"],
            "companyName": pick_data["companyName"],
            "recommendation": pick_data["recommendation"],
            "priceAtPick": Decimal(str(price_at_pick)),
            "currentPrice": Decimal(str(current_price)),
            "returnPercent": Decimal(str(round(return_percent, 2))),
            "inverseReturnPercent": Decimal(str(round(inverse_return, 2))),
            "pickDate": pick_date.isoformat(),
            "showName": pick_data["showName"],
            "notes": pick_data["notes"],
            "createdAt": datetime.utcnow().isoformat(),
            "updatedAt": datetime.utcnow().isoformat(),
            "GSI1PK": f"TICKER#{pick_data['ticker']}",
            "GSI1SK": f"CRAMER#{pick_date.strftime('%Y-%m-%d')}",
        }
        table.put_item(Item=item)
        print(f"Seeded Cramer pick: {pick_data['ticker']} ({pick_data['recommendation']})")


def seed_congress_members():
    """Seed Congress member profiles."""
    # Note: Using correct enum values: "D"/"R" for party, "House"/"Senate" for chamber
    members = [
        {
            "id": "nancy-pelosi",
            "name": "Nancy Pelosi",
            "party": "D",  # Democrat
            "chamber": "House",
            "state": "CA",
            "district": "11",
            "totalTrades": 45,
            "estimatedPortfolioReturn": 68.5,
            "avgDaysToDisclose": 28.5,
            "topHoldings": ["NVDA", "GOOGL", "MSFT", "AAPL"],
            "imageUrl": "https://bioguide.congress.gov/bioguide/photo/P/P000197.jpg",
        },
        {
            "id": "dan-crenshaw",
            "name": "Dan Crenshaw",
            "party": "R",  # Republican
            "chamber": "House",
            "state": "TX",
            "district": "2",
            "totalTrades": 28,
            "estimatedPortfolioReturn": 42.3,
            "avgDaysToDisclose": 35.2,
            "topHoldings": ["XOM", "CVX", "OXY"],
            "imageUrl": "https://bioguide.congress.gov/bioguide/photo/C/C001120.jpg",
        },
        {
            "id": "tommy-tuberville",
            "name": "Tommy Tuberville",
            "party": "R",  # Republican
            "chamber": "Senate",
            "state": "AL",
            "district": None,
            "totalTrades": 156,
            "estimatedPortfolioReturn": 35.8,
            "avgDaysToDisclose": 42.1,
            "topHoldings": ["MSFT", "AAPL", "TSM", "AMD"],
            "imageUrl": "https://bioguide.congress.gov/bioguide/photo/T/T000278.jpg",
        },
        {
            "id": "mark-green",
            "name": "Mark Green",
            "party": "R",  # Republican
            "chamber": "House",
            "state": "TN",
            "district": "7",
            "totalTrades": 18,
            "estimatedPortfolioReturn": 22.1,
            "avgDaysToDisclose": 31.0,
            "topHoldings": ["LMT", "RTX", "GD"],
            "imageUrl": "https://bioguide.congress.gov/bioguide/photo/G/G000590.jpg",
        },
        {
            "id": "josh-gottheimer",
            "name": "Josh Gottheimer",
            "party": "D",  # Democrat
            "chamber": "House",
            "state": "NJ",
            "district": "5",
            "totalTrades": 32,
            "estimatedPortfolioReturn": 52.7,
            "avgDaysToDisclose": 25.8,
            "topHoldings": ["META", "AMZN", "NFLX"],
            "imageUrl": "https://bioguide.congress.gov/bioguide/photo/G/G000583.jpg",
        },
    ]

    for member in members:
        item = {
            "PK": "CONGRESS_MEMBERS",  # Note: plural for proper query pattern
            "SK": f"MEMBER#{member['id']}",  # Note: MEMBER# prefix
            "id": member["id"],
            "name": member["name"],
            "party": member["party"],
            "chamber": member["chamber"],
            "state": member["state"],
            "district": member.get("district"),
            "totalTrades": member["totalTrades"],
            "estimatedPortfolioReturn": Decimal(str(member["estimatedPortfolioReturn"])),
            "avgDaysToDisclose": Decimal(str(member["avgDaysToDisclose"])),
            "topHoldings": member.get("topHoldings", []),
            "imageUrl": member.get("imageUrl"),
            "createdAt": datetime.utcnow().isoformat(),
            "updatedAt": datetime.utcnow().isoformat(),
            # GSI for sorting by return
            "GSI1PK": "CONGRESS_LEADERBOARD",
            "GSI1SK": f"{member['estimatedPortfolioReturn']:08.2f}#{member['id']}",
        }
        # Remove None values
        item = {k: v for k, v in item.items() if v is not None}
        table.put_item(Item=item)
        print(f"Seeded Congress member: {member['name']}")


def seed_congress_trades():
    """Seed Congress trades."""
    # Note: Using correct enum values: "D"/"R" for party, "House"/"Senate" for chamber, "Purchase"/"Sale" for transaction type
    trades = [
        {
            "memberId": "nancy-pelosi",
            "memberName": "Nancy Pelosi",
            "party": "D",  # Democrat
            "chamber": "House",
            "state": "CA",
            "ticker": "NVDA",
            "companyName": "NVIDIA Corporation",
            "transactionType": "Purchase",
            "amountRangeLow": 250000,
            "amountRangeHigh": 500000,
            "transactionDate": datetime.utcnow() - timedelta(days=42),
            "disclosureDate": datetime.utcnow() - timedelta(days=14),
            "priceAtTransaction": 118.50,
            "currentPrice": 142.80,
        },
        {
            "memberId": "nancy-pelosi",
            "memberName": "Nancy Pelosi",
            "party": "D",  # Democrat
            "chamber": "House",
            "state": "CA",
            "ticker": "GOOGL",
            "companyName": "Alphabet Inc.",
            "transactionType": "Purchase",
            "amountRangeLow": 100000,
            "amountRangeHigh": 250000,
            "transactionDate": datetime.utcnow() - timedelta(days=28),
            "disclosureDate": datetime.utcnow() - timedelta(days=7),
            "priceAtTransaction": 175.30,
            "currentPrice": 192.30,
        },
        {
            "memberId": "tommy-tuberville",
            "memberName": "Tommy Tuberville",
            "party": "R",  # Republican
            "chamber": "Senate",
            "state": "AL",
            "ticker": "MSFT",
            "companyName": "Microsoft Corporation",
            "transactionType": "Purchase",
            "amountRangeLow": 50000,
            "amountRangeHigh": 100000,
            "transactionDate": datetime.utcnow() - timedelta(days=35),
            "disclosureDate": datetime.utcnow() - timedelta(days=3),
            "priceAtTransaction": 405.00,
            "currentPrice": 425.50,
        },
        {
            "memberId": "tommy-tuberville",
            "memberName": "Tommy Tuberville",
            "party": "R",  # Republican
            "chamber": "Senate",
            "state": "AL",
            "ticker": "AAPL",
            "companyName": "Apple Inc.",
            "transactionType": "Sale",
            "amountRangeLow": 15000,
            "amountRangeHigh": 50000,
            "transactionDate": datetime.utcnow() - timedelta(days=20),
            "disclosureDate": datetime.utcnow() - timedelta(days=5),
            "priceAtTransaction": 235.00,
            "currentPrice": 230.50,
        },
        {
            "memberId": "dan-crenshaw",
            "memberName": "Dan Crenshaw",
            "party": "R",  # Republican
            "chamber": "House",
            "state": "TX",
            "ticker": "XOM",
            "companyName": "Exxon Mobil Corporation",
            "transactionType": "Purchase",
            "amountRangeLow": 15000,
            "amountRangeHigh": 50000,
            "transactionDate": datetime.utcnow() - timedelta(days=45),
            "disclosureDate": datetime.utcnow() - timedelta(days=7),
            "priceAtTransaction": 108.50,
            "currentPrice": 112.30,
        },
        {
            "memberId": "josh-gottheimer",
            "memberName": "Josh Gottheimer",
            "party": "D",  # Democrat
            "chamber": "House",
            "state": "NJ",
            "ticker": "META",
            "companyName": "Meta Platforms",
            "transactionType": "Purchase",
            "amountRangeLow": 100000,
            "amountRangeHigh": 250000,
            "transactionDate": datetime.utcnow() - timedelta(days=38),
            "disclosureDate": datetime.utcnow() - timedelta(days=10),
            "priceAtTransaction": 545.00,
            "currentPrice": 612.50,
        },
    ]

    for trade_data in trades:
        trade_id = str(uuid.uuid4())[:8]
        trans_date = trade_data["transactionDate"]
        disclosure_date = trade_data["disclosureDate"]
        price_at_trans = trade_data["priceAtTransaction"]
        current_price = trade_data["currentPrice"]
        return_percent = ((current_price - price_at_trans) / price_at_trans) * 100
        days_to_disclose = (disclosure_date - trans_date).days

        item = {
            "PK": "CONGRESS",
            "SK": f"TRADE#{disclosure_date.strftime('%Y-%m-%d')}#{trade_data['memberId']}#{trade_data['ticker']}",
            "id": trade_id,
            "memberId": trade_data["memberId"],
            "memberName": trade_data["memberName"],
            "party": trade_data["party"],
            "chamber": trade_data["chamber"],
            "state": trade_data["state"],
            "ticker": trade_data["ticker"],
            "companyName": trade_data["companyName"],
            "transactionType": trade_data["transactionType"],
            "amountRangeLow": trade_data["amountRangeLow"],
            "amountRangeHigh": trade_data["amountRangeHigh"],
            "transactionDate": trans_date.isoformat(),
            "disclosureDate": disclosure_date.isoformat(),
            "daysToDisclose": days_to_disclose,
            "priceAtTransaction": Decimal(str(price_at_trans)),
            "currentPrice": Decimal(str(current_price)),
            "returnSinceTransaction": Decimal(str(round(return_percent, 2))),
            "createdAt": datetime.utcnow().isoformat(),
            "updatedAt": datetime.utcnow().isoformat(),
            # GSI for ticker lookups
            "GSI1PK": f"TICKER#{trade_data['ticker']}",
            "GSI1SK": f"CONGRESS#{disclosure_date.strftime('%Y-%m-%d')}",
        }
        table.put_item(Item=item)
        print(f"Seeded Congress trade: {trade_data['memberName']} - {trade_data['ticker']} ({trade_data['transactionType']})")


def seed_earnings_events():
    """Seed upcoming earnings events."""
    events = [
        {
            "ticker": "NFLX",
            "companyName": "Netflix Inc.",
            "daysAhead": 2,
            "estimatedEPS": 4.52,
            "fiscalQuarter": "Q4",
            "fiscalYear": 2025,
            "marketCap": "280B",
        },
        {
            "ticker": "TSLA",
            "companyName": "Tesla Inc.",
            "daysAhead": 4,
            "estimatedEPS": 0.72,
            "fiscalQuarter": "Q4",
            "fiscalYear": 2025,
            "marketCap": "780B",
        },
        {
            "ticker": "MSFT",
            "companyName": "Microsoft Corporation",
            "daysAhead": 5,
            "estimatedEPS": 3.12,
            "fiscalQuarter": "Q2",
            "fiscalYear": 2026,
            "marketCap": "3.1T",
        },
        {
            "ticker": "META",
            "companyName": "Meta Platforms",
            "daysAhead": 6,
            "estimatedEPS": 5.85,
            "fiscalQuarter": "Q4",
            "fiscalYear": 2025,
            "marketCap": "1.5T",
        },
        {
            "ticker": "AAPL",
            "companyName": "Apple Inc.",
            "daysAhead": 8,
            "estimatedEPS": 2.35,
            "fiscalQuarter": "Q1",
            "fiscalYear": 2026,
            "marketCap": "3.5T",
        },
        {
            "ticker": "AMZN",
            "companyName": "Amazon.com Inc.",
            "daysAhead": 10,
            "estimatedEPS": 1.48,
            "fiscalQuarter": "Q4",
            "fiscalYear": 2025,
            "marketCap": "2.2T",
        },
        {
            "ticker": "GOOGL",
            "companyName": "Alphabet Inc.",
            "daysAhead": 11,
            "estimatedEPS": 2.05,
            "fiscalQuarter": "Q4",
            "fiscalYear": 2025,
            "marketCap": "2.3T",
        },
        {
            "ticker": "AMD",
            "companyName": "Advanced Micro Devices",
            "daysAhead": 12,
            "estimatedEPS": 0.92,
            "fiscalQuarter": "Q4",
            "fiscalYear": 2025,
            "marketCap": "200B",
        },
    ]

    for event_data in events:
        earnings_date = datetime.utcnow() + timedelta(days=event_data["daysAhead"])
        event_id = f"{event_data['ticker']}-{earnings_date.strftime('%Y-%m-%d')}"

        item = {
            "PK": "EARNINGS",
            "SK": f"EVENT#{earnings_date.strftime('%Y-%m-%d')}#{event_data['ticker']}",
            "id": event_id,
            "ticker": event_data["ticker"],
            "companyName": event_data["companyName"],
            "earningsDate": earnings_date.isoformat(),
            "estimatedEPS": Decimal(str(event_data["estimatedEPS"])),
            "fiscalQuarter": event_data["fiscalQuarter"],
            "fiscalYear": event_data["fiscalYear"],
            "marketCap": event_data["marketCap"],
            "createdAt": datetime.utcnow().isoformat(),
            "updatedAt": datetime.utcnow().isoformat(),
            # GSI for ticker lookups
            "GSI1PK": f"TICKER#{event_data['ticker']}",
            "GSI1SK": f"EARNINGS#{earnings_date.strftime('%Y-%m-%d')}",
        }
        table.put_item(Item=item)
        print(f"Seeded earnings event: {event_data['ticker']} ({earnings_date.strftime('%Y-%m-%d')})")


if __name__ == "__main__":
    print("Seeding Cramer picks...")
    seed_cramer_picks()
    print("\nSeeding Congress members...")
    seed_congress_members()
    print("\nSeeding Congress trades...")
    seed_congress_trades()
    print("\nSeeding earnings events...")
    seed_earnings_events()
    print("\nDone!")
