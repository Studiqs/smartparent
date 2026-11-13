"""
STUDIQS® SmartParent™ (v6.2 Complete) - Student Milestones & Achievement Badges Engine
=============================================================================
Engine: achievement_engine.py (Section 8)
Evaluates real academic milestones and awards verified badges to celebrate student learning.
Strictly evidence-backed:
1. Centum Club (Scored 100% on any verified exam)
2. Consistency Champion (Positive consistency trajectory over 3+ exams)
3. Gap Slayer (Resolved 3+ persistent topic gaps via diagnostic rechecks)
4. Syllabus Pioneer (Reached >= 70% syllabus coverage in curriculum)
5. Board Ready (Attained READY or ON_TRACK tier in Board Exam Index)
6. Persistent Scholar (Logged 5+ verified test assessments)
7. Subject Maestro (Achieved >= 90% average in a core academic subject)
=============================================================================
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class AchievementEngine:
    """
    Section 8 Deterministic Student Achievement & Milestone Badge Engine.
    Awards pedagogical badges grounded purely in student test evidence.
    """

    BADGE_DEFINITIONS = [
        {
            "badge_code": "CENTUM_CLUB",
            "title": "Centum Club Champion",
            "category": "EXCELLENCE",
            "description": "Scored a perfect 100% on a verified school test or examination.",
            "icon": "trophy-centum",
            "target_threshold": 1,
        },
        {
            "badge_code": "CONSISTENCY_CHAMPION",
            "title": "Consistency Champion",
            "category": "PROGRESSION",
            "description": "Maintained an upward performance trajectory with positive consistency slope.",
            "icon": "trending-up-star",
            "target_threshold": 1,
        },
        {
            "badge_code": "GAP_SLAYER",
            "title": "Topic Gap Slayer",
            "category": "REMEDIATION",
            "description": "Successfully conquered and resolved 3 or more persistent topic gaps through diagnostic rechecks.",
            "icon": "target-conquered",
            "target_threshold": 3,
        },
        {
            "badge_code": "SYLLABUS_PIONEER",
            "title": "Syllabus Pioneer",
            "category": "COVERAGE",
            "description": "Achieved 70% or higher topic coverage across the official curriculum.",
            "icon": "compass-milestone",
            "target_threshold": 70,
        },
        {
            "badge_code": "BOARD_READY",
            "title": "Board Exam Ready",
            "category": "READINESS",
            "description": "Attained 'READY' or 'ON_TRACK' status on the Board Exam Readiness Radar.",
            "icon": "shield-check-star",
            "target_threshold": 1,
        },
        {
            "badge_code": "PERSISTENT_SCHOLAR",
            "title": "Persistent Scholar",
            "category": "DEDICATION",
            "description": "Logged 5 or more verified assessments in the current academic year.",
            "icon": "book-open-ribbon",
            "target_threshold": 5,
        },
        {
            "badge_code": "SUBJECT_MAESTRO",
            "title": "Subject Maestro",
            "category": "MASTERY",
            "description": "Achieved a 90% or higher average across tests in a core academic subject.",
            "icon": "award-laurel",
            "target_threshold": 90,
        },
    ]

    def evaluate_achievements(
        self,
        evidence_records: List[Dict[str, Any]],
        topic_gaps: List[Dict[str, Any]],
        coverage_metrics: Dict[str, Any],
        board_readiness_status: str,
        consistency_slope: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Evaluates student evidence and calculates all unlocked and in-progress achievement badges.
        """
        unlocked_badges = []
        in_progress_badges = []

        total_assessments = len(evidence_records)
        resolved_gaps = [
            g for g in topic_gaps
            if str(g.get("gap_status", "")).upper() == "RESOLVED"
        ]
        resolved_gaps_count = len(resolved_gaps)
        coverage_pct = float(coverage_metrics.get("coverage_percentage", 0.0))

        # Check Centum Club (100% score)
        has_centum = False
        centum_evidence_title = ""
        for rec in evidence_records:
            scored = float(rec.get("scored_marks", 0.0))
            max_m = float(rec.get("max_marks", 100.0))
            if max_m > 0 and scored >= max_m:
                has_centum = True
                centum_evidence_title = rec.get("test_title", "School Assessment")
                break

        # Check Subject Maestro (>=90% in any subject with at least 2 tests)
        subject_scores: Dict[str, List[float]] = {}
        for rec in evidence_records:
            subj = str(rec.get("subject", "GENERAL")).upper()
            scored = float(rec.get("scored_marks", 0.0))
            max_m = float(rec.get("max_marks", 100.0))
            if max_m > 0:
                pct = (scored / max_m) * 100.0
                subject_scores.setdefault(subj, []).append(pct)

        has_maestro = False
        maestro_subject = ""
        for subj, pcts in subject_scores.items():
            if len(pcts) >= 2 and (sum(pcts) / len(pcts)) >= 90.0:
                has_maestro = True
                maestro_subject = subj
                break

        # Check Board Ready
        is_board_ready = board_readiness_status in ["READY", "ON_TRACK"]

        # Check Consistency Champion
        is_consistency_champion = consistency_slope >= 0.05 and total_assessments >= 3

        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Centum Club
        if has_centum:
            unlocked_badges.append(self._build_unlocked(
                "CENTUM_CLUB",
                evidence_highlight=f"Achieved 100% on '{centum_evidence_title}'",
                unlocked_at=now_iso,
            ))
        else:
            in_progress_badges.append(self._build_in_progress(
                "CENTUM_CLUB",
                current_progress=0,
                target_threshold=1,
                progress_label="Score 100% on any upcoming test",
            ))

        # 2. Consistency Champion
        if is_consistency_champion:
            unlocked_badges.append(self._build_unlocked(
                "CONSISTENCY_CHAMPION",
                evidence_highlight=f"Steadily improving trajectory (slope +{round(consistency_slope, 2)})",
                unlocked_at=now_iso,
            ))
        else:
            slope_disp = round(consistency_slope, 2)
            in_progress_badges.append(self._build_in_progress(
                "CONSISTENCY_CHAMPION",
                current_progress=1 if total_assessments >= 2 else 0,
                target_threshold=1,
                progress_label=f"Current slope {slope_disp}. Maintain upward scores across 3 tests",
            ))

        # 3. Gap Slayer
        if resolved_gaps_count >= 3:
            unlocked_badges.append(self._build_unlocked(
                "GAP_SLAYER",
                evidence_highlight=f"Conquered {resolved_gaps_count} persistent topic gaps",
                unlocked_at=now_iso,
            ))
        else:
            in_progress_badges.append(self._build_in_progress(
                "GAP_SLAYER",
                current_progress=resolved_gaps_count,
                target_threshold=3,
                progress_label=f"{resolved_gaps_count}/3 gaps resolved via diagnostic rechecks",
            ))

        # 4. Syllabus Pioneer
        if coverage_pct >= 70.0:
            unlocked_badges.append(self._build_unlocked(
                "SYLLABUS_PIONEER",
                evidence_highlight=f"Reached {coverage_pct}% syllabus evaluation coverage",
                unlocked_at=now_iso,
            ))
        else:
            in_progress_badges.append(self._build_in_progress(
                "SYLLABUS_PIONEER",
                current_progress=int(coverage_pct),
                target_threshold=70,
                progress_label=f"{coverage_pct}% / 70% curriculum topics tested",
            ))

        # 5. Board Ready
        if is_board_ready:
            unlocked_badges.append(self._build_unlocked(
                "BOARD_READY",
                evidence_highlight=f"Achieved '{board_readiness_status}' status on Board Radar",
                unlocked_at=now_iso,
            ))
        else:
            in_progress_badges.append(self._build_in_progress(
                "BOARD_READY",
                current_progress=0,
                target_threshold=1,
                progress_label="Reach 'READY' or 'ON_TRACK' tier on Board Readiness index",
            ))

        # 6. Persistent Scholar
        if total_assessments >= 5:
            unlocked_badges.append(self._build_unlocked(
                "PERSISTENT_SCHOLAR",
                evidence_highlight=f"Logged {total_assessments} verified assessments",
                unlocked_at=now_iso,
            ))
        else:
            in_progress_badges.append(self._build_in_progress(
                "PERSISTENT_SCHOLAR",
                current_progress=total_assessments,
                target_threshold=5,
                progress_label=f"{total_assessments}/5 assessments logged this year",
            ))

        # 7. Subject Maestro
        if has_maestro:
            unlocked_badges.append(self._build_unlocked(
                "SUBJECT_MAESTRO",
                evidence_highlight=f"Achieved 90%+ average in {maestro_subject}",
                unlocked_at=now_iso,
            ))
        else:
            in_progress_badges.append(self._build_in_progress(
                "SUBJECT_MAESTRO",
                current_progress=0,
                target_threshold=90,
                progress_label="Maintain >=90% test average in any core subject",
            ))

        return {
            "total_badges_count": len(self.BADGE_DEFINITIONS),
            "unlocked_count": len(unlocked_badges),
            "in_progress_count": len(in_progress_badges),
            "completion_percentage": round((len(unlocked_badges) / len(self.BADGE_DEFINITIONS)) * 100.0, 1),
            "unlocked_badges": unlocked_badges,
            "in_progress_badges": in_progress_badges,
        }

    def _get_badge_meta(self, code: str) -> Dict[str, Any]:
        for b in self.BADGE_DEFINITIONS:
            if b["badge_code"] == code:
                return b
        return {
            "badge_code": code,
            "title": code.replace("_", " ").title(),
            "category": "GENERAL",
            "description": "",
            "icon": "star",
            "target_threshold": 1,
        }

    def _build_unlocked(self, code: str, evidence_highlight: str, unlocked_at: str) -> Dict[str, Any]:
        meta = self._get_badge_meta(code)
        return {
            "badge_code": code,
            "title": meta["title"],
            "category": meta["category"],
            "description": meta["description"],
            "icon": meta["icon"],
            "is_unlocked": True,
            "unlocked_at": unlocked_at,
            "evidence_highlight": evidence_highlight,
            "progress_percentage": 100.0,
        }

    def _build_in_progress(
        self,
        code: str,
        current_progress: int,
        target_threshold: int,
        progress_label: str,
    ) -> Dict[str, Any]:
        meta = self._get_badge_meta(code)
        pct = min(100.0, max(0.0, round((current_progress / target_threshold) * 100.0, 1))) if target_threshold > 0 else 0.0
        return {
            "badge_code": code,
            "title": meta["title"],
            "category": meta["category"],
            "description": meta["description"],
            "icon": meta["icon"],
            "is_unlocked": False,
            "current_progress": current_progress,
            "target_threshold": target_threshold,
            "progress_percentage": pct,
            "progress_label": progress_label,
        }


def calculate_achievement(data: dict) -> dict:
    """Legacy backward-compatibility helper for raw activity calculations."""
    certificates = data.get("certificates", 0)
    sports = data.get("sports", 0)
    competitions = data.get("competitions", 0)
    cultural = data.get("cultural", 0)
    total_students = data.get("total_students", 1) or 1

    achievement_activity = certificates + sports + competitions + cultural
    achievement_score = round(achievement_activity / total_students * 100)

    if achievement_score >= 75:
        engagement_level = "High"
        insight = "Student achievement participation is excellent. The school is highly active in extracurricular activities."
    elif achievement_score >= 40:
        engagement_level = "Moderate"
        insight = "Student achievement participation is moderate. More inter-school competitions can improve engagement."
    else:
        engagement_level = "Low"
        insight = "Student achievement participation is low. The school should introduce more extracurricular programs."

    return {
        "achievement_score": achievement_score,
        "engagement_level": engagement_level,
        "insight": insight,
    }
