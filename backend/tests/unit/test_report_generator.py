"""
Unit Tests for STUDIQS® SmartParent™ Report Generation Engine (Engine 14)
Verifies:
  - Vector PDF compilation via ReportLab 2-Pass NumberedCanvas
  - Valid PDF magic bytes (%PDF-) and page count calculation
  - Dynamic parent pulse auto-synthesis if not provided
  - Custom output path overrides
  - Structured JSON diagnostic payload generation (scorecards, summaries, gap watchlist)
  - English-only text enforcement (no bilingual/Tamil text)
  - Zero-crash fallback degradation on corrupt inputs
"""

import os
from pathlib import Path
import pytest
from src.smartparent.engines.report_generator import (
    ReportGenerator,
    ReportGenerationResult,
    StudentProfileSchema
)


@pytest.fixture
def report_generator(tmp_path):
    # Use isolated temporary directory for test report outputs
    return ReportGenerator(output_dir=tmp_path / "test_reports")


def test_report_generator_end_to_end_pdf_creation(report_generator, tmp_path):
    """Verifies complete PDF rendering pipeline, file existence, and PDF magic headers."""
    payload = {
        "report_type": "MONTHLY_CONSOLIDATED",
        "student_profile": {
            "student_name": "Aarav Sharma",
            "standard_class": "Class 10",
            "board": "CBSE",
            "school_name": "Studiqs Demo High School"
        },
        "subject_trajectories": {
            "Mathematics": {
                "latest_percentage": 84.5,
                "movement_indicator": "↑ +5.5%",
                "trajectory_status": "IMPROVING",
                "consistency_index": 92.0,
                "total_tests": 4
            },
            "Science": {
                "latest_percentage": 68.0,
                "movement_indicator": "↓ -4.0%",
                "trajectory_status": "DECLINING",
                "consistency_index": 78.5,
                "total_tests": 3
            },
            "Social Science": {
                "latest_percentage": 88.0,
                "movement_indicator": "→ 0.0%",
                "trajectory_status": "STABLE",
                "consistency_index": 95.0,
                "total_tests": 2
            }
        },
        "active_gaps": [
            "Optics: Refraction of Light",
            "Quadratic Equations: Word Problems",
            "Periodic Classification of Elements"
        ]
    }

    result = report_generator.execute(payload)

    assert isinstance(result, ReportGenerationResult)
    assert result.generation_status == "SUCCESS"
    assert result.student_name == "Aarav Sharma"
    assert result.pdf_path is not None
    assert os.path.exists(result.pdf_path)

    # Verify PDF file headers
    with open(result.pdf_path, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-"

    assert result.pdf_bytes_size > 1000  # ReportLab vector output is typically > 5KB
    assert result.total_pages >= 1
    assert len(result.subject_scorecard) == 3


def test_report_generator_auto_synthesizes_pulse_digest(report_generator):
    """Verifies that ReportGenerator dynamically generates parent pulse cards if not provided."""
    payload = {
        "student_profile": {
            "student_name": "Priya Nair",
            "standard_class": "Class 9",
            "board": "ICSE"
        },
        "subject_trajectories": {
            "Physics": {
                "latest_percentage": 86.0,
                "direction_delta_60d": 6.0,
                "trajectory_status": "IMPROVING"
            },
            "Chemistry": {
                "latest_percentage": 56.0,
                "direction_delta_60d": -7.0,
                "trajectory_status": "DECLINING"
            }
        },
        "active_gaps": ["Atomic Structure and Chemical Bonding"]
        # Notice: parent_pulse_digest is NOT passed here
    }

    result = report_generator.execute(payload)

    assert result.generation_status == "SUCCESS"
    assert "improvement_area" in result.parent_pulse_digest
    assert "watch_area" in result.parent_pulse_digest
    assert "next_immediate_action" in result.parent_pulse_digest

    # Pulse digest should highlight Chemistry / Atomic Structure in watch area
    watch_card = result.parent_pulse_digest["watch_area"]
    assert "Chemistry" in watch_card.get("headline", "") or "Atomic Structure" in watch_card.get("headline", "")


def test_report_generator_custom_output_path(report_generator, tmp_path):
    """Verifies writing PDF to an explicitly provided file path."""
    custom_pdf = tmp_path / "custom_folder" / "aarav_term1_report.pdf"

    payload = {
        "student_profile": {"student_name": "Siddharth Rao"},
        "pdf_output_path": str(custom_pdf),
        "subject_trajectories": {
            "Mathematics": {"latest_percentage": 90.0, "movement_indicator": "↑ +2.0%"}
        }
    }

    result = report_generator.execute(payload)

    assert result.generation_status == "SUCCESS"
    assert result.pdf_path == str(custom_pdf)
    assert custom_pdf.exists()
    assert custom_pdf.stat().st_size > 500


def test_report_generator_structured_scorecard_data(report_generator):
    """Verifies structured subject scorecard calculations and executive averages."""
    payload = {
        "student_profile": {"student_name": "Meera Krishnan"},
        "subject_trajectories": {
            "English": {"latest_percentage": 80.0},
            "Mathematics": {"latest_percentage": 90.0},
            "Science": {"latest_percentage": 70.0}
        }
    }

    result = report_generator.execute(payload)

    assert len(result.subject_scorecard) == 3
    # Average of 80, 90, 70 is 80.0
    assert result.executive_summary["overall_average"] == 80.0


def test_report_generator_english_only_compliance(report_generator):
    """Verifies that generated structured summary and cards contain no Tamil characters."""
    payload = {
        "student_profile": {"student_name": "Vijay Balaji", "board": "CBSE"},
        "subject_trajectories": {
            "Mathematics": {"latest_percentage": 75.0, "direction_delta_60d": 3.0},
            "Science": {"latest_percentage": 65.0, "direction_delta_60d": -4.0}
        },
        "active_gaps": ["Cell Structure and Functions"]
    }

    result = report_generator.execute(payload)

    # Check student name, summaries, and pulse card contents
    combined_texts = [
        result.student_name,
        str(result.executive_summary),
        str(result.parent_pulse_digest)
    ]
    for text in combined_texts:
        assert not any('\u0b80' <= c <= '\u0bff' for c in text), (
            f"Tamil characters detected in report output: {text}"
        )


def test_report_generator_fallback_on_corrupt_data(report_generator):
    """Verifies safe non-crashing degraded result when payload is corrupt."""
    result = report_generator.execute({})

    assert isinstance(result, ReportGenerationResult)
    assert result.generation_status == "DEGRADED"
    assert result.pdf_path is None
    assert result.total_pages == 0
    assert "error" in result.executive_summary
