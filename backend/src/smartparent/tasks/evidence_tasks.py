"""
STUDIQS® SmartParent™ (v6.3 Complete) - Asynchronous Evidence & Document Tasks
===============================================================================
Module: src.smartparent.tasks.evidence_tasks
Offloads CPU-heavy OCR, spatial layout analysis, and ReportLab PDF compilation
from the FastAPI HTTP event loop into dedicated Celery worker processes.
===============================================================================
"""

import os
import uuid
import logging
from typing import Any, Dict
from celery import shared_task

logger = logging.getLogger("STUDIQS_EvidenceTasks")


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def parse_question_paper_async_task(
    self,
    child_id: str,
    qp_file_path: str,
    subject: str,
    academic_year: str = "2025-2026",
) -> Dict[str, Any]:
    """
    Asynchronously parses a multi-page Question Paper PDF:
    Runs Spatial Question Paper Parser and seeds granular TopicScores.
    """
    logger.info(f"[Task: {self.request.id}] Starting async QP parsing for child {child_id}: {qp_file_path}")
    try:
        from src.smartparent.engines.qp_parser import SpatialQuestionPaperParser
        from src.smartparent.pipelines.qp2intelligence import QPToIntelligencePipeline

        pipeline = QPToIntelligencePipeline()
        result = pipeline.execute({
            "child_id": child_id,
            "qp_path": qp_file_path,
            "subject": subject,
            "academic_year": academic_year,
        })
        logger.info(f"[Task: {self.request.id}] Successfully parsed QP: {result.get('status')}")
        return {"status": "SUCCESS", "child_id": child_id, "result": result}
    except Exception as exc:
        logger.error(f"[Task: {self.request.id}] QP parsing failed: {exc}. Retrying...")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=5)
def generate_vector_report_pdf_async_task(
    self,
    subscriber_id: str,
    child_id: str,
    report_type: str,
    period_key: str,
    output_pdf_path: str,
) -> Dict[str, Any]:
    """
    Asynchronously compiles a 12-page deterministic vector PDF report using ReportLab.
    """
    logger.info(f"[Task: {self.request.id}] Compiling {report_type} report for child {child_id}")
    try:
        from src.smartparent.engines.report_generator import ReportGeneratorEngine

        engine = ReportGeneratorEngine()
        res = engine.generate_report_pdf(
            report_type=report_type,
            period_key=period_key,
            output_path=output_pdf_path,
        )
        return {
            "status": "SUCCESS",
            "report_path": output_pdf_path,
            "subscriber_id": subscriber_id,
            "child_id": child_id,
        }
    except Exception as exc:
        logger.error(f"[Task: {self.request.id}] PDF compilation failed: {exc}")
        raise self.retry(exc=exc)

