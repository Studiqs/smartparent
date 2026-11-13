"""
STUDIQS® SmartParent™ (v6.2 Complete) - Board Readiness & Future Stream Readiness Engine
=============================================================================
Engine: board_readiness_engine.py (Section 8)
Mathematical, deterministic evaluation for Secondary & Senior Secondary (Classes 10 & 12).
Computes:
1. Syllabus Coverage & Mastery Completion Gauge
2. High-Weightage Topic Risk Radar (Topics with >=10% exam weightage in WEAK/CRITICAL tiers)
3. Deterministic Projected Board Score Corridor (Lower, Most Likely, Upper) with gap & stability adjustments
4. Board Readiness Status Tier (READY, ON_TRACK, NEEDS_ATTENTION, CRITICAL_RISK)
5. Stream & Career Future Readiness Bridge (Science Engineering, Life Science, Commerce, Humanities)
6. High-Priority Remedial Focus Checklist before Board Examination
=============================================================================
"""

import math
from typing import Any, Dict, List, Optional, Tuple


class BoardReadinessEngine:
    """
    Section 8 Deterministic Board Readiness & Stream Future Readiness Engine.
    Strictly deterministic, syllabus-grounded, zero cloud dependencies.
    """

    # Exam weightage coefficients for projecting final board performance
    EXAM_TYPE_WEIGHTS = {
        "PRE_BOARD": 1.4,
        "MODEL_EXAM": 1.3,
        "ANNUAL_EXAM": 1.3,
        "HALF_YEARLY": 1.1,
        "MID_TERM": 1.0,
        "QUARTERLY": 0.9,
        "UNIT_TEST": 0.7,
        "CLASS_TEST": 0.5,
        "QUICK_MARKS": 0.8,
        "REPEAT_EXAM": 1.0,
        "OTHER": 0.7,
    }

    # Core academic streams for secondary stream selection
    STREAM_SUBJECT_MAP = {
        "ENGINEERING": ["MATHEMATICS", "PHYSICS", "CHEMISTRY"],
        "LIFE_SCIENCE": ["BIOLOGY", "PHYSICS", "CHEMISTRY"],
        "COMMERCE": ["COMMERCE", "ACCOUNTANCY", "ECONOMICS", "MATHEMATICS"],
        "HUMANITIES": ["HISTORY", "GEOGRAPHY", "POLITICAL_SCIENCE", "ECONOMICS", "ENGLISH"],
    }

    def evaluate_board_readiness(
        self,
        standard_class: str,
        board: str,
        evidence_records: List[Dict[str, Any]],
        topic_scores: List[Dict[str, Any]],
        topic_gaps: List[Dict[str, Any]],
        curriculum_topics: List[Dict[str, Any]],
        consistency_slope: float = 0.0,
        stability_index: float = 0.8,
    ) -> Dict[str, Any]:
        """
        Executes complete Board Readiness analysis for student.

        :param standard_class: e.g. "Class 10", "Class 12"
        :param board: e.g. "CBSE", "STATE_BOARD"
        :param evidence_records: List of test results with subject, scored_marks, max_marks, exam_type
        :param topic_scores: List of topic mastery records with topic_id, topic_name, subject, score_percentage, mastery_tier
        :param topic_gaps: List of active/resolved topic gaps with topic_name, subject, severity, is_critical
        :param curriculum_topics: Total syllabus topics for this class & board
        :param consistency_slope: Slope from performance_consistency_engine (-1.0 to +1.0)
        :param stability_index: Volatility stability index (0.0 to 1.0)
        :return: Comprehensive Board Readiness dictionary
        """
        # 1. Subject-level Weighted Scores
        subject_stats = self._compute_subject_stats(evidence_records)

        # 2. Syllabus Coverage & Mastery Completion Gauge
        coverage_metrics = self._compute_syllabus_coverage(
            curriculum_topics=curriculum_topics,
            topic_scores=topic_scores,
        )

        # 3. High-Weightage Topic Risk Radar
        risk_radar = self._compute_high_weightage_risk_radar(
            curriculum_topics=curriculum_topics,
            topic_scores=topic_scores,
            topic_gaps=topic_gaps,
        )

        # 4. Projected Board Score Corridor
        score_corridor = self._compute_projected_score_corridor(
            subject_stats=subject_stats,
            consistency_slope=consistency_slope,
            stability_index=stability_index,
            critical_gap_count=risk_radar["critical_risk_count"],
            coverage_percentage=coverage_metrics["coverage_percentage"],
        )

        # 5. Readiness Status Tier
        readiness_status, status_rationale = self._determine_readiness_status(
            score_corridor=score_corridor,
            high_weightage_risks=risk_radar["high_weightage_risk_count"],
            coverage_percentage=coverage_metrics["coverage_percentage"],
            active_gaps_count=len([g for g in topic_gaps if g.get("gap_status", "ACTIVE") == "ACTIVE"]),
        )

        # 6. Stream & Future Readiness Bridge (Class 10 & 11)
        stream_alignment = self._evaluate_stream_alignment(
            subject_stats=subject_stats,
            standard_class=standard_class,
        )

        # 7. High Priority Board Action Items
        action_checklist = self._generate_board_action_checklist(
            readiness_status=readiness_status,
            risk_radar=risk_radar,
            subject_stats=subject_stats,
            coverage_metrics=coverage_metrics,
        )

        return {
            "standard_class": standard_class,
            "board": board,
            "readiness_status": readiness_status,
            "status_rationale": status_rationale,
            "score_corridor": score_corridor,
            "syllabus_coverage": coverage_metrics,
            "risk_radar": risk_radar,
            "subject_breakdown": subject_stats,
            "stream_alignment": stream_alignment,
            "priority_action_checklist": action_checklist,
            "is_board_appearing_grade": standard_class.upper() in ["CLASS 10", "CLASS 12", "10", "12"],
        }

    def _compute_subject_stats(
        self,
        evidence_records: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Aggregates weighted percentage averages per subject from verified test evidence.
        """
        if not evidence_records:
            return {}

        subject_accumulator: Dict[str, Dict[str, float]] = {}

        for rec in evidence_records:
            subj = str(rec.get("subject", "GENERAL")).upper()
            scored = float(rec.get("scored_marks", 0.0))
            max_m = float(rec.get("max_marks", 100.0))
            if max_m <= 0:
                continue

            pct = (scored / max_m) * 100.0
            exam_type = str(rec.get("exam_type", "OTHER")).upper()
            weight = self.EXAM_TYPE_WEIGHTS.get(exam_type, 0.8)

            if subj not in subject_accumulator:
                subject_accumulator[subj] = {
                    "weighted_sum": 0.0,
                    "weight_sum": 0.0,
                    "test_count": 0,
                    "latest_pct": pct,
                }

            subject_accumulator[subj]["weighted_sum"] += pct * weight
            subject_accumulator[subj]["weight_sum"] += weight
            subject_accumulator[subj]["test_count"] += 1
            subject_accumulator[subj]["latest_pct"] = pct

        results = {}
        for subj, acc in subject_accumulator.items():
            avg = acc["weighted_sum"] / acc["weight_sum"] if acc["weight_sum"] > 0 else 0.0
            avg_rounded = round(avg, 1)

            if avg_rounded >= 80.0:
                health = "STRONG"
            elif avg_rounded >= 60.0:
                health = "AVERAGE"
            elif avg_rounded >= 40.0:
                health = "VULNERABLE"
            else:
                health = "CRITICAL"

            results[subj] = {
                "subject": subj,
                "average_percentage": avg_rounded,
                "latest_percentage": round(acc["latest_pct"], 1),
                "total_assessments": acc["test_count"],
                "health_tier": health,
            }

        return results

    def _compute_syllabus_coverage(
        self,
        curriculum_topics: List[Dict[str, Any]],
        topic_scores: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Calculates tested and mastered topic coverage against total curriculum nodes.
        """
        total_topics_count = len(curriculum_topics) if curriculum_topics else 100
        tested_topic_ids = set()
        mastered_topic_ids = set()

        for ts in topic_scores:
            tid = ts.get("topic_id") or ts.get("topic_name")
            if tid:
                tested_topic_ids.add(str(tid))
                score_pct = float(ts.get("score_percentage", 0.0))
                tier = str(ts.get("mastery_tier", "")).upper()
                if score_pct >= 80.0 or tier == "MASTERED":
                    mastered_topic_ids.add(str(tid))

        tested_count = len(tested_topic_ids)
        mastered_count = len(mastered_topic_ids)

        # Baseline coverage ratio
        effective_total = max(total_topics_count, tested_count)
        coverage_pct = round((tested_count / effective_total) * 100.0, 1) if effective_total > 0 else 0.0
        mastery_pct = round((mastered_count / effective_total) * 100.0, 1) if effective_total > 0 else 0.0

        return {
            "total_curriculum_topics": effective_total,
            "tested_topics_count": tested_count,
            "mastered_topics_count": mastered_count,
            "coverage_percentage": min(100.0, coverage_pct),
            "mastery_percentage": min(100.0, mastery_pct),
            "untested_topics_count": max(0, effective_total - tested_count),
        }

    def _compute_high_weightage_risk_radar(
        self,
        curriculum_topics: List[Dict[str, Any]],
        topic_scores: List[Dict[str, Any]],
        topic_gaps: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Scans for high-weightage topics (>=10% exam marks or core concepts) where student is WEAK or has Gaps.
        """
        risk_topics = []
        active_gap_topics = {
            str(g.get("topic_name", "")).upper(): g
            for g in topic_gaps
            if g.get("gap_status", "ACTIVE") == "ACTIVE"
        }

        # Index topic scores by upper topic name
        score_by_topic: Dict[str, Dict[str, Any]] = {
            str(ts.get("topic_name", "")).upper(): ts for ts in topic_scores
        }

        # Check curriculum topics for high weightage (>= 10% or weightage >= 8.0)
        for cur in curriculum_topics:
            tname = str(cur.get("topic_name", "")).upper()
            weightage = float(cur.get("weightage_marks", cur.get("weightage", 10.0)))
            is_high_weightage = weightage >= 8.0 or cur.get("is_high_weightage", False)

            if not is_high_weightage:
                continue

            ts = score_by_topic.get(tname)
            has_gap = tname in active_gap_topics
            score_pct = float(ts.get("score_percentage", 0.0)) if ts else 0.0
            tier = str(ts.get("mastery_tier", "UNTESTED")).upper() if ts else "UNTESTED"

            # Risk trigger: Untested high-weightage topic, or score < 60%, or active gap
            is_risk = has_gap or (ts is not None and score_pct < 60.0) or (ts is None and weightage >= 12.0)

            if is_risk:
                severity = "CRITICAL" if (score_pct < 40.0 or has_gap) else "EMERGING"
                risk_topics.append({
                    "topic_name": cur.get("topic_name", tname),
                    "subject": str(cur.get("subject", "GENERAL")).upper(),
                    "chapter": cur.get("chapter_name", cur.get("chapter", "Core Syllabus")),
                    "weightage_marks": weightage,
                    "student_score_pct": round(score_pct, 1),
                    "mastery_tier": tier,
                    "has_active_gap": has_gap,
                    "risk_severity": severity,
                    "remediation_action": f"Prioritize 10-min revision on {cur.get('topic_name', tname)} before next term test.",
                })

        # Sort risks: CRITICAL first, then by highest weightage marks
        risk_topics.sort(
            key=lambda x: (0 if x["risk_severity"] == "CRITICAL" else 1, -x["weightage_marks"])
        )

        critical_count = sum(1 for r in risk_topics if r["risk_severity"] == "CRITICAL")

        # Overall risk index (0 to 100, where 0 is safest, 100 is highest risk)
        base_risk = (critical_count * 15.0) + ((len(risk_topics) - critical_count) * 8.0)
        risk_index = min(100.0, max(0.0, round(base_risk, 1)))

        return {
            "high_weightage_risk_count": len(risk_topics),
            "critical_risk_count": critical_count,
            "risk_index": risk_index,
            "risk_level": "HIGH" if risk_index >= 50 else ("MODERATE" if risk_index >= 25 else "LOW"),
            "risk_topics": risk_topics[:10],  # Top 10 high-weightage risks
        }

    def _compute_projected_score_corridor(
        self,
        subject_stats: Dict[str, Dict[str, Any]],
        consistency_slope: float,
        stability_index: float,
        critical_gap_count: int,
        coverage_percentage: float,
    ) -> Dict[str, Any]:
        """
        Computes a 3-point deterministic score projection corridor:
        - Lower Bound
        - Most Likely
        - Upper Bound
        """
        if not subject_stats:
            # Cold-start baseline defaults
            return {
                "lower_bound_pct": 50.0,
                "most_likely_pct": 65.0,
                "upper_bound_pct": 78.0,
                "projection_confidence": "LOW (Awaiting Test Results)",
                "confidence_score": 0.35,
            }

        # 1. Base average of subjects
        subject_avgs = [s["average_percentage"] for s in subject_stats.values()]
        base_avg = sum(subject_avgs) / len(subject_avgs)

        # 2. Consistency trajectory adjustment (-5% to +4%)
        # Positive slope means accelerating improvement; negative slope means tapering
        slope_adjustment = max(-5.0, min(4.0, consistency_slope * 6.0))

        # 3. Critical Gap Penalty (-1.2% per unresolved high-weightage gap, max -10%)
        gap_penalty = min(10.0, critical_gap_count * 1.2)

        # 4. Coverage adjustment (Low coverage means higher uncertainty and lower base)
        coverage_factor = (coverage_percentage / 100.0)
        coverage_adjustment = (coverage_factor - 0.7) * 4.0  # -2.8% to +1.2%

        # Calculate Most Likely score
        most_likely = base_avg + slope_adjustment - gap_penalty + coverage_adjustment
        most_likely = max(30.0, min(99.0, most_likely))

        # 5. Corridor Spread determined by stability_index
        # High stability (1.0) -> narrow corridor (+-3%)
        # Low stability (0.3) -> wide corridor (+-8%)
        stability_safe = max(0.2, min(1.0, stability_index))
        corridor_half_width = round(9.0 - (stability_safe * 5.5), 1)

        lower_bound = max(25.0, round(most_likely - corridor_half_width, 1))
        upper_bound = min(100.0, round(most_likely + corridor_half_width, 1))
        most_likely_rounded = round(most_likely, 1)

        # Confidence level
        total_tests = sum(s["total_assessments"] for s in subject_stats.values())
        if total_tests >= 6 and stability_safe >= 0.7:
            conf_tier = "HIGH"
            conf_score = 0.88
        elif total_tests >= 3:
            conf_tier = "MODERATE"
            conf_score = 0.65
        else:
            conf_tier = "PRELIMINARY"
            conf_score = 0.45

        return {
            "lower_bound_pct": lower_bound,
            "most_likely_pct": most_likely_rounded,
            "upper_bound_pct": upper_bound,
            "corridor_spread_pct": round(upper_bound - lower_bound, 1),
            "projection_confidence": conf_tier,
            "confidence_score": conf_score,
        }

    def _determine_readiness_status(
        self,
        score_corridor: Dict[str, Any],
        high_weightage_risks: int,
        coverage_percentage: float,
        active_gaps_count: int,
    ) -> Tuple[str, str]:
        """
        Categorizes student into the 4 official Board Readiness Tiers:
        - READY
        - ON_TRACK
        - NEEDS_ATTENTION
        - CRITICAL_RISK
        """
        most_likely = score_corridor["most_likely_pct"]

        if most_likely >= 85.0 and high_weightage_risks <= 1 and coverage_percentage >= 70.0:
            return (
                "READY",
                f"Projected board score is {most_likely}% with excellent syllabus coverage ({coverage_percentage}%) and minimal high-weightage risks."
            )
        elif most_likely >= 70.0 and high_weightage_risks <= 3 and coverage_percentage >= 50.0:
            return (
                "ON_TRACK",
                f"Solid academic trajectory ({most_likely}% most likely). Focusing on closing the {high_weightage_risks} high-weightage risks will push performance into Centum range."
            )
        elif most_likely >= 55.0 or high_weightage_risks > 3:
            return (
                "NEEDS_ATTENTION",
                f"Current score trajectory is {most_likely}%. Requires focused intervention on {high_weightage_risks} high-weightage chapter gaps before board pre-finals."
            )
        else:
            return (
                "CRITICAL_RISK",
                f"Urgent pedagogical remediation needed. Score projection is {most_likely}% with {active_gaps_count} open gaps across core examination subjects."
            )

    def _evaluate_stream_alignment(
        self,
        subject_stats: Dict[str, Dict[str, Any]],
        standard_class: str,
    ) -> Dict[str, Any]:
        """
        Computes stream aptitude alignment (Engineering, Life Science, Commerce, Humanities).
        Especially relevant for Class 10 students transitioning to Class 11.
        """
        if not subject_stats:
            return {
                "recommended_stream": "Awaiting Assessment Marks",
                "alignment_scores": {},
                "rationale": "Add student test marks across Maths, Science, and Social to generate stream readiness.",
            }

        STREAM_PRIMARY_ANCHORS = {
            "ENGINEERING": ["MATHEMATICS", "PHYSICS"],
            "LIFE_SCIENCE": ["BIOLOGY"],
            "COMMERCE": ["COMMERCE", "ACCOUNTANCY", "ECONOMICS"],
            "HUMANITIES": ["HISTORY", "GEOGRAPHY", "POLITICAL_SCIENCE"],
        }

        stream_scores = {}
        for stream, required_subjects in self.STREAM_SUBJECT_MAP.items():
            matched_scores = []
            has_primary_anchor = False
            primary_anchors = STREAM_PRIMARY_ANCHORS.get(stream, [])

            for subj in required_subjects:
                for stored_subj, stat in subject_stats.items():
                    if subj in stored_subj or stored_subj in subj:
                        matched_scores.append(stat["average_percentage"])
                        if any(a in stored_subj or stored_subj in a for a in primary_anchors):
                            has_primary_anchor = True
                        break

            if matched_scores:
                raw_avg = sum(matched_scores) / len(matched_scores)
                # If student lacks the primary anchor subject for this stream (e.g. Maths alone without Commerce/Accountancy),
                # apply a discount to reflect missing domain specialization
                if primary_anchors and not has_primary_anchor:
                    raw_avg *= 0.75

                # Weight by proportion of stream subjects available
                coverage_weight = min(1.0, 0.7 + (0.3 * len(matched_scores) / len(required_subjects)))
                final_score = round(raw_avg * coverage_weight, 1)
                stream_scores[stream] = final_score
            else:
                stream_scores[stream] = 45.0  # default baseline

        # Find best matching stream
        best_stream = max(stream_scores.items(), key=lambda x: x[1])

        stream_display_names = {
            "ENGINEERING": "Science (Maths & Computer Science / Engineering Focus)",
            "LIFE_SCIENCE": "Science (Biology / Medical & Life Sciences Focus)",
            "COMMERCE": "Commerce & Business Studies (Finance / CA / Economics Focus)",
            "HUMANITIES": "Humanities & Social Sciences (Civil Services / Law / Media Focus)",
        }

        return {
            "recommended_stream": best_stream[0],
            "recommended_stream_display": stream_display_names.get(best_stream[0], best_stream[0]),
            "best_stream_score": best_stream[1],
            "alignment_scores": stream_scores,
            "rationale": f"Student exhibits highest average competency ({best_stream[1]}%) in prerequisite subjects for {stream_display_names.get(best_stream[0], best_stream[0])}.",
        }

    def _generate_board_action_checklist(
        self,
        readiness_status: str,
        risk_radar: Dict[str, Any],
        subject_stats: Dict[str, Dict[str, Any]],
        coverage_metrics: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        """
        Produces top 3 actionable board preparation priorities for parents.
        """
        actions = []

        # 1. High weightage risks
        risk_topics = risk_radar.get("risk_topics", [])
        if risk_topics:
            top_risk = risk_topics[0]
            actions.append({
                "priority": "HIGH",
                "title": f"Remediate {top_risk['topic_name']} ({top_risk['subject']})",
                "action": f"This topic carries {top_risk['weightage_marks']} marks in board exams. Complete a 10-minute diagnostic recheck to eliminate the gap.",
                "target_subject": top_risk["subject"],
            })

        # 2. Lowest performing subject
        if subject_stats:
            lowest_subj = min(subject_stats.values(), key=lambda x: x["average_percentage"])
            if lowest_subj["average_percentage"] < 75.0:
                actions.append({
                    "priority": "HIGH" if lowest_subj["average_percentage"] < 60.0 else "MEDIUM",
                    "title": f"Strengthen {lowest_subj['subject']} Foundation",
                    "action": f"Current subject average is {lowest_subj['average_percentage']}%. Schedule 2 targeted practice worksheets this week.",
                    "target_subject": lowest_subj["subject"],
                })

        # 3. Syllabus completion
        untested = coverage_metrics.get("untested_topics_count", 0)
        if untested > 10:
            actions.append({
                "priority": "MEDIUM",
                "title": "Increase Syllabus Evaluation Coverage",
                "action": f"{untested} topics remain untested in the official curriculum. Upload recent school tests to unlock complete board risk visibility.",
                "target_subject": "ALL",
            })
        else:
            actions.append({
                "priority": "LOW",
                "title": "Maintain Revision Consistency",
                "action": "Consistent weekly assessments reinforce long-term memory retention for board exams.",
                "target_subject": "ALL",
            })

        return actions[:3]
