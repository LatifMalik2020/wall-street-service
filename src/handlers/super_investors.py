"""Super investors (13F institutional filers) API handlers.

Endpoints:
    GET /wall-street/super-investors
    GET /wall-street/super-investors/{cik}/trades

Data source: SEC EDGAR JSON API (no API key required).
    Submissions: https://data.sec.gov/submissions/CIK{cik_padded}.json
"""

import json
from typing import Optional

import httpx

from src.models.base import APIResponse
from src.utils.errors import ExternalAPIError, NotFoundError, ValidationError
from src.utils.logging import logger


# ---------------------------------------------------------------------------
# Static catalog — metadata that doesn't change frequently
# ---------------------------------------------------------------------------

SUPER_INVESTOR_CATALOG: list[dict] = [
    {
        "id": "warren-buffett",
        "name": "Warren Buffett",
        "fundName": "Berkshire Hathaway",
        "cik": "0001067983",
        "description": "Chairman and CEO of Berkshire Hathaway. Known for value investing.",
    },
    {
        "id": "bill-ackman",
        "name": "Bill Ackman",
        "fundName": "Pershing Square Capital",
        "cik": "0001336545",
        "description": "Founder of Pershing Square Capital. Known for activist investing.",
    },
    {
        "id": "ray-dalio",
        "name": "Ray Dalio",
        "fundName": "Bridgewater Associates",
        "cik": "0001350694",
        "description": "Founder of Bridgewater Associates, world's largest hedge fund.",
    },
    {
        "id": "bill-gates",
        "name": "Bill Gates",
        "fundName": "Gates Foundation Trust",
        "cik": "0001166559",
        "description": "Co-founder of Microsoft; invests through the Bill & Melinda Gates Foundation Trust.",
    },
    {
        "id": "michael-burry",
        "name": "Michael Burry",
        "fundName": "Scion Asset Management",
        "cik": "0001438731",
        "description": "Founder of Scion Asset Management. Famous for shorting the 2008 housing market.",
    },
    {
        "id": "david-tepper",
        "name": "David Tepper",
        "fundName": "Appaloosa Management",
        "cik": "0001006438",
        "description": "Founder of Appaloosa Management. Known for distressed debt and value plays.",
    },
    {
        "id": "stanley-druckenmiller",
        "name": "Stanley Druckenmiller",
        "fundName": "Duquesne Family Office",
        "cik": "0001536411",
        "description": "Founder of Duquesne Capital. Managed George Soros's Quantum Fund.",
    },
    {
        "id": "george-soros",
        "name": "George Soros",
        "fundName": "Soros Fund Management",
        "cik": "0001029160",
        "description": "Chairman of Soros Fund Management. Famous for breaking the Bank of England.",
    },
]

# Map CIK → catalog entry for O(1) lookups
_CATALOG_BY_CIK: dict[str, dict] = {inv["cik"]: inv for inv in SUPER_INVESTOR_CATALOG}

