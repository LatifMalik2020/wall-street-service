"""Base DynamoDB repository."""

import boto3
from datetime import datetime
from typing import Any, Dict, List, Optional
from boto3.dynamodb.conditions import Key, Attr

from src.utils.config import get_settings
from src.utils.logging import logger


class DynamoDBRepository:
    """Base repository for DynamoDB operations."""

    def __init__(self, table_name: Optional[str] = None):
        """Initialize repository with DynamoDB table."""
        settings = get_settings()
        self._dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self._table_name = table_name or settings.dynamodb_table
        self._table = self._dynamodb.Table(self._table_name)

    def _now_iso(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.utcnow().isoformat() + "Z"

    def _get_item(self, pk: str, sk: str) -> Optional[Dict[str, Any]]:
        """Get single item by primary key."""
        try:
            response = self._table.get_item(Key={"PK": pk, "SK": sk})
            return response.get("Item")
        except Exception as e:
            logger.error("DynamoDB get_item error", pk=pk, sk=sk, error=str(e))
            raise

    def _put_item(self, item: Dict[str, Any]) -> None:
        """Put single item."""
        try:
            self._table.put_item(Item=item)
        except Exception as e:
            logger.error("DynamoDB put_item error", pk=item.get("PK"), error=str(e))
            raise

    def _update_item(
        self,
        pk: str,
        sk: str,
        update_expression: str,
        expression_values: Dict[str, Any],
        expression_names: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Update item and return updated attributes."""
        try:
            kwargs = {
                "Key": {"PK": pk, "SK": sk},
                "UpdateExpression": update_expression,
                "ExpressionAttributeValues": expression_values,
                "ReturnValues": "ALL_NEW",
            }
            if expression_names:
                kwargs["ExpressionAttributeNames"] = expression_names
            response = self._table.update_item(**kwargs)
            return response.get("Attributes", {})
        except Exception as e:
            logger.error("DynamoDB update_item error", pk=pk, sk=sk, error=str(e))
            raise

    def _delete_item(self, pk: str, sk: str) -> None:
        """Delete single item."""
        try:
            self._table.delete_item(Key={"PK": pk, "SK": sk})
        except Exception as e:
            logger.error("DynamoDB delete_item error", pk=pk, sk=sk, error=str(e))
            raise

    def _query(
        self,
        pk: str,
        sk_begins_with: Optional[str] = None,
        sk_between: Optional[tuple] = None,
        index_name: Optional[str] = None,
        limit: Optional[int] = None,
        scan_index_forward: bool = True,
        filter_expression: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Query items by partition key with optional sort key condition."""
        try:
            key_condition = Key("PK").eq(pk) if not index_name else Key("GSI1PK").eq(pk)

            if sk_begins_with:
                sk_key = "SK" if not index_name else "GSI1SK"
                key_condition = key_condition & Key(sk_key).begins_with(sk_begins_with)
            elif sk_between:
                sk_key = "SK" if not index_name else "GSI1SK"
                key_condition = key_condition & Key(sk_key).between(
                    sk_between[0], sk_between[1]
                )

            kwargs = {
                "KeyConditionExpression": key_condition,
                "ScanIndexForward": scan_index_forward,
            }

            if index_name:
                kwargs["IndexName"] = index_name
            if limit:
                kwargs["Limit"] = limit
            if filter_expression:
                kwargs["FilterExpression"] = filter_expression

            response = self._table.query(**kwargs)
            return response.get("Items", [])
        except Exception as e:
            logger.error("DynamoDB query error", pk=pk, error=str(e))
            raise

    def _query_paginated(
        self,
        pk: str,
        page: int = 1,
        page_size: int = 20,
        sk_begins_with: Optional[str] = None,
        index_name: Optional[str] = None,
        scan_index_forward: bool = False,
    ) -> tuple[List[Dict[str, Any]], int]:
        """Query with pagination support. Returns (items, total_count)."""
        try:
            # First get total count
            key_condition = Key("PK").eq(pk) if not index_name else Key("GSI1PK").eq(pk)
            if sk_begins_with:
                sk_key = "SK" if not index_name else "GSI1SK"
                key_condition = key_condition & Key(sk_key).begins_with(sk_begins_with)

            kwargs = {
                "KeyConditionExpression": key_condition,
                "Select": "COUNT",
            }
            if index_name:
                kwargs["IndexName"] = index_name

            count_response = self._table.query(**kwargs)
            total_count = count_response.get("Count", 0)

            # Then get page of items
            kwargs["Select"] = "ALL_ATTRIBUTES"
            kwargs["ScanIndexForward"] = scan_index_forward
            kwargs["Limit"] = page_size * page  # Fetch enough for pagination

            response = self._table.query(**kwargs)
            items = response.get("Items", [])

            # Apply offset for page
            start_index = (page - 1) * page_size
            page_items = items[start_index : start_index + page_size]

            return page_items, total_count
        except Exception as e:
            logger.error("DynamoDB query_paginated error", pk=pk, error=str(e))
            raise

    def _batch_get(self, keys: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Batch get multiple items."""
        if not keys:
            return []

        try:
            response = self._dynamodb.batch_get_item(
                RequestItems={
                    self._table_name: {
                        "Keys": [{"PK": k["pk"], "SK": k["sk"]} for k in keys]
                    }
                }
            )
            return response.get("Responses", {}).get(self._table_name, [])
        except Exception as e:
            logger.error("DynamoDB batch_get error", error=str(e))
            raise

    def _batch_write(self, items: List[Dict[str, Any]]) -> None:
        """Batch write multiple items."""
        if not items:
            return

        try:
            with self._table.batch_writer() as batch:
                for item in items:
                    batch.put_item(Item=item)
        except Exception as e:
            logger.error("DynamoDB batch_write error", error=str(e))
            raise
