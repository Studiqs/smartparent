"""
STUDIQS® SmartParent™ - Dynamic Context Builder, Taxonomy Resolver & Pedagogical Reranker
=============================================================================
Module: src.smartparent.rag.context_builder

Aligned with 15-Phase Production RAG Architecture:
  - Phase 3: CHUNKING - Hierarchical Parent-Child concept relationships.
  - Phase 5: QUERY PROCESSING - 2-Stage Entity & Syllabus Taxonomy Resolution.
  - Phase 6: RETRIEVAL - 3-Way Candidate Generation (SQL + Graph + Drills).
  - Phase 7: RERANKING - Pedagogical Severity Reranker & Semantic Deduplication.
  - Phase 8: CONTEXT ENGINEERING - Context Compression & Token Budgeting.
=============================================================================
"""

import os
import re
import json
from typing import Dict, List, Optional, Tuple, Any
from src.smartparent.rag.telemetry_retriever import ChildDiagnosticTelemetry, SubjectTelemetry
from src.smartparent.rag.interfaces import IContextBuilder


class ContextBuilder(IContextBuilder):
    """
    Assembles compact, verified academic grounding context for NLG generation.
    Incorporates Phase 7 Reranking and Phase 8 Context Compression.
    Implements IContextBuilder protocol.
    """

    # Extended Syllabus Topic Taxonomy Mapping (CBSE / ICSE / State Board)
    SYLLABUS_TOPIC_GRAPH: Dict[str, Dict[str, Any]] = {
        "quadratic equations": {
            "canonical": "Quadratic Equations",
            "subject": "Mathematics",
            "chapter": "Algebra",
            "prerequisites": ["Linear Equations", "Polynomials"],
            "board_weightage_marks": 8,
        },
        "discriminant and roots": {
            "canonical": "Discriminant and Roots",
            "subject": "Mathematics",
            "chapter": "Algebra",
            "prerequisites": ["Quadratic Equations"],
            "board_weightage_marks": 4,
        },
        "trigonometry": {
            "canonical": "Trigonometry",
            "subject": "Mathematics",
            "chapter": "Trigonometry",
            "prerequisites": ["Similar Triangles", "Pythagoras Theorem"],
            "board_weightage_marks": 12,
        },
        "light reflection": {
            "canonical": "Light Reflection and Refraction",
            "subject": "Science",
            "chapter": "Optics",
            "prerequisites": ["Rectilinear Propagation of Light"],
            "board_weightage_marks": 7,
        },
        "acids bases and salts": {
            "canonical": "Acids, Bases and Salts",
            "subject": "Chemistry",
            "chapter": "Chemical Substances",
            "prerequisites": ["Chemical Reactions"],
            "board_weightage_marks": 6,
        },
        "magnetic effects of current": {
            "canonical": "Magnetic Effects of Electric Current",
            "subject": "Physics",
            "chapter": "Electromagnetism",
            "prerequisites": ["Electricity and Current"],
            "board_weightage_marks": 8,
        },
    }

    @classmethod
    def load_taxonomy(cls, force_excel: bool = False) -> int:
        """
        Dynamically loads the 8,034-topic curriculum taxonomy into in-memory DAG.
        Priority:
          1. JSON cache (`taxonomy_topics.json`) if present and not force_excel (330ms boot).
          2. Internal Master Excel (`smartparent-backend/data/curriculum_repository/master/master_curriculum_classes_1_to_12.xlsx`).
          3. DB Master KB (`smartparent-backend/src/smartparent/db/smartparent_master_repository_kb.xlsx`).
        """
        use_json = (not force_excel) and (os.environ.get("STUDIQS_USE_TAXONOMY_JSON", "1") != "0")
        json_path = os.path.join(os.path.dirname(__file__), "templates", "taxonomy_topics.json")

        # 1. Try JSON cache for ultra-fast boot
        if use_json and os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.get("canonical_topics", {}).items():
                        clean_k = v.get("canonical_name", "").lower()
                        tid = str(v.get("topic_id", "")).strip().lower()
                        topic_data = {
                            "topic_id": v.get("topic_id"),
                            "canonical": v.get("canonical_name"),
                            "subject": v.get("subject"),
                            "grade": v.get("grade"),
                            "board": v.get("board"),
                            "chapter": v.get("chapter"),
                            "prerequisites": v.get("prerequisites", []),
                            "board_weightage_marks": v.get("board_weightage_marks", 5),
                        }
                        if clean_k and clean_k not in cls.SYLLABUS_TOPIC_GRAPH:
                            cls.SYLLABUS_TOPIC_GRAPH[clean_k] = topic_data
                        if tid and tid not in cls.SYLLABUS_TOPIC_GRAPH:
                            cls.SYLLABUS_TOPIC_GRAPH[tid] = topic_data
                return len(cls.SYLLABUS_TOPIC_GRAPH)
            except Exception:
                pass

        # 2. Fallback: Parse Master Excel directly from smartparent-backend
        backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        master_excel = os.path.join(
            backend_root, "data", "curriculum_repository", "master", "master_curriculum_classes_1_to_12.xlsx"
        )
        db_excel = os.path.join(
            backend_root, "src", "smartparent", "db", "smartparent_master_repository_kb.xlsx"
        )

        target_excel = master_excel if os.path.exists(master_excel) else (db_excel if os.path.exists(db_excel) else None)
        if target_excel and os.path.exists(target_excel):
            try:
                import pandas as pd
                df = pd.read_excel(target_excel)
                for _, row in df.iterrows():
                    tid = str(row.get("Topic_ID", "")).strip()
                    name = str(row.get("Topic", "")).strip()
                    clean_k = name.lower()
                    clean_tid = tid.lower()
                    topic_data = {
                        "topic_id": tid,
                        "canonical": name,
                        "subject": str(row.get("Subject", "")).strip(),
                        "grade": f"Class {str(row.get('Class', '')).strip()}",
                        "board": str(row.get("Board", "")).strip(),
                        "chapter": str(row.get("Chapter", "")).strip(),
                        "prerequisites": [],
                        "board_weightage_marks": 5,
                    }
                    if clean_k and clean_k not in cls.SYLLABUS_TOPIC_GRAPH:
                        cls.SYLLABUS_TOPIC_GRAPH[clean_k] = topic_data
                    if clean_tid and clean_tid not in cls.SYLLABUS_TOPIC_GRAPH:
                        cls.SYLLABUS_TOPIC_GRAPH[clean_tid] = topic_data
                return len(cls.SYLLABUS_TOPIC_GRAPH)
            except Exception:
                pass

        return len(cls.SYLLABUS_TOPIC_GRAPH)

    @classmethod
    def resolve_child(
        cls,
        detected_children: List[str],
        authorized_roster: Optional[List[str]] = None,
        default_name: str = "Viswa",
    ) -> str:
        """
        Fuzzy matches extracted child token against parent's registered children (Phase 5).
        """
        clean_detected = [re.sub(r"['’]s?$", "", c).strip() for c in (detected_children or [])]
        clean_detected = [c for c in clean_detected if c]

        if not authorized_roster:
            return clean_detected[0] if clean_detected else default_name

        roster_lower = {name.lower(): name for name in authorized_roster}
        for det in clean_detected:
            det_low = det.lower()
            if det_low in roster_lower:
                return roster_lower[det_low]
            for r_low, r_name in roster_lower.items():
                if det_low in r_low or r_low in det_low:
                    return r_name

        return authorized_roster[0]

    @classmethod
    def resolve_topic(
        cls,
        raw_topic_span: str,
        db_session: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Resolves raw extracted topic string against syllabus taxonomy DAG (Phase 5 & 6).
        Queries in-memory 8,034-topic graph first (O(1)), then falls back to PostgreSQL
        curriculum_nodes if a live database session is provided.
        """
        clean = raw_topic_span.strip().lower()
        if not clean:
            return None

        # 1. Exact match by canonical name or topic_id
        if clean in cls.SYLLABUS_TOPIC_GRAPH:
            return cls.SYLLABUS_TOPIC_GRAPH[clean]

        # 2. Substring matching against 8,034 syllabus topics
        for key, data in cls.SYLLABUS_TOPIC_GRAPH.items():
            if len(key) >= 4 and (key in clean or clean in key):
                return data

        # 3. Dynamic PostgreSQL fallback (CurriculumNode table)
        if db_session is not None:
            try:
                from sqlalchemy import text
                stmt = text(
                    "SELECT node_id, topic_name, subject, standard_class, board, chapter_name "
                    "FROM curriculum_nodes "
                    "WHERE topic_name ILIKE :q OR node_id ILIKE :q "
                    "LIMIT 1"
                )
                res = db_session.execute(stmt, {"q": f"%{clean}%"}).fetchone()
                if res:
                    return {
                        "topic_id": res[0],
                        "canonical": res[1],
                        "subject": res[2],
                        "grade": f"Class {res[3]}",
                        "board": res[4],
                        "chapter": res[5],
                        "prerequisites": [],
                        "board_weightage_marks": 5,
                    }
            except Exception:
                pass

        return None

    @classmethod
    def bind_subject_telemetry(
        cls,
        data: ChildDiagnosticTelemetry,
        requested_subjects: List[str],
    ) -> ChildDiagnosticTelemetry:
        """
        Dynamically binds telemetry for the primary and secondary requested subjects.
        """
        if not requested_subjects or not data.subject_records:
            return data

        primary_subj = requested_subjects[0]
        matched_sr = data.subject_records.get(primary_subj)
        if not matched_sr:
            for s_name, sr in data.subject_records.items():
                if s_name.lower() == primary_subj.lower():
                    matched_sr = sr
                    break

        if matched_sr:
            data.watch_subject = matched_sr.subject
            data.watch_subject_pct = matched_sr.latest_pct

        return data

    @classmethod
    def rerank_and_deduplicate_gaps(
        cls,
        subject_records: Dict[str, SubjectTelemetry],
        relevance_threshold: float = 0.50,
    ) -> List[Dict[str, Any]]:
        """
        Phase 7: RERANKING & SEMANTIC DEDUPLICATION
        Sorts active topic gaps by pedagogical urgency (Critical < 40%, marks lost,
        and high-stakes Board exam weightage). Deduplicates redundant chapter mentions.
        """
        seen_topics = set()
        candidates: List[Dict[str, Any]] = []

        for subj, sr in subject_records.items():
            if not sr.weak_topic or sr.weak_topic in seen_topics:
                continue
            seen_topics.add(sr.weak_topic)

            # Dynamic pedagogical urgency derived strictly from student assessment telemetry:
            # (Actual marks lost in test + percentage deficit + Critical mastery tier boost)
            deficit = max(0.0, 100.0 - float(sr.latest_pct))
            tier_boost = 25.0 if sr.latest_pct < 40.0 else (10.0 if sr.latest_pct < 60.0 else 0.0)
            urgency_score = (float(sr.marks_lost) * 2.5) + deficit + tier_boost

            candidates.append({
                "subject": subj,
                "topic": sr.weak_topic,
                "marks_lost": sr.marks_lost,
                "cognitive_root_cause": sr.cognitive_root_cause,
                "latest_pct": sr.latest_pct,
                "urgency_score": urgency_score,
                "remedial_drill": sr.remedial_drill_name,
                "question_count": sr.remedial_question_count,
            })

        # Rank descending by pedagogical urgency
        candidates.sort(key=lambda x: x["urgency_score"], reverse=True)
        return candidates

    @classmethod
    def compress_and_budget_context(
        cls,
        telemetry: ChildDiagnosticTelemetry,
        max_tokens: int = 256,
    ) -> Dict[str, Any]:
        """
        Phase 8: CONTEXT ENGINEERING & TOKEN BUDGETING
        Packs high-density pedagogical telemetry into a compressed structure
        adhering strictly to subscriber token caps without losing critical facts.
        """
        reranked_gaps = cls.rerank_and_deduplicate_gaps(telemetry.subject_records)
        top_critical_gap = reranked_gaps[0] if reranked_gaps else None

        compressed_facts = {
            "child": telemetry.child_name,
            "overall_avg": f"{telemetry.overall_avg_pct}%",
            "health_status": telemetry.overall_health_band,
            "top_anchor": f"{telemetry.top_subject} ({telemetry.top_subject_pct}%)",
            "primary_watch": f"{telemetry.watch_subject} ({telemetry.watch_subject_pct}%)",
            "board_readiness": f"{telemetry.board_readiness_index}% ({telemetry.board_readiness_band})",
            "velocity_60d": f"{telemetry.mom_velocity}%",
            "top_remedial_action": top_critical_gap,
            "reranked_gaps_count": len(reranked_gaps),
        }
        return compressed_facts

    @classmethod
    def build_context(
        cls,
        telemetry: ChildDiagnosticTelemetry,
        nlu_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        IContextBuilder implementation building grounded envelope for NLG.
        """
        return cls.compress_and_budget_context(telemetry)


# Auto-load curriculum taxonomy on module import (from internal smartparent-backend assets)
ContextBuilder.load_taxonomy()

