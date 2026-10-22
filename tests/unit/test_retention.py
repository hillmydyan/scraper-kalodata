import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from app.services.retention_service import RetentionService
from app.models.entities import Setting, ExportFile


def test_get_excel_retention_days_default():
    assert RetentionService.get_excel_retention_days(None) == 5


def test_get_excel_retention_days_from_db():
    db = MagicMock()
    mock_setting = Setting(key="retention_excel_days", value=7)
    db.get.return_value = mock_setting

    days = RetentionService.get_excel_retention_days(db)
    assert days == 7


def test_cleanup_old_data_with_custom_days():
    db = MagicMock()
    # Mock no DB setting so it defaults to 5
    db.get.return_value = None

    now = datetime.now(timezone.utc)
    # Mock exports query
    db.execute.return_value.scalars.return_value.all.return_value = []
    db.execute.return_value.rowcount = 0

    res = RetentionService.cleanup_old_data(db)
    assert "excel_deleted" in res
    assert "screenshots_deleted" in res
    assert "audit_deleted" in res
