"""
Retention service for scheduled cleanup of exports, screenshots, and logs.
Follows rules in PRD §10.3.
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, Optional
import structlog
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.config import settings
from app.models.entities import ExportFile, DiagnosticScreenshot, AuditLog, Setting

logger = structlog.get_logger(__name__)


class RetentionService:
    @staticmethod
    def get_excel_retention_days(db: Optional[Session] = None) -> int:
        """Returns the configured retention days for Excel exports (default: settings.RETENTION_EXCEL_DAYS)."""
        if db:
            try:
                st = db.get(Setting, "retention_excel_days")
                if st and st.value is not None:
                    return int(st.value)
            except Exception:
                pass
        return settings.RETENTION_EXCEL_DAYS

    @staticmethod
    def cleanup_old_data(db: Session) -> Dict[str, int]:
        """
        Executes retention policy:
        - Excel files: > configured days (default 5 days)
        - Screenshots: > 30 days (or settings.RETENTION_SCREENSHOT_DAYS)
        - Audit logs: > 365 days (or settings.RETENTION_AUDIT_DAYS)
        """
        now = datetime.now(timezone.utc)
        results = {
            "excel_deleted": 0,
            "screenshots_deleted": 0,
            "audit_deleted": 0
        }

        # 1. Clean old Export files (Database tracked)
        excel_days = RetentionService.get_excel_retention_days(db)
        excel_cutoff = now - timedelta(days=excel_days)
        old_exports = db.execute(
            select(ExportFile).filter(
                ExportFile.created_at < excel_cutoff,
                ExportFile.deleted_at.is_(None)
            )
        ).scalars().all()

        for exp in old_exports:
            full_path = settings.RUNTIME_DIR / "exports" / exp.relative_path
            try:
                if full_path.exists():
                    full_path.unlink()
            except Exception as e:
                logger.warning("Failed to delete expired export file", path=str(full_path), error=str(e))
            exp.deleted_at = now
            results["excel_deleted"] += 1

        # Also remove any orphaned or direct files older than excel_cutoff in runtime/exports
        exports_dir = settings.RUNTIME_DIR / "exports"
        if exports_dir.exists():
            cutoff_ts = excel_cutoff.timestamp()
            try:
                for f in exports_dir.glob("*.xlsx"):
                    if f.is_file() and f.stat().st_mtime < cutoff_ts:
                        try:
                            f.unlink()
                            results["excel_deleted"] += 1
                        except Exception:
                            pass
            except Exception as ex:
                logger.warning("Error checking exports directory for old files", error=str(ex))

        # 2. Clean old Screenshots
        screen_cutoff = now - timedelta(days=settings.RETENTION_SCREENSHOT_DAYS)
        old_screens = db.execute(
            select(DiagnosticScreenshot).filter(
                DiagnosticScreenshot.created_at < screen_cutoff,
                DiagnosticScreenshot.deleted_at.is_(None)
            )
        ).scalars().all()

        for sc in old_screens:
            full_path = settings.RUNTIME_DIR / "screenshots" / sc.relative_path
            try:
                if full_path.exists():
                    full_path.unlink()
            except Exception as e:
                logger.warning("Failed to delete expired screenshot", path=str(full_path), error=str(e))
            sc.deleted_at = now
            results["screenshots_deleted"] += 1

        # 3. Clean old Audit logs
        audit_cutoff = now - timedelta(days=settings.RETENTION_AUDIT_DAYS)
        stmt = delete(AuditLog).where(AuditLog.timestamp < audit_cutoff)
        audit_res = db.execute(stmt)
        results["audit_deleted"] = audit_res.rowcount or 0

        # Record cleanup in audit log
        log_entry = AuditLog(
            action="CLEANUP_RETENTION",
            target_type="system",
            details=results
        )
        db.add(log_entry)
        db.commit()

        logger.info("Retention cleanup completed", results=results)
        return results
