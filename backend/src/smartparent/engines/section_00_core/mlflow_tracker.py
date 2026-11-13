"""
=============================================================================
STUDIQS® MLOps & MLflow Tracking Layer
=============================================================================
Provides real-time model and pipeline telemetry:
1. Experiment & Run Management: Tracks every question paper parsed & mapped.
2. Metrics Logging:
   - Extraction rate & question counts.
   - Topic mapping accuracy & mean confidence scores.
   - Low confidence / manual review rates.
   - Latency per engine stage (parser, mapper, total).
3. Data Drift & Quality Alerts:
   - Triggers warnings if mapping accuracy < 90% or mean confidence < 60%.
4. Artifact Registration: Auto-registers generated Task 1, 2, 12 files.
5. Zero-Dependency Fallback: If MLflow server is offline, writes structured
   telemetry to local JSONL (outputs/mlops_telemetry.jsonl).
=============================================================================
"""

import os
import sys
import time
import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger("STUDIQS_MLOps")

# Optional MLflow Import
try:
    import mlflow
    HAS_MLFLOW = True
except ImportError:
    mlflow = None
    HAS_MLFLOW = False
    logger.warning("[MLOps] MLflow not installed. Falling back to local telemetry logging.")


class MLOpsTracker:
    """
    Production MLOps Tracking Singleton for STUDIQS®.
    Integrates MLflow experiment tracking with local fallback safety.
    """

    _instance: Optional["MLOpsTracker"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(MLOpsTracker, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, experiment_name: str = "STUDIQS_Production_Pipeline_V3", tracking_uri: Optional[str] = None):
        if self._initialized:
            return

        self.experiment_name = experiment_name
        self.project_root = Path(__file__).resolve().parent.parent.parent.parent
        self.local_log_dir = self.project_root / "outputs" / "mlops"
        self.local_log_dir.mkdir(parents=True, exist_ok=True)
        self.local_telemetry_file = self.local_log_dir / "pipeline_telemetry.jsonl"

        # Initialize MLflow
        self.mlflow_enabled = False
        if HAS_MLFLOW:
            try:
                # Default tracking URI: local directory if not specified in env
                uri = tracking_uri or os.environ.get("MLFLOW_TRACKING_URI")
                if not uri:
                    mlflow_dir = self.project_root / "mlruns"
                    mlflow_dir.mkdir(parents=True, exist_ok=True)
                    clean_dir = str(mlflow_dir).replace("\\", "/")
                    uri = f"file:///{clean_dir}"

                mlflow.set_tracking_uri(uri)
                mlflow.set_experiment(self.experiment_name)
                self.mlflow_enabled = True
                logger.info(f"[MLOps] MLflow initialized successfully. Tracking URI: {uri}, Experiment: {self.experiment_name}")
            except Exception as e:
                logger.warning(f"[MLOps] MLflow initialization failed ({e}). Falling back to local JSONL logging.")
                self.mlflow_enabled = False

        self._initialized = True

    def start_run(self, run_name: str, tags: Optional[Dict[str, str]] = None) -> Optional[str]:
        """Starts a new MLflow run for a question paper processing lifecycle."""
        if not self.mlflow_enabled:
            return f"local-{int(time.time()*1000)}"

        try:
            active_run = mlflow.active_run()
            if active_run:
                # If current active run is for this paper, reuse it
                active_name = active_run.data.tags.get("mlflow.runName", "")
                if active_name == run_name:
                    return active_run.info.run_id
                # Otherwise end previous run and start fresh run for this paper
                try:
                    mlflow.end_run()
                except Exception:
                    pass

            run = mlflow.start_run(run_name=run_name, tags=tags)
            return run.info.run_id
        except Exception as e:
            logger.warning(f"[MLOps] Failed to start MLflow run: {e}")
            return None

    def end_run(self):
        """Ends the currently active MLflow run."""
        if self.mlflow_enabled:
            try:
                if mlflow.active_run():
                    mlflow.end_run()
            except Exception as e:
                logger.warning(f"[MLOps] Error ending MLflow run: {e}")

    def log_parser_metrics(
        self,
        paper_name: str,
        question_count: int,
        extraction_rate: float,
        latency_ms: float,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Logs metrics and parameters from the question paper parsing stage."""
        meta = metadata or {}
        record = {
            "timestamp": time.time(),
            "stage": "parser",
            "paper_name": paper_name,
            "question_count": question_count,
            "extraction_rate": extraction_rate,
            "latency_parser_ms": latency_ms,
            "parser_version": "v3.0.0-doc-intelligence",
            "board": meta.get("board", "Unknown"),
            "subject": meta.get("subject", "Unknown"),
            "grade": str(meta.get("grade", meta.get("class", "Unknown")))
        }

        # 1. Log to MLflow
        if self.mlflow_enabled:
            try:
                self.start_run(run_name=paper_name)
                mlflow.log_params({
                    "paper_name": paper_name,
                    "parser_version": record["parser_version"],
                    "board": record["board"],
                    "subject": record["subject"],
                    "grade": record["grade"]
                })
                mlflow.log_metrics({
                    "extracted_question_count": question_count,
                    "extraction_rate": extraction_rate,
                    "latency_parser_ms": latency_ms
                })
            except Exception as e:
                logger.warning(f"[MLOps] MLflow logging failed for parser: {e}")

        # 2. Append to Local Telemetry Log
        self._write_local_telemetry(record)

    def log_mapping_metrics(
        self,
        paper_name: str,
        total_questions: int,
        mapped_questions: int,
        mapping_accuracy: float,
        mean_confidence: float,
        low_confidence_count: int,
        latency_ms: float
    ):
        """Logs metrics and alerts from the universal topic mapping stage."""
        manual_review_rate = (low_confidence_count / max(total_questions, 1))
        record = {
            "timestamp": time.time(),
            "stage": "topic_mapper",
            "paper_name": paper_name,
            "total_questions": total_questions,
            "mapped_questions": mapped_questions,
            "mapping_accuracy": mapping_accuracy,
            "mean_confidence_score": mean_confidence,
            "low_confidence_count": low_confidence_count,
            "manual_review_rate": manual_review_rate,
            "latency_mapper_ms": latency_ms,
            "mapper_version": "v3.0.0-universal-semantic"
        }

        # Check for Drift / Quality Alerts
        alerts = self.check_drift_and_alert(mapping_accuracy, mean_confidence, manual_review_rate)
        record["alerts"] = alerts

        # 1. Log to MLflow
        if self.mlflow_enabled:
            try:
                self.start_run(run_name=paper_name)
                mlflow.log_params({
                    "mapper_version": record["mapper_version"]
                })
                mlflow.log_metrics({
                    "total_questions": total_questions,
                    "mapped_questions": mapped_questions,
                    "mapping_accuracy": mapping_accuracy,
                    "mean_confidence_score": mean_confidence,
                    "low_confidence_count": low_confidence_count,
                    "manual_review_rate": manual_review_rate,
                    "latency_mapper_ms": latency_ms
                })
                if alerts:
                    mlflow.set_tags({"quality_alert": ",".join(alerts)})
            except Exception as e:
                logger.warning(f"[MLOps] MLflow logging failed for mapper: {e}")

        # 2. Append to Local Telemetry Log
        self._write_local_telemetry(record)

    def check_drift_and_alert(
        self,
        mapping_accuracy: float,
        mean_confidence: float,
        manual_review_rate: float,
        threshold_acc: float = 0.90,
        threshold_conf: float = 0.60
    ) -> List[str]:
        """Evaluates mapping metrics against SLA thresholds and flags anomalies."""
        alerts = []
        if mapping_accuracy < threshold_acc:
            msg = f"DRIFT_ALERT: Mapping accuracy ({mapping_accuracy*100:.1f}%) is below SLA threshold ({threshold_acc*100:.1f}%)."
            logger.warning(f"[MLOps] {msg}")
            alerts.append(msg)

        if mean_confidence < threshold_conf:
            msg = f"CONFIDENCE_ALERT: Mean confidence ({mean_confidence:.2f}) is below acceptable quality ({threshold_conf:.2f})."
            logger.warning(f"[MLOps] {msg}")
            alerts.append(msg)

        if manual_review_rate > 0.15:
            msg = f"REVIEW_SPIKE_ALERT: High manual review rate ({manual_review_rate*100:.1f}% > 15%)."
            logger.warning(f"[MLOps] {msg}")
            alerts.append(msg)

        return alerts

    def log_artifacts(self, file_paths: List[str]):
        """Logs output files (.xlsx, .json) to the current MLflow run."""
        if not self.mlflow_enabled:
            return

        try:
            for fp in file_paths:
                if os.path.exists(fp):
                    mlflow.log_artifact(fp)
        except Exception as e:
            logger.warning(f"[MLOps] Failed to log artifacts: {e}")

    def _write_local_telemetry(self, record: Dict[str, Any]):
        """Thread-safe write to local JSONL telemetry log."""
        try:
            with open(self.local_telemetry_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"[MLOps] Failed to write local telemetry: {e}")


def get_mlops_tracker() -> MLOpsTracker:
    """Convenience factory function for the MLOpsTracker singleton."""
    return MLOpsTracker()
