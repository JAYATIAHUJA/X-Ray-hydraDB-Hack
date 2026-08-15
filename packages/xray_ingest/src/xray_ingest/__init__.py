"""Deterministic ingestion and evidence persistence for X-Ray."""

from .sources import SourceAdapterError, code_records, email_records, slack_records, ticket_records

__all__ = [
    "SourceAdapterError",
    "code_records",
    "email_records",
    "slack_records",
    "ticket_records",
]
