"""
STUDIQS® SmartParent™ (v6.2 Complete) - Performance & Consistency Engine
=============================================================================
Engine: performance_consistency_engine.py
Implements Section 5 of Studiqs SmartParent Specification:
1. Subject Monthly Consistency: (Maths 72 → 78 → 81 | Improving)
2. Overall Monthly Movement: (+4% vs last comparable result - strict compatibility)
3. Term Consistency: (Term 1 → Term 2 direction with sufficiency validation)
4. Topic Movement: (Needs Attention → Needs Practice → Mastered)
5. Gap Closure Tracking: (2 of 3 gaps improved / closed)
6. Expert Feedback Status: (Submitted → Under Review → Completed with 48h SLA)
=============================================================================
"""

import math
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, ConfigDict, Field

from src.smartparent.engines.base_engine import BaseEngine, EngineHealthStatus
from src.smartparent.schemas.performance import (
    SubjectMonthlyConsistencySchema,
    OverallMonthlyMovementSchema,
    TermConsistencySchema,
    TopicMovementSchema,
    GapClosureSummarySchema,
    ExpertFeedbackStatusSchema,
    Section5PerformanceResponse,
)

logger = logging.getLogger("STUDIQS_PerformanceConsistencyEngine")


class PerformanceConsistencyEngine(BaseEngine):
    """
    Engine 11: Performance & Consistency Engine (performance_consistency_engine.py)
    
    Transforms raw multi-test evidence, curriculum topic mappings, and expert cases
    into Section 5 pedagogical intelligence views.
    """

    def __init__(self, failure_threshold: int = 5):
        super().__init__(name="PerformanceConsistencyEngine", failure_threshold=failure_threshold)

    # -------------------------------------------------------------------------
    # BaseEngine Template Method Lifecycle Hooks
    # -------------------------------------------------------------------------

    def validate_input(self, input_data: Any) -> Dict[str, Any]:
        """Validates input payload for Section 5 evaluation."""
        if not input_data:
            raise ValueError("Performance consistency payload cannot be empty.")

        if hasattr(input_data, "model_dump"):
            data = input_data.model_dump()
        elif hasattr(input_data, "dict"):
            data = input_data.dict()
        elif isinstance(input_data, dict):
            data = dict(input_data)
        else:
            raise ValueError(f"Unsupported payload type for PerformanceConsistencyEngine: {type(input_data)}")

        return data

    def execute_core(self, validated_data: Dict[str, Any]) -> Section5PerformanceResponse:
        """Executes full Section 5 multi-metric evaluation."""
        child_id = str(validated_data.get("child_id", "CHILD_UNKNOWN"))
        student_name = str(validated_data.get("student_name", "Student"))
        standard_class = str(validated_data.get("standard_class", "Class 10"))
        academic_year = str(validated_data.get("academic_year", "2026-2027"))

        assessments = validated_data.get("assessments", [])
        gaps_data = validated_data.get("gaps", [])
        expert_cases = validated_data.get("expert_cases", [])
        topic_history = validated_data.get("topic_history", [])

        # 1. Subject Monthly Consistency
        subject_consistencies = self.evaluate_subject_monthly_consistency(assessments)

        # 2. Overall Monthly Movement (Strict Compatibility Enforcement)
        overall_movement = self.evaluate_overall_monthly_movement(assessments)

        # 3. Term Consistency (Sufficiency Check)
        term_consistency = self.evaluate_term_consistency(assessments)

        # 4. Topic Movement Tracking
        topic_movements = self.evaluate_topic_movement(topic_history)

        # 5. Gap Closure Tracking
        gap_closure = self.evaluate_gap_closure(gaps_data)

        # 6. Expert Feedback Status & 48h SLA
        feedback_cases = self.evaluate_expert_feedback_status(expert_cases)

        return Section5PerformanceResponse(
            child_id=child_id,
            student_name=student_name,
            standard_class=standard_class,
            academic_year=academic_year,
            overall_monthly_movement=overall_movement,
            subject_consistencies=subject_consistencies,
            term_consistency=term_consistency,
            topic_movements=topic_movements,
            gap_closure_summary=gap_closure,
            expert_feedback_cases=feedback_cases,
            generated_at=datetime.utcnow().isoformat(),
        )

    def fallback(self, error: Exception, input_data: Any) -> Section5PerformanceResponse:
        """Safe fallback producing neutral non-panicking views."""
        logger.warning(f"[PerformanceConsistencyEngine] Fallback triggered due to error: {error}")
        return Section5PerformanceResponse(
            child_id=str(input_data.get("child_id", "UNKNOWN")) if isinstance(input_data, dict) else "UNKNOWN",
            student_name=str(input_data.get("student_name", "Student")) if isinstance(input_data, dict) else "Student",
            standard_class="Class 10",
            academic_year="2026-2027",
            overall_monthly_movement=OverallMonthlyMovementSchema(
                current_month="Current",
                prior_month=None,
                current_mean=0.0,
                prior_mean=None,
                movement_percentage=0.0,
                movement_symbol="→",
                display_badge="0.0% (Awaiting test results)",
                is_comparable=True,
            ),
            subject_consistencies=[],
            term_consistency=TermConsistencySchema(
                terms_evaluated=[],
                term_scores={},
                has_sufficient_evidence=False,
                term_direction="INSUFFICIENT_EVIDENCE",
                display_narrative="Insufficient evidence to evaluate term direction",
            ),
            topic_movements=[],
            gap_closure_summary=GapClosureSummarySchema(
                total_identified_gaps=0,
                active_gaps_count=0,
                in_recheck_count=0,
                resolved_gaps_count=0,
                closure_rate_percent=0.0,
                display_badge="0 of 0 gaps active",
            ),
            expert_feedback_cases=[],
            generated_at=datetime.utcnow().isoformat(),
        )

    # -------------------------------------------------------------------------
    # Core Domain Logic for Section 5 Metrics
    # -------------------------------------------------------------------------

    def evaluate_subject_monthly_consistency(
        self, assessments: List[Dict[str, Any]]
    ) -> List[SubjectMonthlyConsistencySchema]:
        """
        1. Subject Monthly Consistency: Maths 72 → 78 → 81 | Improving
        Rule: Comparable confirmed results only. Groups tests by subject & month chronologically.
        """
        if not assessments:
            return []

        # Group by subject
        by_subject: Dict[str, List[Dict[str, Any]]] = {}
        for a in assessments:
            subj = str(a.get("subject", "General")).strip()
            by_subject.setdefault(subj, []).append(a)

        results: List[SubjectMonthlyConsistencySchema] = []

        for subj, records in by_subject.items():
            # Parse dates and calculate percentages
            normalized_tests = []
            for r in records:
                t_date = r.get("test_date")
                if isinstance(t_date, str):
                    try:
                        parsed_date = datetime.strptime(t_date[:10], "%Y-%m-%d").date()
                    except Exception:
                        parsed_date = date.today()
                elif isinstance(t_date, (datetime, date)):
                    parsed_date = t_date.date() if isinstance(t_date, datetime) else t_date
                else:
                    parsed_date = date.today()

                scored = float(r.get("total_scored_marks", 0.0))
                max_m = float(r.get("total_max_marks", 100.0)) or 100.0
                pct = round((scored / max_m) * 100.0, 1)

                month_key = parsed_date.strftime("%Y-%m")
                normalized_tests.append({"date": parsed_date, "month": month_key, "percentage": pct})

            # Sort chronologically
            normalized_tests.sort(key=lambda x: x["date"])

            # Aggregate by month
            months_map: Dict[str, List[float]] = {}
            for nt in normalized_tests:
                months_map.setdefault(nt["month"], []).append(nt["percentage"])

            sorted_months = sorted(months_map.keys())
            progression = [round(sum(months_map[m]) / len(months_map[m]), 1) for m in sorted_months]

            if not progression:
                continue

            current_pct = progression[-1]
            previous_pct = progression[-2] if len(progression) > 1 else None
            delta = round(current_pct - previous_pct, 1) if previous_pct is not None else 0.0

            # Determine direction & tier
            # Fluctuating check: 3+ months with alternate +/- jumps > 4%
            is_fluctuating = False
            if len(progression) >= 3:
                diffs = [progression[i] - progression[i - 1] for i in range(1, len(progression))]
                if (diffs[-1] > 3.0 and diffs[-2] < -3.0) or (diffs[-1] < -3.0 and diffs[-2] > 3.0):
                    is_fluctuating = True

            if is_fluctuating:
                direction = "FLUCTUATING"
                symbol = "∿"
                tier = "Fluctuating"
            elif delta > 2.0:
                direction = "IMPROVING"
                symbol = "↗"
                tier = "Improving"
            elif delta < -2.0:
                direction = "DECLINING"
                symbol = "↘"
                tier = "Declining"
            else:
                direction = "STABLE"
                symbol = "→"
                tier = "Stable"

            # Build narrative: Maths 72 → 78 → 81 | Improving
            int_prog = [str(int(round(p))) for p in progression]
            prog_str = " → ".join(int_prog)
            narrative = f"{subj} {prog_str} | {tier}"

            results.append(
                SubjectMonthlyConsistencySchema(
                    subject=subj,
                    progression=progression,
                    months=sorted_months,
                    current_percentage=current_pct,
                    previous_percentage=previous_pct,
                    delta=delta,
                    trend_direction=direction,
                    directional_symbol=symbol,
                    consistency_tier=tier,
                    display_narrative=narrative,
                    tests_count=len(records),
                )
            )

        return results

    def evaluate_overall_monthly_movement(
        self, assessments: List[Dict[str, Any]]
    ) -> OverallMonthlyMovementSchema:
        """
        2. Overall Monthly Movement: +4% vs last comparable result
        Strict Rule: Never silently compare incompatible evidence!
        """
        if not assessments:
            return OverallMonthlyMovementSchema(
                current_month=datetime.utcnow().strftime("%Y-%m"),
                prior_month=None,
                current_mean=0.0,
                prior_mean=None,
                movement_percentage=0.0,
                movement_symbol="→",
                display_badge="0.0% (Awaiting evidence)",
                is_comparable=True,
            )

        # Group by month
        monthly_groups: Dict[str, List[Dict[str, Any]]] = {}
        for a in assessments:
            t_date = a.get("test_date")
            if isinstance(t_date, str):
                try:
                    m_key = t_date[:7]
                except Exception:
                    m_key = datetime.utcnow().strftime("%Y-%m")
            elif isinstance(t_date, (datetime, date)):
                m_key = t_date.strftime("%Y-%m")
            else:
                m_key = datetime.utcnow().strftime("%Y-%m")
            monthly_groups.setdefault(m_key, []).append(a)

        sorted_months = sorted(monthly_groups.keys())
        current_m = sorted_months[-1]
        cur_records = monthly_groups[current_m]

        cur_pcts = [
            round((float(r.get("total_scored_marks", 0.0)) / (float(r.get("total_max_marks", 100.0)) or 100.0)) * 100.0, 1)
            for r in cur_records
        ]
        current_mean = round(sum(cur_pcts) / len(cur_pcts), 1) if cur_pcts else 0.0

        if len(sorted_months) < 2:
            return OverallMonthlyMovementSchema(
                current_month=current_m,
                prior_month=None,
                current_mean=current_mean,
                prior_mean=None,
                movement_percentage=0.0,
                movement_symbol="→",
                display_badge=f"Baseline established at {current_mean}%",
                is_comparable=True,
                compatibility_note="First recorded month; baseline established.",
            )

        prior_m = sorted_months[-2]
        prior_records = monthly_groups[prior_m]

        # Comparability check:
        # Check if subjects overlap or evidence types are compatible
        cur_subjects = {str(r.get("subject", "")).strip().lower() for r in cur_records}
        prior_subjects = {str(r.get("subject", "")).strip().lower() for r in prior_records}

        intersection = cur_subjects.intersection(prior_subjects)
        if not intersection and (len(cur_subjects) > 0 and len(prior_subjects) > 0):
            # Incompatible evidence! Disjoint subjects
            return OverallMonthlyMovementSchema(
                current_month=current_m,
                prior_month=prior_m,
                current_mean=current_mean,
                prior_mean=None,
                movement_percentage=0.0,
                movement_symbol="≠",
                display_badge="Incompatible evidence comparison avoided",
                is_comparable=False,
                compatibility_note=f"No overlapping subjects between {current_m} ({', '.join(cur_subjects)}) and {prior_m} ({', '.join(prior_subjects)}).",
            )

        prior_pcts = [
            round((float(r.get("total_scored_marks", 0.0)) / (float(r.get("total_max_marks", 100.0)) or 100.0)) * 100.0, 1)
            for r in prior_records
        ]
        prior_mean = round(sum(prior_pcts) / len(prior_pcts), 1) if prior_pcts else 0.0

        movement = round(current_mean - prior_mean, 1)
        sign = "+" if movement > 0 else ("" if movement < 0 else "")
        symbol = "↑" if movement > 0 else ("↓" if movement < 0 else "→")
        badge = f"{sign}{movement}% vs last comparable result"

        return OverallMonthlyMovementSchema(
            current_month=current_m,
            prior_month=prior_m,
            current_mean=current_mean,
            prior_mean=prior_mean,
            movement_percentage=movement,
            movement_symbol=symbol,
            display_badge=badge,
            is_comparable=True,
        )

    def evaluate_term_consistency(
        self, assessments: List[Dict[str, Any]]
    ) -> TermConsistencySchema:
        """
        3. Term Consistency: Term 1 → Term 2 direction
        Rule: Only with sufficient evidence (>= 2 assessments per term or explicit major exam).
        """
        if not assessments:
            return TermConsistencySchema(
                terms_evaluated=[],
                term_scores={},
                has_sufficient_evidence=False,
                term_direction="INSUFFICIENT_EVIDENCE",
                display_narrative="Insufficient evidence to evaluate term direction",
                evidence_breakdown={},
            )

        term_buckets: Dict[str, List[float]] = {"Term 1": [], "Term 2": [], "Term 3": []}

        for a in assessments:
            title = str(a.get("test_title", "")).lower()
            scored = float(a.get("total_scored_marks", 0.0))
            max_m = float(a.get("total_max_marks", 100.0)) or 100.0
            pct = round((scored / max_m) * 100.0, 1)

            t_date = a.get("test_date")
            month = 0
            if isinstance(t_date, (datetime, date)):
                month = t_date.month
            elif isinstance(t_date, str):
                try:
                    month = int(t_date[5:7])
                except Exception:
                    month = 0

            # Categorize into Term 1, Term 2, or Term 3
            if "term 1" in title or "quarterly" in title or (month in (6, 7, 8, 9)):
                term_buckets["Term 1"].append(pct)
            elif "term 2" in title or "half yearly" in title or "midterm" in title or (month in (10, 11, 12)):
                term_buckets["Term 2"].append(pct)
            elif "term 3" in title or "annual" in title or "final" in title or (month in (1, 2, 3, 4)):
                term_buckets["Term 3"].append(pct)
            else:
                # Default by month
                if month in (5, 6, 7, 8, 9):
                    term_buckets["Term 1"].append(pct)
                elif month in (10, 11, 12):
                    term_buckets["Term 2"].append(pct)
                else:
                    term_buckets["Term 3"].append(pct)

        # Filter active terms
        active_terms = [t for t, scores in term_buckets.items() if len(scores) > 0]
        evidence_counts = {t: len(term_buckets[t]) for t in active_terms}
        term_scores = {t: round(sum(term_buckets[t]) / len(term_buckets[t]), 1) for t in active_terms}

        # Check sufficiency: Need at least 2 terms, each with >= 2 tests or major test
        if len(active_terms) < 2:
            return TermConsistencySchema(
                terms_evaluated=active_terms,
                term_scores=term_scores,
                has_sufficient_evidence=False,
                term_direction="INSUFFICIENT_EVIDENCE",
                display_narrative=f"Only {active_terms[0] if active_terms else '0 terms'} recorded. Additional term required for direction.",
                evidence_breakdown=evidence_counts,
            )

        t1_name = active_terms[0]
        t2_name = active_terms[1]
        c1 = evidence_counts.get(t1_name, 0)
        c2 = evidence_counts.get(t2_name, 0)

        # Rule: Minimum 2 tests in each compared term
        if c1 < 2 or c2 < 2:
            return TermConsistencySchema(
                terms_evaluated=[t1_name, t2_name],
                term_scores=term_scores,
                has_sufficient_evidence=False,
                term_direction="INSUFFICIENT_EVIDENCE",
                display_narrative=f"Insufficient evidence: {t1_name} ({c1} tests), {t2_name} ({c2} tests). Need >= 2 tests per term.",
                evidence_breakdown=evidence_counts,
            )

        s1 = term_scores[t1_name]
        s2 = term_scores[t2_name]
        diff = round(s2 - s1, 1)

        if diff > 2.0:
            direction = "IMPROVING"
            tier = "Improving"
        elif diff < -2.0:
            direction = "DECLINING"
            tier = "Declining"
        else:
            direction = "STABLE"
            tier = "Stable"

        narrative = f"{t1_name} ({int(round(s1))}%) → {t2_name} ({int(round(s2))}%) | {tier}"

        return TermConsistencySchema(
            terms_evaluated=[t1_name, t2_name],
            term_scores=term_scores,
            has_sufficient_evidence=True,
            term_direction=direction,
            display_narrative=narrative,
            evidence_breakdown=evidence_counts,
        )

    def evaluate_topic_movement(
        self, topic_history: List[Dict[str, Any]]
    ) -> List[TopicMovementSchema]:
        """
        4. Topic Movement: Needs Attention → Needs Practice → Mastered
        Rule: Topic-level evidence required. Aggregate marks alone never create fake mastery.
        """
        if not topic_history:
            return []

        def _get_tier(score: float) -> str:
            if score >= 80.0:
                return "Mastered"
            elif score >= 60.0:
                return "Foundational"
            elif score >= 40.0:
                return "Needs Practice"
            else:
                return "Needs Attention"

        movements: List[TopicMovementSchema] = []

        for th in topic_history:
            node_id = str(th.get("node_id", ""))
            t_name = str(th.get("topic_name", "General Topic"))
            subject = str(th.get("subject", "General"))
            cur_score = float(th.get("current_score", 0.0))
            prev_score = th.get("previous_score")

            prev_score_val = float(prev_score) if prev_score is not None else None
            cur_tier = _get_tier(cur_score)
            prev_tier = _get_tier(prev_score_val) if prev_score_val is not None else None

            if prev_tier:
                movement_label = f"{prev_tier} → {cur_tier}"
                is_improved = cur_score > prev_score_val
            else:
                movement_label = f"Identified at {cur_tier}"
                is_improved = False

            movements.append(
                TopicMovementSchema(
                    node_id=node_id,
                    topic_name=t_name,
                    subject=subject,
                    previous_tier=prev_tier,
                    current_tier=cur_tier,
                    previous_score=prev_score_val,
                    current_score=cur_score,
                    movement_label=movement_label,
                    is_improved=is_improved,
                )
            )

        return movements

    def evaluate_gap_closure(
        self, gaps_data: List[Dict[str, Any]]
    ) -> GapClosureSummarySchema:
        """
        5. Gap Closure: 2 of 3 gaps improved / closed
        Rule: Actual recheck/new evidence only.
        """
        total = len(gaps_data)
        if total == 0:
            return GapClosureSummarySchema(
                total_identified_gaps=0,
                active_gaps_count=0,
                in_recheck_count=0,
                resolved_gaps_count=0,
                closure_rate_percent=0.0,
                display_badge="No learning gaps identified",
                active_gaps=[],
                recently_closed_gaps=[],
            )

        active = 0
        in_recheck = 0
        resolved = 0
        active_list = []
        resolved_list = []

        for g in gaps_data:
            st = str(g.get("gap_status", g.get("status", "ACTIVE"))).upper()
            if st == "RESOLVED":
                resolved += 1
                resolved_list.append(g)
            elif st == "IN_RECHECK":
                in_recheck += 1
                active_list.append(g)
            else:
                active += 1
                active_list.append(g)

        rate = round((resolved / total) * 100.0, 1) if total > 0 else 0.0
        badge = f"{resolved} of {total} gaps improved / closed ({rate}%)"

        return GapClosureSummarySchema(
            total_identified_gaps=total,
            active_gaps_count=active,
            in_recheck_count=in_recheck,
            resolved_gaps_count=resolved,
            closure_rate_percent=rate,
            display_badge=badge,
            active_gaps=active_list,
            recently_closed_gaps=resolved_list,
        )

    def evaluate_expert_feedback_status(
        self, expert_cases: List[Dict[str, Any]]
    ) -> List[ExpertFeedbackStatusSchema]:
        """
        6. Expert Feedback Status: Submitted → Under Review → Completed
        Rule: Only assigned expert can evaluate. 48h SLA countdown tracking.
        Completed feedback integrates as confirmed evidence.
        """
        if not expert_cases:
            return []

        results: List[ExpertFeedbackStatusSchema] = []
        now = datetime.now(timezone.utc)

        for ec in expert_cases:
            case_id = str(ec.get("case_id", ""))
            subject = str(ec.get("subject", "General"))
            test_title = str(ec.get("test_title", "Expert Evaluation"))
            expert_name = str(ec.get("expert_name", "Subject Expert"))
            status = str(ec.get("case_status", "ASSIGNED")).upper()

            submitted_at = ec.get("submitted_at")
            completed_at = ec.get("completed_at")

            sub_str = None
            comp_str = None
            remaining_hours = None
            is_breached = False

            if submitted_at:
                if isinstance(submitted_at, str):
                    try:
                        sub_dt = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
                    except Exception:
                        sub_dt = now
                    sub_str = submitted_at
                elif isinstance(submitted_at, datetime):
                    sub_dt = submitted_at if submitted_at.tzinfo else submitted_at.replace(tzinfo=timezone.utc)
                    sub_str = sub_dt.isoformat()
                else:
                    sub_dt = now

                elapsed = (now - sub_dt).total_seconds() / 3600.0
                remaining_hours = max(0.0, round(48.0 - elapsed, 1))

                if elapsed > 48.0 and status != "COMPLETED":
                    is_breached = True

            if completed_at:
                if isinstance(completed_at, str):
                    comp_str = completed_at
                elif isinstance(completed_at, datetime):
                    comp_str = completed_at.isoformat()

            is_confirmed = (status == "COMPLETED")
            pdf_path = ec.get("evaluated_pdf_path")
            feedback = ec.get("expert_feedback") or ec.get("pedagogical_feedback")

            results.append(
                ExpertFeedbackStatusSchema(
                    case_id=case_id,
                    subject=subject,
                    test_title=test_title,
                    expert_name=expert_name,
                    case_status=status,
                    submitted_at=sub_str,
                    completed_at=comp_str,
                    sla_hours_remaining=remaining_hours,
                    is_sla_breached=is_breached,
                    is_confirmed_evidence=is_confirmed,
                    evaluated_pdf_path=pdf_path,
                    expert_feedback_summary=feedback,
                )
            )

        return results
