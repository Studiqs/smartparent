"""
STUDIQS® SmartParent™ - Neuro-Symbolic Intent Classifier & NLU Engine
=============================================================================
Module: src.smartparent.rag.intent_classifier

Provides real-time multi-task intent classification and BIO slot tagging:
  - Pillar Head (6 Academic Pillars): OVERALL, SUBJECT, TOPIC_GAPS, MOM_TRENDS,
    CONSISTENCY, NEXT_ACTION.
  - Logic Head: STATUS, DRILLDOWN, TREND, COMPARISON, PROJECTION, PRESCRIPTION.
  - Slot BIO Tagger: CHILD, SUBJECT, TOPIC, TIMEFRAME, EXCLUSIONS.
  - Sub-1ms Zero-Mutation Security Firewall (blocks SQL/account mutations).
  - Colloquial Tamil & Tanglish Academic Keyword Grounding.
  - Uses High-Performance Singleton NLUModelRegistry (sub-15ms inference).
=============================================================================
"""

import os
import re
import json
import time
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

from src.smartparent.rag.interfaces import IIntentClassifier
from src.smartparent.rag.model_registry import NLUModelRegistry


class VoiceIntentClassifier(IIntentClassifier):
    """
    Sub-20ms 3-Head Neuro-Symbolic Transformer NLU Engine.
    Quantized to int8; runs locally on CPU with zero cloud dependencies.
    Implements IIntentClassifier protocol.
    """

    PILLARS = [
        "OVERALL_ACADEMIC_STANDING",
        "SUBJECT_PERFORMANCE",
        "GRANULAR_TOPIC_GAPS",
        "MONTH_ON_MONTH_TRENDS",
        "TERM_CONSISTENCY",
        "NEXT_GAP_RECHECK_ACTION",
        "ZERO_MUTATION_FIREWALL",
    ]

    LOGIC_TYPES = [
        "STATUS",
        "DRILLDOWN",
        "TREND",
        "COMPARISON",
        "PROJECTION",
        "PRESCRIPTION",
    ]

    SUBJECT_ALIASES = {
        "mathematics": "Mathematics",
        "maths": "Mathematics",
        "math": "Mathematics",
        "ganitham": "Mathematics",
        "social science": "Social Science",
        "social studies": "Social Science",
        "social": "Social Science",
        "computer science": "Computer Science",
        "computer": "Computer Science",
        "cs": "Computer Science",
        "general science": "Science",
        "science": "Science",
        "sci": "Science",
        "physics": "Physics",
        "phy": "Physics",
        "chemistry": "Chemistry",
        "chem": "Chemistry",
        "biology": "Biology",
        "bio": "Biology",
        "english": "English",
        "eng": "English",
    }

    def __init__(self, bundle_dir: Optional[str] = None):
        # Delegate heavy model weight loading to the thread-safe Model Registry Singleton
        self.registry = NLUModelRegistry.get_instance(bundle_dir=bundle_dir)
        self.bundle_dir = self.registry.bundle_dir
        self.config = self.registry.config
        self.id_to_bio = self.registry.id_to_bio
        self.tokenizer = self.registry.tokenizer
        self.session = self.registry.session

        # Security patterns (Zero-Mutation Firewall)
        self.security_patterns = re.compile(
            r"\b(delete|remove|erase|wipe|edit|modify|change\s+.*mark|change\s+.*score|"
            r"update\s+.*score|update\s+.*mark|add\s+.*mark|insert|drop\s+table|truncate|"
            r"database|refund|razorpay|pay\s+.*fee|change\s+.*plan|change\s+.*subscription|"
            r"cancel\s+.*subscription|share\s+.*file|share\s+.*external|assign\s+.*expert)\b",
            re.IGNORECASE,
        )

        self.academic_anchor_pattern = re.compile(
            r"\b(mark|marks|score|scores|test|tests|exam|exams|assessment|assessments|"
            r"subject|subjects|overall|holistic|standing|status|progress|perform|performing|"
            r"performance|result|results|percentage|grade|gap|gaps|weak|critical|struggle|"
            r"lose|lost|drop|dropped|improve|improved|improvement|decline|trend|trajectory|"
            r"consistency|consistent|steady|stability|stable|board|readiness|recheck|drill|"
            r"practice|worksheet|paper|topic|topics|chapter|chapters|syllabus|compare|"
            r"padikira|evalo|vaangirukan|munnadi)\b",
            re.IGNORECASE,
        )

        self.anaphora_pattern = re.compile(
            r"\b(in\s+that|in\s+it|for\s+that|about\s+that|fix\s+it|close\s+it|what\s+about|how\s+about|and\s+in|and\s+for)\b",
            re.IGNORECASE,
        )

        self.keyword_intents = {
            0: ["overall", "holistic", "all subjects", "student 360", "complete summary", "overall ah", "overall academic"],
            1: ["perform in", "latest score", "latest test", "percentage in", "evalo marks", "poor score", "got in", "test results", "score in", "marks in"],
            2: ["lose marks", "lost marks", "weak", "critical", "topic gap", "topics need", "struggle", "immediate attention"],
            3: ["changed", "since the last test", "month on month", "trajectory", "improvement or decline", "munnadi test", "trend"],
            4: ["consistency", "score stability", "steady", "board exam", "readiness", "midterm assessments", "stable"],
            5: ["recheck", "practice paper", "practice drill", "how to fix", "how do we fix", "aduthu enna", "close gap", "next recommended"],
        }

    def security_check(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        Fast regex evaluation for mutations, billing tampering, or destructive commands.
        Returns (is_blocked, reason).
        """
        match = self.security_patterns.search(text)
        if match:
            return True, f"Mutation operation '{match.group(0)}' blocked by zero-mutation security firewall."
        return False, None

    def resolve_child_entity(
        self,
        tokens: List[str],
        tags: List[str],
        authorized_children: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Extracts and verifies child entity against authorized family roster.
        """
        if not authorized_children:
            return None
        text_lower = " ".join(tokens).lower()
        for child in authorized_children:
            if re.search(rf"\b{re.escape(child.lower())}\b", text_lower):
                return child
        return None

    def _align_subwords(self, words: List[str], word_ids: List[Optional[int]], slot_logits_seq: np.ndarray) -> Dict[str, List[str]]:
        word_to_tag = {}
        for token_idx, word_idx in enumerate(word_ids):
            if word_idx is None or word_idx in word_to_tag:
                continue
            if token_idx < len(slot_logits_seq):
                tag_id = int(np.argmax(slot_logits_seq[token_idx]))
                word_to_tag[word_idx] = self.id_to_bio.get(tag_id, "O")

        slots: Dict[str, List[str]] = {"CHILD": [], "SUBJ": [], "TOPIC": [], "TIME": [], "EXCL": []}
        current_entity, current_type = [], None

        for idx, word in enumerate(words):
            clean_w = word.strip("?.,!'\"")
            if not clean_w:
                continue
            tag = word_to_tag.get(idx, "O")
            if tag.startswith("B-"):
                if current_entity and current_type in slots:
                    slots[current_type].append(" ".join(current_entity))
                current_type = tag.split("-", 1)[1].strip()
                current_entity = [clean_w]
            elif tag.startswith("I-") and current_type == tag.split("-", 1)[1].strip():
                current_entity.append(clean_w)
            else:
                if current_entity and current_type in slots:
                    slots[current_type].append(" ".join(current_entity))
                current_entity, current_type = [], None

        if current_entity and current_type in slots:
            slots[current_type].append(" ".join(current_entity))
        return slots

    def _extract_subjects(self, text_lower: str, neural_subjs: List[str]) -> List[str]:
        found: List[str] = []
        for alias, canonical in self.SUBJECT_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", text_lower):
                if canonical not in found:
                    found.append(canonical)
        for ns in neural_subjs:
            canon = self.SUBJECT_ALIASES.get(ns.lower())
            if canon and canon not in found:
                found.append(canon)
        return found

    def predict(
        self,
        text: str,
        threshold: float = 0.50,
        authorized_family_children: Optional[List[str]] = None,
        previous_session_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes multi-task inference, returning pillar, logic, and slot entities.
        """
        t0 = time.perf_counter()
        clean_text = text.replace("?", " ?").replace(".", " .").replace(",", " ,")
        words = clean_text.split()
        text_lower = text.lower()

        # Token calculation
        input_token_count = len(words)
        enc_ids, enc_mask, word_ids = None, None, None
        if self.tokenizer:
            enc = self.tokenizer.encode(text)
            input_token_count = sum(1 for m in enc.attention_mask if m > 0)
            enc_ids = enc.ids
            enc_mask = enc.attention_mask
            word_ids = enc.word_ids

        # 1. Zero-Mutation Security Firewall (< 0.1ms)
        is_blocked, _ = self.security_check(text)
        if is_blocked:
            ms = round((time.perf_counter() - t0) * 1000, 3)
            return {
                "query": text,
                "pillar_id": 6,
                "pillar_name": "ZERO_MUTATION_FIREWALL",
                "logic_id": 0,
                "logic_name": "STATUS",
                "confidence": 1.0,
                "slots": {"CHILD": [], "SUBJ": [], "TOPIC": [], "TIME": [], "EXCL": []},
                "security_blocked": True,
                "out_of_scope": False,
                "input_tokens": input_token_count,
                "nlu_latency_ms": ms,
            }

        # 2. ONNX Neural Inference
        pillar_id = 0
        logic_id = 0
        confidence = 0.85
        slots = {"CHILD": [], "SUBJ": [], "TOPIC": [], "TIME": [], "EXCL": []}

        if self.session and enc_ids is not None:
            ort_inputs = {
                "input_ids": np.array([enc_ids[:64]], dtype=np.int64),
                "attention_mask": np.array([enc_mask[:64]], dtype=np.int64),
            }
            p_logits, l_logits, s_logits = self.session.run(None, ort_inputs)
            p_probs = 1.0 / (1.0 + np.exp(-np.clip(p_logits[0], -20, 20)))

            if len(p_probs) > 6 and p_probs[6] >= 0.65:
                ms = round((time.perf_counter() - t0) * 1000, 2)
                return {
                    "query": text,
                    "pillar_id": 6,
                    "pillar_name": "ZERO_MUTATION_FIREWALL",
                    "logic_id": 0,
                    "logic_name": "STATUS",
                    "confidence": round(float(p_probs[6]), 4),
                    "slots": slots,
                    "security_blocked": True,
                    "out_of_scope": False,
                    "input_tokens": input_token_count,
                    "nlu_latency_ms": ms,
                }

            pillar_id = int(np.argmax(p_probs[:6]))
            confidence = round(float(p_probs[pillar_id]), 4)
            logic_id = int(np.argmax(l_logits[0])) if len(l_logits[0]) > 0 else 0

            if word_ids:
                slots = self._align_subwords(words, word_ids[:64], s_logits[0])
        else:
            # Fallback keyword-based routing
            for p_idx, kw_list in self.keyword_intents.items():
                if any(kw in text_lower for kw in kw_list):
                    pillar_id = p_idx
                    break

        # Subject extraction
        slots["SUBJ"] = self._extract_subjects(text_lower, slots.get("SUBJ", []))

        # Child entity matching (Authorized roster + known names)
        detected_children = []
        roster = list(authorized_family_children or []) + self.config.get("known_children", [])
        for c in roster:
            if re.search(rf"\b{re.escape(c.lower())}\b", text_lower):
                if c not in detected_children:
                    detected_children.append(c)
        for c in slots.get("CHILD", []):
            if c not in detected_children:
                detected_children.append(c)
        slots["CHILD"] = detected_children

        # Topic matching
        known_topics = self.config.get("known_topics", [])
        for t in known_topics:
            if re.search(rf"\b{re.escape(t.lower())}\b", text_lower):
                if t not in slots.get("TOPIC", []):
                    slots.setdefault("TOPIC", []).append(t)

        # Multi-turn anaphora inheritance
        if previous_session_state and not slots["CHILD"] and previous_session_state.get("child"):
            slots["CHILD"] = [previous_session_state["child"]]
        if previous_session_state and not slots["SUBJ"] and previous_session_state.get("subject"):
            if self.anaphora_pattern.search(text_lower):
                slots["SUBJ"] = [previous_session_state["subject"]]

        # Out-of-scope evaluation (queries unrelated to student academics, marks, syllabus, or progress)
        has_academic_anchor = bool(self.academic_anchor_pattern.search(text_lower))
        has_subject = bool(slots.get("SUBJ"))
        has_child = bool(slots.get("CHILD"))
        has_topic = bool(slots.get("TOPIC"))
        has_keyword = any(kw in text_lower for kw_list in self.keyword_intents.values() for kw in kw_list)
        is_out_of_scope = not (has_academic_anchor or has_subject or has_child or has_topic or has_keyword)

        ms = round((time.perf_counter() - t0) * 1000, 2)
        pillar_name = self.PILLARS[pillar_id] if pillar_id < len(self.PILLARS) else self.PILLARS[0]
        logic_name = self.LOGIC_TYPES[logic_id] if logic_id < len(self.LOGIC_TYPES) else self.LOGIC_TYPES[0]

        return {
            "query": text,
            "pillar_id": pillar_id,
            "pillar_name": pillar_name,
            "logic_id": logic_id,
            "logic_name": logic_name,
            "confidence": confidence,
            "slots": slots,
            "security_blocked": False,
            "out_of_scope": is_out_of_scope,
            "input_tokens": input_token_count,
            "nlu_latency_ms": ms,
        }