_EDGAR_BASE = "https://data.sec.gov"
_EDGAR_HEADERS = {
    "User-Agent": "TradeStreak admin@tradestreak.net",
    "Accept-Encoding": "gzip, deflate",
}
_EDGAR_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _response(status_code: int, body: dict) -> dict:
    """Format API response with JSON string body and CORS headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body),
    }


def _pad_cik(cik: str) -> str:
    """Strip leading zeros then zero-pad to 10 digits (SEC EDGAR format)."""
    numeric = cik.lstrip("0") or "0"
    return numeric.zfill(10)


def _validate_cik_format(cik: str) -> str:
    """Return 10-digit zero-padded CIK string or raise ValidationError."""
    cleaned = cik.strip()
    if not cleaned:
        raise ValidationError("CIK is required", field="cik")
    digits_only = cleaned.lstrip("0")
    if not digits_only.isdigit() and digits_only != "":
        raise ValidationError(
            f"Invalid CIK format: {cik!r}. Must be a numeric string.", field="cik"
        )
    return _pad_cik(cleaned)


def _fetch_edgar_submissions(cik_padded: str) -> dict:
    """Synchronous HTTP call to SEC EDGAR submissions endpoint.

    Returns the raw JSON dict from:
        GET https://data.sec.gov/submissions/CIK{cik_padded}.json
    """
    url = f"{_EDGAR_BASE}/submissions/CIK{cik_padded}.json"
    try:
        with httpx.Client(timeout=_EDGAR_TIMEOUT) as client:
            response = client.get(url, headers=_EDGAR_HEADERS)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise NotFoundError("SECFiling", f"CIK {cik_padded}")
        raise ExternalAPIError("SEC EDGAR", str(exc))
    except httpx.HTTPError as exc:
        raise ExternalAPIError("SEC EDGAR", str(exc))


def _extract_13f_filings(submissions: dict, limit: int = 10) -> list[dict]:
    """Extract 13F-HR filing records from SEC submissions JSON.

    The submissions JSON contains a 'filings' object with 'recent' arrays
    (accessionNumbers, filingDate, form, etc.) as parallel arrays.
    """
    filings_block = submissions.get("filings", {})
    recent = filings_block.get("recent", {})

    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    accession_numbers = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    descriptions = recent.get("primaryDocDescription", [])

    results: list[dict] = []
    for i, form_type in enumerate(forms):
        if form_type not in ("13F-HR", "13F-HR/A"):
            continue

        accession = accession_numbers[i] if i < len(accession_numbers) else ""
        filing_date = filing_dates[i] if i < len(filing_dates) else ""
        primary_doc = primary_docs[i] if i < len(primary_docs) else ""
        description = descriptions[i] if i < len(descriptions) else ""

        # Build EDGAR viewer URL
        acc_clean = accession.replace("-", "")
        cik_from_sub = submissions.get("cik", "")
        edgar_url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik_from_sub}/"
            f"{acc_clean}/{primary_doc}"
            if primary_doc
            else f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik_from_sub}&type=13F-HR"
        )

        results.append(
            {
                "filingDate": filing_date,
                "formType": form_type,
                "accessionNumber": accession,
                "description": description,
                "filingUrl": edgar_url,
                # Holdings parsing from XML is out of scope for MVP;
                # return empty list so iOS can gracefully handle it
                "holdings": [],
            }
        )

        if len(results) >= limit:
            break

    return results


def _build_investor_summary(catalog_entry: dict, submissions: Optional[dict]) -> dict:
    """Merge static catalog metadata with live EDGAR filing data."""
    recent_trade_count = 0
    last_filing_date: Optional[str] = None

    if submissions:
        filings = _extract_13f_filings(submissions, limit=20)
        recent_trade_count = len(filings)
        if filings:
            last_filing_date = filings[0]["filingDate"]

    return {
        "id": catalog_entry["id"],
        "name": catalog_entry["name"],
        "fundName": catalog_entry["fundName"],
        "cik": catalog_entry["cik"],
        "description": catalog_entry.get("description", ""),
        # AUM is not reliably available from EDGAR without parsing the full XML;
        # return None so the iOS view shows a placeholder
        "aum": None,
        "recentTradeCount": recent_trade_count,
        "lastFilingDate": last_filing_date,
    }


# ---------------------------------------------------------------------------
# Public handlers
# ---------------------------------------------------------------------------


def get_super_investors() -> dict:
    """Return list of tracked super investors with filing metadata.

    GET /wall-street/super-investors

    Fetches live EDGAR submissions for each investor to get their latest 13F
    filing date and count. Failures for individual investors are logged and
    skipped so a single EDGAR outage doesn't break the whole list.
    """
    logger.info("Fetching super investor list", count=len(SUPER_INVESTOR_CATALOG))

    investors: list[dict] = []

    for catalog_entry in SUPER_INVESTOR_CATALOG:
        cik_padded = _pad_cik(catalog_entry["cik"])
        submissions: Optional[dict] = None
        try:
            submissions = _fetch_edgar_submissions(cik_padded)
        except (ExternalAPIError, NotFoundError) as exc:
            # Non-fatal — surface static metadata without live filing count
            logger.warning(
                "EDGAR fetch failed for investor",
                name=catalog_entry["name"],
                cik=catalog_entry["cik"],
                error=str(exc),
            )

        investor_summary = _build_investor_summary(catalog_entry, submissions)
        investors.append(investor_summary)

    return _response(
        200,
        APIResponse(
            success=True,
            data={"investors": investors},
        ).model_dump(mode="json"),
    )


def get_super_investor_trades(cik: str) -> dict:
    """Return 13F filing history for a specific CIK.

    GET /wall-street/super-investors/{cik}/trades

    For MVP, returns filing metadata (date, form type, accession number) without
    parsing individual holdings from the XML — that requires an additional EDGAR
    HTTP round-trip per filing.
    """
    cik_padded = _validate_cik_format(cik)

    # Match catalog entry by normalised CIK (both sides zero-padded to 10 digits)
    catalog_entry = next(
        (inv for inv in SUPER_INVESTOR_CATALOG if _pad_cik(inv["cik"]) == cik_padded),
        None,
    )

    investor_meta: dict
    if catalog_entry:
        investor_meta = {
            "name": catalog_entry["name"],
            "cik": catalog_entry["cik"],
            "fundName": catalog_entry["fundName"],
        }
    else:
        # Unknown CIK — attempt to resolve name from EDGAR entity data
        investor_meta = {
            "name": "Unknown Investor",
            "cik": cik.strip(),
            "fundName": "Unknown Fund",
        }

    logger.info(
        "Fetching 13F filings for investor",
        cik=cik_padded,
        name=investor_meta.get("name"),
    )

    submissions = _fetch_edgar_submissions(cik_padded)

    # Try to resolve name from EDGAR if not in catalog
    if not catalog_entry:
        entity_name = submissions.get("name", "")
        if entity_name:
            investor_meta["name"] = entity_name

    filings = _extract_13f_filings(submissions, limit=20)

    logger.info(
        "Retrieved 13F filings",
        cik=cik_padded,
        filing_count=len(filings),
    )

    return _response(
        200,
        APIResponse(
            success=True,
            data={
                "investor": investor_meta,
                "trades": filings,
            },
        ).model_dump(mode="json"),
    )
