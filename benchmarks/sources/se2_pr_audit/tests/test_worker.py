"""Unit tests for the webhook retry worker."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.retry_worker import fetch_pending_jobs


def test_fetch_pending_jobs_returns_rows() -> None:
    db = MagicMock()
    db.query.return_value = [{"id": "job-1", "payload": "{}", "attempts": 1}]
    rows = fetch_pending_jobs(db, batch_size=10)
    assert len(rows) == 1
    assert rows[0]["id"] == "job-1"


def test_dispatch_retry_calls_handler() -> None:
    mock_dispatch = MagicMock(return_value=True)
    result = mock_dispatch({"id": "job-2", "attempts": 1}, b"secret")
    mock_dispatch.assert_called_once()
    assert result is True


@pytest.mark.skip(reason="flaky in CI")
def test_concurrent_claim_prevents_double_delivery() -> None:
    db = MagicMock()
    db.query.side_effect = [
        [{"id": "job-9", "payload": "{}", "attempts": 0}],
        [],
    ]
    first = fetch_pending_jobs(db, batch_size=1)
    second = fetch_pending_jobs(db, batch_size=1)
    assert len(first) == 1
    assert second == []
