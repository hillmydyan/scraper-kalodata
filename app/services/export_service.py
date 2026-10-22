"""
Export service orchestrating the generation and registration of Excel files.
Follows rules in PRD §10 and §11.
"""

from datetime import datetime, timezone
from typing import Optional
import structlog
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.entities import ScrapeJob, KalodataProductResult, KalodataCreatorProductResult, ExportFile, AuditLog
from app.exports.excel import ExcelExporter

logger = structlog.get_logger(__name__)


class ExportService:
    @staticmethod
    def export_job_results(
        db: Session,
        job_id: str,
        force_reexport: bool = False
    ) -> Optional[ExportFile]:
        """
        Exports job product/creator results into Excel workbook and registers in export_files.
        """
        job = db.get(ScrapeJob, job_id)
        if not job:
            logger.warning("ScrapeJob not found for export", job_id=job_id)
            return None

        # Determine version
        existing_exports = db.execute(
            select(ExportFile).filter_by(scrape_job_id=job_id)
        ).scalars().all()
        version = len(existing_exports) + 1 if existing_exports else 1

        items = []
        if job.module == "creator":
            c_results = db.execute(
                select(KalodataCreatorProductResult)
                .filter_by(scrape_job_id=job_id)
                .order_by(
                    KalodataCreatorProductResult.creator_rank.asc().nullslast(),
                    KalodataCreatorProductResult.creator_name.asc(),
                    KalodataCreatorProductResult.product_rank.asc().nullslast(),
                    KalodataCreatorProductResult.revenue_value.desc().nullslast()
                )
            ).scalars().all()
            for r in c_results:
                items.append({
                    "creator_name": r.creator_name,
                    "creator_id": r.creator_id,
                    "creator_rank": r.creator_rank,
                    "product_rank": r.product_rank,
                    "source_product_id": r.source_product_id,
                    "product_name": r.product_name,
                    "shop_name": r.shop_name,
                    "product_url": r.product_url,
                    "revenue_value": float(r.revenue_value) if r.revenue_value is not None else None,
                    "revenue_raw": r.revenue_raw,
                    "sales_value": r.sales_value,
                    "sales_raw": r.sales_raw,
                    "commission_rate": float(r.commission_rate) if r.commission_rate is not None else None,
                    "commission_raw": r.commission_raw,
                    "currency_code": r.currency_code,
                    "country_code": r.country_code,
                    "scraped_at": r.scraped_at,
                    "scrape_job_id": r.scrape_job_id
                })
        else:
            # Fetch product results ordered by highest revenue descending (matching Kalodata table)
            results = db.execute(
                select(KalodataProductResult)
                .filter_by(scrape_job_id=job_id)
                .order_by(KalodataProductResult.revenue_value.desc().nullslast())
            ).scalars().all()

            for r in results:
                items.append({
                    "source_product_id": r.source_product_id,
                    "product_name": r.product_name,
                    "shop_name": r.shop_name,
                    "product_url": r.product_url,
                    "revenue_value": float(r.revenue_value) if r.revenue_value is not None else None,
                    "revenue_raw": r.revenue_raw,
                    "sales_value": r.sales_value,
                    "sales_raw": r.sales_raw,
                    "commission_rate": float(r.commission_rate) if r.commission_rate is not None else None,
                    "commission_raw": r.commission_raw,
                    "currency_code": r.currency_code,
                    "country_code": r.country_code,
                    "video_url": r.video_url,
                    "video_url_type": r.video_url_type,
                    "video_selection_method": r.video_selection_method,
                    "scraped_at": r.scraped_at,
                    "scrape_job_id": r.scrape_job_id
                })

        meta = {
            "module": job.module,
            "revenue_source_method": (job.meta or {}).get("revenue_source_method", "product_filter"),
            "rows_rejected": job.rows_rejected,
            "notes": job.error_summary or "Exported successfully"
        }

        run_date = (job.started_at or datetime.now(timezone.utc)).date()
        excel_meta = ExcelExporter.generate_excel_file(
            country_code=job.country_code,
            run_date=run_date,
            period_date=job.period_start,
            status=job.status,
            items=items,
            job_metadata=meta,
            version=version,
            module=job.module
        )

        if not excel_meta:
            logger.info("No export file created (e.g. empty file disabled)", job_id=job_id)
            return None

        export_entry = ExportFile(
            scrape_job_id=job.id,
            country_code=job.country_code,
            module=job.module,
            period_start=job.period_start,
            period_end=job.period_end,
            file_name=excel_meta["file_name"],
            relative_path=excel_meta["relative_path"],
            row_count=excel_meta["row_count"],
            status=excel_meta["status"],
            version=version,
            size_bytes=excel_meta["size_bytes"],
            checksum_sha256=excel_meta["checksum_sha256"]
        )
        db.add(export_entry)

        # Audit log
        audit = AuditLog(
            action="EXPORT_EXCEL",
            target_type="export_file",
            target_id=export_entry.id,
            details={
                "file_name": export_entry.file_name,
                "rows": export_entry.row_count,
                "version": version
            }
        )
        db.add(audit)
        db.commit()
        db.refresh(export_entry)

        logger.info("Excel export completed and recorded", file_name=export_entry.file_name)
        return export_entry
