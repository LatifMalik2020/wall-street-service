"""Shadow-portfolio DynamoDB repository (layout: SHADOW_PORTFOLIOS_DESIGN.md).

  SHADOWFILER#{cik} / PROFILE            — name, latestAccession, latestFilingDate
  SHADOWFILER#{cik} / HOLDINGS#{acc}     — target weights snapshot for a filing
  USER#{id}        / SHADOW#{cik}        — a user's shadow portfolio state
  USER#{id}        / SHADOWTRADE#{ts}#{n} — provenance-stamped shadow trades
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.repositories.base import DynamoDBRepository


def _to_ddb(obj: Any) -> Any:
    """Floats -> Decimal for DynamoDB, recursively."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_ddb(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_ddb(v) for v in obj]
    return obj


def _from_ddb(obj: Any) -> Any:
    """Decimal -> float coming back out, recursively."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _from_ddb(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_from_ddb(v) for v in obj]
    return obj


class ShadowRepository(DynamoDBRepository):
    """Persistence for shadow filers and user shadow portfolios."""

    # -- filer snapshots (written by the ingest job) --

    def put_filer_snapshot(self, cik: int, name: str, accession: str,
                           filing_date: str, targets: List[Dict]) -> None:
        pk = f"SHADOWFILER#{cik}"
        self._put_item(_to_ddb({
            "PK": pk, "SK": f"HOLDINGS#{accession}",
            "targets": targets, "filingDate": filing_date,
        }))
        self._put_item(_to_ddb({
            "PK": pk, "SK": "PROFILE", "name": name, "cik": cik,
            "latestAccession": accession, "latestFilingDate": filing_date,
            "updatedAt": self._now_iso(),
        }))

    def get_filer_profile(self, cik: int) -> Optional[Dict]:
        item = self._get_item(f"SHADOWFILER#{cik}", "PROFILE")
        return _from_ddb(item) if item else None

    def get_filer_holdings(self, cik: int, accession: str) -> Optional[Dict]:
        item = self._get_item(f"SHADOWFILER#{cik}", f"HOLDINGS#{accession}")
        return _from_ddb(item) if item else None

    # -- user shadows --

    def put_user_shadow(self, user_id: str, cik: int, portfolio: Dict) -> None:
        self._put_item(_to_ddb({
            "PK": f"USER#{user_id}", "SK": f"SHADOW#{cik}",
            **portfolio, "updatedAt": self._now_iso(),
        }))

    def get_user_shadow(self, user_id: str, cik: int) -> Optional[Dict]:
        item = self._get_item(f"USER#{user_id}", f"SHADOW#{cik}")
        return _from_ddb(item) if item else None

    def list_user_shadows(self, user_id: str) -> List[Dict]:
        items = self._query(f"USER#{user_id}", sk_begins_with="SHADOW#")
        return [_from_ddb(i) for i in items]

    def append_shadow_trades(self, user_id: str, cik: int,
                             trades: List[Dict]) -> None:
        ts = self._now_iso()
        for n, trade in enumerate(trades):
            self._put_item(_to_ddb({
                "PK": f"USER#{user_id}", "SK": f"SHADOWTRADE#{ts}#{n:03d}",
                "cik": cik, **trade,
            }))

    def list_shadow_trades(self, user_id: str, limit: int = 50) -> List[Dict]:
        items = self._query(f"USER#{user_id}", sk_begins_with="SHADOWTRADE#",
                            limit=limit, scan_index_forward=False)
        return [_from_ddb(i) for i in items]
