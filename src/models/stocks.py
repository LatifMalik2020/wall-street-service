"""Stock fundamentals, technicals, IPO, market status, and SEC filing models."""

from typing import List, Optional
from pydantic import Field

from src.models.base import BaseEntity


class StockSnapshot(BaseEntity):
    """Real-time stock price snapshot from Polygon."""

    symbol: str = Field(..., description="Ticker symbol")
    price: float = Field(..., description="Current price")
    change: float = Field(..., description="Price change from previous close")
    changePercent: float = Field(..., description="Percent change from previous close")
    volume: int = Field(..., description="Volume for the current session")
    latestTradingDay: str = Field(..., description="Date of the latest trading session")


class StockRatios(BaseEntity):
    """Financial ratios for a stock (from Polygon /stocks/financials/v1/ratios)."""

    ticker: Optional[str] = Field(None, description="Ticker symbol")
    date: Optional[str] = Field(None, description="Date the ratios were calculated")
    price: Optional[float] = Field(None, description="Stock price at ratio calculation date")
    market_cap: Optional[float] = Field(None, description="Market capitalisation")
    enterprise_value: Optional[float] = Field(None, description="Enterprise value")
    earnings_per_share: Optional[float] = Field(None, description="Trailing EPS")
    price_to_earnings: Optional[float] = Field(None, description="P/E ratio")
    price_to_book: Optional[float] = Field(None, description="P/B ratio")
    price_to_sales: Optional[float] = Field(None, description="P/S ratio")
    dividend_yield: Optional[float] = Field(None, description="Dividend yield as decimal")
    return_on_assets: Optional[float] = Field(None, description="ROA")
    return_on_equity: Optional[float] = Field(None, description="ROE")
    debt_to_equity: Optional[float] = Field(None, description="Debt-to-equity ratio")
    current: Optional[float] = Field(None, description="Current ratio")
    quick: Optional[float] = Field(None, description="Quick ratio")
    cash: Optional[float] = Field(None, description="Cash ratio")
    ev_to_ebitda: Optional[float] = Field(None, description="EV / EBITDA")
    free_cash_flow: Optional[float] = Field(None, description="Free cash flow")
    average_volume: Optional[float] = Field(None, description="Average daily volume")


class IncomeStatement(BaseEntity):
    """Annual or quarterly income statement from Polygon /stocks/financials/v1/income-statements."""

    ticker: Optional[str] = Field(None, description="Ticker symbol")
    timeframe: Optional[str] = Field(None, description="annual | quarterly")
    fiscal_year: Optional[str] = Field(None, description="Fiscal year")
    fiscal_period: Optional[str] = Field(None, description="Fiscal period label")
    start_date: Optional[str] = Field(None, description="Period start date")
    end_date: Optional[str] = Field(None, description="Period end date")
    revenue: Optional[float] = Field(None, description="Total revenue")
    cost_of_revenue: Optional[float] = Field(None, description="Cost of revenue")
    gross_profit: Optional[float] = Field(None, description="Gross profit")
    operating_income: Optional[float] = Field(None, description="Operating income/loss")
    ebitda: Optional[float] = Field(None, description="EBITDA")
    net_income_loss: Optional[float] = Field(None, description="Net income or loss")
    earnings_per_share_basic: Optional[float] = Field(None, description="Basic EPS")
    earnings_per_share_diluted: Optional[float] = Field(None, description="Diluted EPS")
    operating_expenses: Optional[float] = Field(None, description="Total operating expenses")
    research_and_development: Optional[float] = Field(None, description="R&D expense")
    interest_expense: Optional[float] = Field(None, description="Interest expense")
    income_tax_expense: Optional[float] = Field(None, description="Income tax expense")


class ShortInterestData(BaseEntity):
    """Short interest record from Polygon /stocks/v1/short-interest."""

    ticker: Optional[str] = Field(None, description="Ticker symbol")
    short_interest: Optional[float] = Field(None, description="Number of shares sold short")
    avg_daily_volume: Optional[float] = Field(None, description="Average daily trading volume")
    days_to_cover: Optional[float] = Field(None, description="Days to cover (short ratio)")
    settlement_date: Optional[str] = Field(None, description="Settlement date of the report")


class ShortVolumeData(BaseEntity):
    """Short volume record from Polygon /stocks/v1/short-volume."""

    ticker: Optional[str] = Field(None, description="Ticker symbol")
    date: Optional[str] = Field(None, description="Trading date")
    short_volume: Optional[float] = Field(None, description="Short volume on the date")
    total_volume: Optional[float] = Field(None, description="Total volume on the date")
    short_volume_ratio: Optional[float] = Field(None, description="Short volume / total volume")


