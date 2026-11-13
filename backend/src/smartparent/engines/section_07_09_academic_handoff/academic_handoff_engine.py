"""
STUDIQS® SmartParent™ (v6.2 Complete) - Academic Handoff Brief Engine
=============================================================================
Engine: academic_handoff_engine.py (Section 7 & Section 9)
Synthesizes high-impact diagnostic briefs for Parent-Teacher Meetings (PTM),
school subject teachers, and home tutors.
Applies 'Praise First, Remediate Second' pedagogical standard.
Transforms vague complaints into precise diagnostic remedial directives.
Now with:
- Multi-Audience Customization: TEACHER, TUTOR, COMPREHENSIVE
- Subject-Specific Dynamic Filtering
- Real Misconception Patterns & Struggling Question Examples
- Exam Trajectory Trends
- 1-Click WhatsApp Share Text Generation
=============================================================================
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from src.smartparent.engines.base_engine import BaseEngine, EngineHealthStatus
from src.smartparent.schemas.actions import (
    AcademicHandoffBriefResponse,
    StrengthItemSchema,
    GapItemSchema,
)
from src.smartparent.schemas.handoff import (
    PtmAudienceEnum,
    PtmExamTrajectoryItemSchema,
    PtmSubjectTrendSchema,
    PtmStrugglingGapSchema,
    PtmPraisePointSchema,
    PtmPackResponse,
    WhatsAppShareResponse,
)

logger = logging.getLogger("STUDIQS_AcademicHandoffEngine")


def resolve_topic_misconception_and_question(subject: str, topic_name: str) -> Dict[str, str]:
    """
    Pedagogical rules engine returning concrete misconception patterns
    and representative struggling question stems for Indian K-12 curricula.
    """
    s_lower = subject.lower()
    t_lower = topic_name.lower()

    if "math" in s_lower or "arithmetic" in s_lower:
        if "quadratic" in t_lower:
            return {
                "misconception": "Struggles with algebraic sign conventions when applying quadratic discriminant (b² - 4ac) or factoring negatives.",
                "question": "Solve for x: 2x² - 5x + 3 = 0, clearly showing the factoring step.",
                "directive": "Isolate coefficients (a, b, c) before substituting into the discriminant formula; verify factoring with FOIL expansion."
            }
        elif "triangle" in t_lower or "geometry" in t_lower or "circle" in t_lower:
            return {
                "misconception": "Difficulty stating prerequisite geometric congruence / similarity theorems before calculating missing angles.",
                "question": "In right triangle ABC with ∠B = 90°, if AB = 6cm and BC = 8cm, prove similarity with altitude BD to hypotenuse AC.",
                "directive": "Always sketch and label the figure with given tick-marks before writing the geometric proof steps."
            }
        elif "trigonometr" in t_lower or "height" in t_lower:
            return {
                "misconception": "Conflating reference angle perspective when calculating sin θ vs cos θ in right triangles.",
                "question": "From a point 20m from the base of a tower, angle of elevation is 45°. Find the height of the tower.",
                "directive": "Label 'Opposite', 'Adjacent', and 'Hypotenuse' relative to the marked angle θ prior to writing ratios."
            }
        elif "linear" in t_lower or "equation" in t_lower:
            return {
                "misconception": "Errors during simultaneous elimination when coefficients have opposite signs.",
                "question": "Solve the pair of linear equations: 3x + 2y = 11 and 2x - 3y = 3.",
                "directive": "Multiply equations by appropriate multipliers so one variable cancels cleanly upon addition/subtraction."
            }
        else:
            return {
                "misconception": "Calculation slips during multi-step numerical simplification.",
                "question": f"Solve two multi-step textbook exercises in {topic_name} without checking the solution appendix.",
                "directive": "Double-check arithmetic at each intermediate line before declaring the final numerical answer."
            }

    elif "physic" in s_lower or "science" in s_lower and any(w in t_lower for w in ["electric", "light", "optics", "motion", "force"]):
        if "electric" in t_lower or "circuit" in t_lower or "current" in t_lower:
            return {
                "misconception": "Unit conversion oversights (e.g. mA to A) and algebraic formula inversion when applying Ohm's Law (V = IR).",
                "question": "Calculate electric current through a 4 Ω resistor when connected across a 12 V potential difference.",
                "directive": "Write given quantities with explicit SI units in the left margin before substituting into V = I × R."
            }
        elif "light" in t_lower or "optics" in t_lower or "lens" in t_lower or "mirror" in t_lower:
            return {
                "misconception": "Confusion regarding Cartesian sign convention (focal length f < 0 for concave vs f > 0 for convex).",
                "question": "An object 2cm high is placed 15cm in front of a concave mirror of focal length 10cm. Find position and size of image.",
                "directive": "Apply the New Cartesian Sign Convention table rigorously before writing the mirror formula: 1/f = 1/v + 1/u."
            }
        else:
            return {
                "misconception": "Difficulty translating word problems into appropriate physical laws and equations.",
                "question": f"State the primary physical law governing {topic_name} and solve one representative numerical problem.",
                "directive": "Identify given variables, state the governing formula, substitute with units, and compute final answer."
            }

    elif "chem" in s_lower or "science" in s_lower and any(w in t_lower for w in ["reaction", "acid", "base", "metal", "periodic", "carbon"]):
        return {
            "misconception": "Imbalance in polyatomic ion conservation and difficulty predicting precipitate products.",
            "question": "Balance the chemical equation: Fe + H₂O → Fe₃O₄ + H₂ and state reaction type.",
            "directive": "Draw an atom count table for reactants vs products before inserting balancing coefficients."
        }

    elif "bio" in s_lower or "science" in s_lower and any(w in t_lower for w in ["life", "cell", "reproduct", "heredity", "plant"]):
        return {
            "misconception": "Incomplete biological diagram labelling and omitting physiological function keywords in 3-mark answers.",
            "question": f"Draw a neat labeled schematic for {topic_name} and state the functions of any two parts.",
            "directive": "Practice neat anatomical diagrams with right-hand aligned label pointers; memorize function keywords."
        }

    elif "eng" in s_lower:
        return {
            "misconception": "Tense inconsistency and subject-verb concordance in complex compound sentences.",
            "question": f"Identify the grammatical error in 3 sentences involving {topic_name} and rewrite them correctly.",
            "directive": "Review subject-verb agreement rules and complete 5 sentence correction exercises daily."
        }

    elif "social" in s_lower or "hist" in s_lower or "geog" in s_lower or "civic" in s_lower:
        return {
            "misconception": "Writing narrative paragraphs without chronological milestone markers or map-pointing accuracy.",
            "question": f"Explain three significant socioeconomic causes/consequences of {topic_name}.",
            "directive": "Structure answers in 3 distinct numbered bullet points with historical dates or geographical map references."
        }

    return {
        "misconception": "Incomplete mastery of core foundational definitions and multi-step procedures.",
        "question": f"Answer 2 textbook review questions from {topic_name} from memory.",
        "directive": f"Dedicate 15 minutes of structured daily review on {topic_name} core definitions."
    }


class AcademicHandoffEngine(BaseEngine):
    """
    Engine: Academic Handoff Engine (academic_handoff_engine.py)
    
    Generates actionable, non-defensive diagnostic briefs for PTM / tutors:
    - Praise points (mastered topics >= 70%)
    - Pinpointed topic gaps (< 60%) with chapter context
    - Actionable 2-week focus directive
    - Exact talking points for parent to share with teacher or tutor
    - Formatted printable plain-text layout
    - WhatsApp 1-tap quick share text
    """

    def __init__(self, failure_threshold: int = 5):
        super().__init__(name="AcademicHandoffEngine", failure_threshold=failure_threshold)

    def validate_input(self, input_data: Any) -> Dict[str, Any]:
        """Validates academic handoff input data."""
        if not input_data:
            raise ValueError("Input data cannot be empty.")

        if hasattr(input_data, "model_dump"):
            data = input_data.model_dump()
        elif hasattr(input_data, "dict"):
            data = input_data.dict()
        elif isinstance(input_data, dict):
            data = dict(input_data)
        else:
            raise ValueError(f"Unsupported payload type for AcademicHandoffEngine: {type(input_data)}")

        return data

    def execute_core(self, validated_data: Dict[str, Any]) -> AcademicHandoffBriefResponse:
        """
        Legacy Section 7 interface. Synthesizes AcademicHandoffBriefResponse.
        """
        ptm_pack = self.synthesize_ptm_pack(validated_data)

        # Convert to AcademicHandoffBriefResponse for backward compatibility
        praise_points = [
            StrengthItemSchema(
                subject=p.subject,
                topic_name=p.topic_name,
                mastery_percentage=p.mastery_percentage,
                status=p.status,
            )
            for p in ptm_pack.praise_points
        ]

        remedial_gaps = [
            GapItemSchema(
                subject=g.subject,
                chapter_name=g.chapter_name,
                topic_name=g.topic_name,
                node_id=g.node_id,
                current_percentage=g.current_percentage,
                severity=g.severity,
                tutor_guidance=g.remedial_directive,
            )
            for g in ptm_pack.priority_gaps
        ]

        return AcademicHandoffBriefResponse(
            brief_id=ptm_pack.brief_id,
            child_id=ptm_pack.child_id,
            student_name=ptm_pack.student_name,
            standard_class=ptm_pack.standard_class,
            board=ptm_pack.board,
            academic_year=ptm_pack.academic_year,
            praise_points=praise_points,
            remedial_gaps=remedial_gaps,
            recommended_focus_next_2_weeks=ptm_pack.recommended_2_week_plan,
            tutor_talking_points=ptm_pack.talking_points,
            formatted_printable_text=ptm_pack.formatted_printable_text,
            generated_at=ptm_pack.generated_at,
        )

    def synthesize_ptm_pack(self, validated_data: Dict[str, Any]) -> PtmPackResponse:
        """
        Section 9 Complete Dynamic PTM Prep Pack Synthesizer.
        Generates deep diagnostic telemetry tailored to the target audience (TEACHER, TUTOR, COMPREHENSIVE).
        """
        child_id = str(validated_data.get("child_id", "CHILD_UNKNOWN"))
        student_name = str(validated_data.get("student_name", "Student"))
        standard_class = str(validated_data.get("standard_class", "Class 10"))
        board = str(validated_data.get("board", "CBSE"))
        academic_year = str(validated_data.get("academic_year", "2026-2027"))

        target_audience_raw = str(validated_data.get("target_audience", "TEACHER")).upper()
        try:
            target_audience = PtmAudienceEnum(target_audience_raw)
        except ValueError:
            target_audience = PtmAudienceEnum.TEACHER

        selected_subject = validated_data.get("selected_subject")
        if selected_subject:
            selected_subject = str(selected_subject).strip()

        strengths_raw = validated_data.get("strengths", [])
        gaps_raw = validated_data.get("gaps", [])
        trends_raw = validated_data.get("trends", [])

        # Filter by selected subject if requested
        if selected_subject:
            strengths_raw = [s for s in strengths_raw if str(s.get("subject", "")).lower() == selected_subject.lower()]
            gaps_raw = [g for g in gaps_raw if str(g.get("subject", "")).lower() == selected_subject.lower()]
            trends_raw = [t for t in trends_raw if str(t.get("subject", "")).lower() == selected_subject.lower()]

        # 1. Process Praise Points (>= 70% mastery)
        praise_points: List[PtmPraisePointSchema] = []
        for s in strengths_raw:
            pct = float(s.get("mastery_percentage", s.get("score", 80.0)))
            if pct >= 70.0:
                subj = str(s.get("subject", "General"))
                top = str(s.get("topic_name", "Core Topic"))
                status = "Mastered" if pct >= 80.0 else "Solid Foundation"
                narrative = f"Demonstrates high confidence ({pct}%) with strong grasp of foundational principles in {top}."
                praise_points.append(
                    PtmPraisePointSchema(
                        subject=subj,
                        topic_name=top,
                        mastery_percentage=pct,
                        status=status,
                        celebration_narrative=narrative,
                    )
                )

        if not praise_points:
            fallback_subj = selected_subject or "General Academics"
            praise_points.append(
                PtmPraisePointSchema(
                    subject=fallback_subj,
                    topic_name="Diligent Exam Participation",
                    mastery_percentage=75.0,
                    status="Consistent Effort",
                    celebration_narrative=f"Shows consistent test participation and positive learning disposition in {fallback_subj}.",
                )
            )

        # 2. Process Remedial Gaps (< 60% mastery)
        priority_gaps: List[PtmStrugglingGapSchema] = []
        for g in gaps_raw:
            pct = float(g.get("current_percentage", g.get("score", 45.0)))
            sev = "CRITICAL" if pct < 40.0 else "WEAK"
            subj = str(g.get("subject", "General"))
            top = str(g.get("topic_name", "Core Topic"))
            chap = str(g.get("chapter_name", top))
            node_id = str(g.get("node_id", "NODE_UNKNOWN"))

            # Pedagogical resolution
            pedagogy = resolve_topic_misconception_and_question(subj, top)
            misconception = str(g.get("misconception_type", pedagogy["misconception"]))
            question = str(g.get("struggling_question_example", pedagogy["question"]))
            directive = str(g.get("remedial_directive", pedagogy["directive"]))

            priority_gaps.append(
                PtmStrugglingGapSchema(
                    subject=subj,
                    chapter_name=chap,
                    topic_name=top,
                    node_id=node_id,
                    current_percentage=pct,
                    severity=sev,
                    misconception_type=misconception,
                    struggling_question_example=question,
                    remedial_directive=directive,
                )
            )

        # 3. Process Subject Trends
        trends: List[PtmSubjectTrendSchema] = []
        for t in trends_raw:
            subj = str(t.get("subject", "Subject"))
            cur_pct = float(t.get("current_percentage", 70.0))
            prior_pct = t.get("prior_percentage")
            prior_val = float(prior_pct) if prior_pct is not None else None
            delta = float(t.get("delta_percentage", 0.0))
            direction = str(t.get("direction", "STABLE")).upper()
            if direction not in ["IMPROVING", "STABLE", "DECLINING"]:
                direction = "IMPROVING" if delta > 2.0 else ("DECLINING" if delta < -2.0 else "STABLE")

            badge = f"{subj} {cur_pct:.1f}% ({direction})"
            recent_exams = [
                PtmExamTrajectoryItemSchema(
                    test_title=str(e.get("test_title", "Test")),
                    test_date=str(e.get("test_date", "")),
                    score_percentage=float(e.get("score_percentage", cur_pct)),
                    subject=subj,
                )
                for e in t.get("recent_exams", [])
            ]

            trends.append(
                PtmSubjectTrendSchema(
                    subject=subj,
                    current_percentage=cur_pct,
                    prior_percentage=prior_val,
                    delta_percentage=delta,
                    direction=direction,
                    consistency_badge=badge,
                    recent_exams=recent_exams,
                )
            )

        # 4. Formulate 2-Week Action Directive
        if priority_gaps:
            top_gap = priority_gaps[0]
            recommended_plan = (
                f"Target {top_gap.subject} - {top_gap.topic_name} (currently at {top_gap.current_percentage}%). "
                f"Allocate 20 minutes daily on core drills: '{top_gap.misconception_type}'. "
                f"Have the student solve representative problem: '{top_gap.struggling_question_example}' "
                f"before attempting the 10-minute diagnostic gap recheck."
            )
        else:
            focus_subj = selected_subject or "all core subjects"
            recommended_plan = (
                f"Maintain balanced review routine in {focus_subj} with emphasis on comprehensive syllabus coverage "
                f"and practice paper problem sets."
            )

        # 5. Formulate Audience-Specific Talking Points
        talking_points: List[str] = []
        lead_strength = praise_points[0]

        if target_audience == PtmAudienceEnum.TEACHER:
            talking_points.append(
                f"Praise & Foundation: Acknowledge that {student_name} is performing strongly in {lead_strength.subject} "
                f"({lead_strength.topic_name} at {lead_strength.mastery_percentage}%). Thank the teacher for classroom guidance."
            )
            if priority_gaps:
                g = priority_gaps[0]
                talking_points.append(
                    f"Diagnostic Evidence: In {g.subject}, our diagnostic identifies {g.topic_name} at {g.current_percentage}%. "
                    f"Specifically, {student_name} faces difficulty with: '{g.misconception_type}'."
                )
                talking_points.append(
                    f"Constructive Question: 'Could you suggest 2-3 targeted textbook problems or check {student_name}'s "
                    f"intermediate working steps during classroom problem sessions?'"
                )
                talking_points.append(
                    f"Classroom Engagement: Inquire about {student_name}'s attentiveness and hand-raising confidence in {g.subject} class."
                )
            else:
                talking_points.append(
                    f"Forward Planning: Discuss upcoming term syllabus chapters and pacing recommendations for board examinations."
                )

        elif target_audience == PtmAudienceEnum.TUTOR:
            talking_points.append(
                f"Confidence Anchor: Begin sessions by reinforcing {lead_strength.topic_name} ({lead_strength.mastery_percentage}%) "
                f"as a proven foundation."
            )
            if priority_gaps:
                g = priority_gaps[0]
                talking_points.append(
                    f"Operational Priority: Remediate {g.subject} — {g.topic_name} ({g.current_percentage}% mastery). "
                    f"Focus explicitly on: '{g.misconception_type}'."
                )
                talking_points.append(
                    f"Immediate Homework Drill: Administer problem '{g.struggling_question_example}' with zero calculator/book help."
                )
                talking_points.append(
                    f"SLA Recheck: Administer the 10-minute diagnostic gap recheck quiz once 5 practice variations are completed."
                )
            else:
                talking_points.append(
                    f"Revision Directive: Assign full-length model exam sections to enhance speed and answer formatting."
                )

        else:  # COMPREHENSIVE
            talking_points.append(
                f"Praise: Foundation in {lead_strength.subject} ({lead_strength.topic_name} at {lead_strength.mastery_percentage}%)."
            )
            if priority_gaps:
                g = priority_gaps[0]
                talking_points.append(
                    f"School Teacher Collaboration: Share diagnostic standing in {g.subject} ({g.topic_name}: {g.current_percentage}%) "
                    f"and ask for classroom board monitoring."
                )
                talking_points.append(
                    f"Home Tutor Remediation: Assign daily 20-min drills on '{g.misconception_type}'."
                )
            else:
                talking_points.append(
                    f"General Review: Sustain balanced study rhythm across all subjects."
                )

        # 6. Formulate WhatsApp Share Text
        wa_subject_str = f"({selected_subject})" if selected_subject else "(All Core Subjects)"
        wa_lines = [
            f"📋 *STUDIQS® SmartParent™ — PTM Diagnostic Brief*",
            f"👦 *Student:* {student_name} | {standard_class} ({board})",
            f"📅 *Date:* {datetime.utcnow().strftime('%d %B %Y')}",
            f"🎯 *Context:* {target_audience.value} Handoff {wa_subject_str}",
            "",
            f"🌟 *Strengths to Celebrate (Praise First):*",
        ]
        for p in praise_points[:2]:
            wa_lines.append(f"• *{p.subject}* — {p.topic_name}: {p.mastery_percentage:.1f}% ({p.status})")

        wa_lines.append("")
        wa_lines.append("⚠️ *Priority Diagnostic Gaps (Remediate Second):*")
        if priority_gaps:
            for g in priority_gaps[:2]:
                wa_lines.append(f"• [{g.severity}] *{g.subject}* | {g.topic_name} ({g.current_percentage:.1f}%)")
                wa_lines.append(f"  _Challenge:_ {g.misconception_type}")
                wa_lines.append(f"  _Sample Drill:_ {g.struggling_question_example}")
        else:
            wa_lines.append("• Zero active critical gaps. All evaluated topics performing solidly.")

        wa_lines.append("")
        wa_lines.append("💬 *Key Talking Points:*")
        for idx, tp in enumerate(talking_points[:3], start=1):
            wa_lines.append(f"{idx}. {tp}")

        wa_lines.append("")
        wa_lines.append(f"🎯 *2-Week Action Directive:*")
        wa_lines.append(recommended_plan)
        wa_lines.append("")
        wa_lines.append("— _Generated by Studiqs® SmartParent™ Diagnostic Telemetry_")
        whatsapp_share_text = "\n".join(wa_lines)

        # 7. Formulate Printable Formatted Text Layout
        print_lines = [
            "=" * 72,
            f"STUDIQS® SmartParent™ — ACADEMIC HANDOFF BRIEF (PTM / TUTOR PREP PACK)",
            "=" * 72,
            f"Student: {student_name} | Grade: {standard_class} ({board}) | Academic Year: {academic_year}",
            f"Target Audience: {target_audience.value} | Subject Scope: {selected_subject or 'All Subjects'}",
            f"Generated: {datetime.utcnow().strftime('%d %B %Y')} | Confidential Diagnostic Brief",
            "-" * 72,
            "",
            "1. ACCOMPLISHMENTS & STRENGTHS TO CELEBRATE (Praise First):",
        ]
        for p in praise_points[:3]:
            print_lines.append(f"  • {p.subject} — {p.topic_name}: {p.mastery_percentage:.1f}% ({p.status})")
            print_lines.append(f"    {p.celebration_narrative}")

        print_lines.extend([
            "",
            "2. PRIORITY DIAGNOSTIC LEARNING GAPS (Targeted Remediation):",
        ])
        if priority_gaps:
            for g in priority_gaps[:3]:
                print_lines.append(f"  • [{g.severity}] {g.subject} | {g.chapter_name}: {g.topic_name} ({g.current_percentage:.1f}%)")
                print_lines.append(f"    Misconception Pattern: {g.misconception_type}")
                print_lines.append(f"    Struggling Problem:   {g.struggling_question_example}")
                print_lines.append(f"    Remedial Directive:   {g.remedial_directive}")
        else:
            print_lines.append("  • Zero active critical gaps. Student is performing steadily across evaluated topics.")

        if trends:
            print_lines.extend([
                "",
                "3. SUBJECT SCORE TRAJECTORIES & TRENDS:",
            ])
            for tr in trends[:3]:
                delta_str = f"+{tr.delta_percentage:.1f}%" if tr.delta_percentage > 0 else f"{tr.delta_percentage:.1f}%"
                print_lines.append(f"  • {tr.subject}: Current {tr.current_percentage:.1f}% | Direction: {tr.direction} ({delta_str})")

        print_lines.extend([
            "",
            f"4. KEY TALKING POINTS FOR PARENT-TEACHER MEETING ({target_audience.value}):",
        ])
        for idx, tp in enumerate(talking_points, start=1):
            print_lines.append(f"  {idx}. {tp}")

        print_lines.extend([
            "",
            "5. RECOMMENDED 2-WEEK ACTION PLAN:",
            f"  {recommended_plan}",
            "",
            "=" * 72,
            "Confidential diagnostic brief prepared exclusively by Studiqs SmartParent.",
            "=" * 72,
        ])
        formatted_printable_text = "\n".join(print_lines)

        brief_id = f"PTM_{datetime.utcnow().strftime('%Y%m%d%H%M')}_{str(child_id)[:8]}"

        return PtmPackResponse(
            brief_id=brief_id,
            child_id=child_id,
            student_name=student_name,
            standard_class=standard_class,
            board=board,
            academic_year=academic_year,
            target_audience=target_audience,
            selected_subject=selected_subject,
            trends=trends,
            praise_points=praise_points,
            priority_gaps=priority_gaps,
            talking_points=talking_points,
            recommended_2_week_plan=recommended_plan,
            whatsapp_share_text=whatsapp_share_text,
            formatted_printable_text=formatted_printable_text,
            generated_at=datetime.utcnow().isoformat(),
        )

    def fallback(self, error: Exception, input_data: Any) -> AcademicHandoffBriefResponse:
        """Safe fallback producing basic handoff brief without failing."""
        logger.warning(f"[AcademicHandoffEngine] Fallback triggered due to error: {error}")
        child_id = str(input_data.get("child_id", "UNKNOWN")) if isinstance(input_data, dict) else "UNKNOWN"
        student_name = str(input_data.get("student_name", "Student")) if isinstance(input_data, dict) else "Student"

        return AcademicHandoffBriefResponse(
            brief_id=f"BRIEF_FALLBACK_{str(child_id)[:8]}",
            child_id=child_id,
            student_name=student_name,
            standard_class="Class 10",
            board="CBSE",
            academic_year="2026-2027",
            praise_points=[
                StrengthItemSchema(
                    subject="General Academics",
                    topic_name="Diligent Effort",
                    mastery_percentage=75.0,
                    status="Consistent",
                )
            ],
            remedial_gaps=[],
            recommended_focus_next_2_weeks="Review weekly test papers and reinforce foundational concepts.",
            tutor_talking_points=["Discuss general revision routine and classroom engagement."],
            formatted_printable_text=f"Academic Handoff Brief for {student_name} (Baseline Confirmed).",
            generated_at=datetime.utcnow().isoformat(),
        )