class FloatData(BaseEntity):
    """Float (free-float) data from Polygon /stocks/vX/float."""

    ticker: Optional[str] = Field(None, description="Ticker symbol")
    effective_date: Optional[str] = Field(None, description="Date the float figure applies to")
    free_float: Optional[float] = Field(None, description="Number of freely tradable shares")
    free_float_percent: Optional[float] = Field(None, description="Free float as percent of shares outstanding")


class TechnicalIndicatorPoint(BaseEntity):
    """Single data point from a technical indicator time series."""

    timestamp: Optional[int] = Field(None, description="Unix timestamp (milliseconds)")
    value: Optional[float] = Field(None, description="Indicator value")
    # MACD-specific fields — None for SMA/EMA/RSI
    signal: Optional[float] = Field(None, description="MACD signal line value")
    histogram: Optional[float] = Field(None, description="MACD histogram value")


class TechnicalIndicators(BaseEntity):
    """Bundled technical indicator data for a stock."""

    symbol: str = Field(..., description="Ticker symbol")
    sma_50: List[TechnicalIndicatorPoint] = Field(
        default_factory=list, description="50-day Simple Moving Average"
    )
    ema_20: List[TechnicalIndicatorPoint] = Field(
        default_factory=list, description="20-day Exponential Moving Average"
    )
    macd: List[TechnicalIndicatorPoint] = Field(
        default_factory=list, description="MACD (12/26/9)"
    )
    rsi_14: List[TechnicalIndicatorPoint] = Field(
        default_factory=list, description="14-period Relative Strength Index"
    )


class IPOEvent(BaseEntity):
    """Upcoming IPO event from Polygon /vX/reference/ipos."""

    ticker: Optional[str] = Field(None, description="Ticker symbol")
    issuer_name: Optional[str] = Field(None, description="Company name")
    listing_date: Optional[str] = Field(None, description="Expected listing date")
    ipo_status: Optional[str] = Field(None, description="IPO status (e.g. pending, priced)")
    final_issue_price: Optional[float] = Field(None, description="Final issue price per share")
    shares_outstanding: Optional[float] = Field(None, description="Total shares outstanding after IPO")
    primary_exchange: Optional[str] = Field(None, description="Exchange where it will list")
    security_type: Optional[str] = Field(None, description="Security type")
    total_offer_size: Optional[float] = Field(None, description="Total dollar value of the offering")


class ExchangeStatus(BaseEntity):
    """Status of a single exchange."""

    name: Optional[str] = Field(None, description="Exchange name")
    status: Optional[str] = Field(None, description="open | closed | extended-hours")


class MarketStatus(BaseEntity):
    """Current market status from Polygon /v1/marketstatus/now."""

    market: Optional[str] = Field(None, description="Overall market status string")
    afterHours: Optional[bool] = Field(None, description="Whether after-hours session is active")
    earlyHours: Optional[bool] = Field(None, description="Whether pre-market session is active")
    serverTime: Optional[str] = Field(None, description="Server timestamp")
    nasdaq: Optional[str] = Field(None, description="NASDAQ status")
    nyse: Optional[str] = Field(None, description="NYSE status")
    otc: Optional[str] = Field(None, description="OTC status")


class SECFiling(BaseEntity):
    """SEC filing record from Polygon /stocks/filings/vX/index."""

    accession_number: Optional[str] = Field(None, description="SEC accession number")
    cik: Optional[str] = Field(None, description="SEC CIK number")
    ticker: Optional[str] = Field(None, description="Ticker symbol")
    issuer_name: Optional[str] = Field(None, description="Company name")
    filing_date: Optional[str] = Field(None, description="Date the filing was submitted")
    form_type: Optional[str] = Field(None, description="Form type (e.g. 10-K, 10-Q, 8-K)")
    filing_url: Optional[str] = Field(None, description="URL to the filing on SEC EDGAR")


class StockDetail(BaseEntity):
    """Combined stock detail: snapshot + ratios + latest short interest."""

    symbol: str = Field(..., description="Ticker symbol")
    snapshot: Optional[StockSnapshot] = Field(None, description="Real-time price snapshot")
    ratios: Optional[StockRatios] = Field(None, description="Latest financial ratios")
    shortInterest: Optional[ShortInterestData] = Field(
        None, description="Most recent short interest report"
    )
