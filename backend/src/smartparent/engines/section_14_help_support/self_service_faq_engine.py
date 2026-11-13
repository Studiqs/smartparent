"""
STUDIQS® SmartParent™ (v6.2 Complete) - Self-Service FAQ & Knowledge Base Engine
=============================================================================
Module: src.smartparent.engines.section_14_help_support.self_service_faq_engine
Section 14: Help Centre, Ticketing and Support Operating Models (Self-Service Tier)

Implements the Tier-1 automated self-service resolution engine:
  - Curated, verified knowledge base for Indian K-12 parents across all Studiqs domains.
  - Multi-category taxonomy (Billing, Marksheet OCR, Topic Gaps, PTM Brief, Expert SLA, Voice AI).
  - High-precision keyword, token, and tag matching algorithm with relevance scoring.
  - Deflects support ticket creation by answering 80%+ of common parent inquiries instantly.
=============================================================================
"""

import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict

from src.smartparent.engines.section_00_core.base_engine import BaseEngine
from src.smartparent.core.constants import SupportTicketCategory


# =============================================================================
# 1. Pydantic v2 Schemas for FAQ
# =============================================================================

class FAQArticle(BaseModel):
    """Knowledge base article definition."""
    model_config = ConfigDict(extra="ignore")

    article_id: str
    category: str
    title: str
    summary: str
    content: str
    tags: List[str] = Field(default_factory=list)
    action_label: Optional[str] = None
    action_deep_link: Optional[str] = None
    helpful_count: int = 0


class FAQSearchResult(BaseModel):
    """Search query matched article with relevance score."""
    model_config = ConfigDict(extra="ignore")

    article: FAQArticle
    relevance_score: float
    matched_terms: List[str]


class FAQSearchResponse(BaseModel):
    """Response payload for knowledge base search query."""
    model_config = ConfigDict(extra="ignore")

    query: str
    total_found: int
    results: List[FAQSearchResult]
    suggested_ticket_category: Optional[str] = None
    fallback_message: Optional[str] = None


# =============================================================================
# 2. Curated Knowledge Base Articles Catalog
# =============================================================================

CURATED_FAQ_ARTICLES: List[FAQArticle] = [
    # --- BILLING & SUBSCRIPTION ---
    FAQArticle(
        article_id="FAQ-BILL-001",
        category=SupportTicketCategory.BILLING_REFUND.value,
        title="What are the subscription plans and prices for Studiqs SmartParent?",
        summary="Overview of Basic, Advanced, and Pro plans with GST-inclusive pricing for 1, 3, 6, and 12 months.",
        content=(
            "Studiqs SmartParent offers three flexible plans with GST-inclusive pricing:\n"
            "• Basic Plan: 1 Mo ₹199 | 3 Mo ₹399 | 6 Mo ₹699 | 12 Mo ₹1,199 (1 Child, 4 uploads/mo, PTM Briefs).\n"
            "• Advanced Plan: 1 Mo ₹399 | 3 Mo ₹799 | 6 Mo ₹1,399 | 12 Mo ₹2,399 (Up to 2 Children, 12 uploads/mo, Board Readiness).\n"
            "• Pro Plan (with Voice AI): 1 Mo ₹599 | 3 Mo ₹1,199 | 6 Mo ₹2,099 | 12 Mo ₹3,599 (Up to 4 Children, 30 uploads/mo, AI Voice Assistant).\n"
            "All multi-month subscriptions include automatic savings of up to 50% compared to monthly renewal."
        ),
        tags=["pricing", "plans", "subscription", "cost", "basic", "advanced", "pro", "fees", "gst", "annual"],
        action_label="View Plan Catalog",
        action_deep_link="/subscription/catalog",
    ),
    FAQArticle(
        article_id="FAQ-BILL-002",
        category=SupportTicketCategory.BILLING_REFUND.value,
        title="How can I download my official GST Tax Invoice and receipt?",
        summary="Steps to download GST-compliant tax invoices (SAC Code 998431) with CGST/SGST details.",
        content=(
            "Every payment generates an instant, sequential GST Tax Invoice (Format: INV-STQ-YYYY-NNNNN):\n"
            "1. Navigate to 'Account' > 'Subscription & Invoices'.\n"
            "2. Tap on any past payment transaction to view the complete tax breakdown (Base amount, CGST 9%, SGST 9% or IGST 18%).\n"
            "3. Tap 'Download PDF Invoice' for your records or tax reimbursement. SAC Code is 998431 (Online Educational Services)."
        ),
        tags=["invoice", "gst", "receipt", "download", "tax", "billing", "payment", "sac"],
        action_label="Go to Invoices",
        action_deep_link="/subscription/invoices",
    ),
    FAQArticle(
        article_id="FAQ-BILL-003",
        category=SupportTicketCategory.BILLING_REFUND.value,
        title="What is the refund policy if I cancel my subscription?",
        summary="Refund rules, mid-term proration, and Razorpay refund turnaround timelines.",
        content=(
            "If you cancel an active subscription, your plan benefits remain active until the end of your prepaid billing period.\n"
            "• Technical / Duplicate Deductions: If a payment was deducted twice due to network latency, the duplicate payment is automatically refunded within 5-7 business days via Razorpay.\n"
            "• Unused Period Proration: For plan upgrades, your remaining unused days on your previous plan are automatically credited towards your new plan."
        ),
        tags=["refund", "cancel", "cancellation", "duplicate", "deduction", "money back", "razorpay"],
        action_label="Check Payment Status",
        action_deep_link="/subscription/status",
    ),

    # --- EVIDENCE INTAKE & MARKSHEET OCR ---
    FAQArticle(
        article_id="FAQ-OCR-001",
        category=SupportTicketCategory.MARKS_ENTRY.value,
        title="What file formats are supported for uploading report cards and question papers?",
        summary="Accepted file types, size limits, and tips for clear OCR extraction from smartphone photos.",
        content=(
            "You can upload student marksheets and question papers using:\n"
            "• Formats: PDF documents, JPG, PNG, and HEIC smartphone camera photos.\n"
            "• Max File Size: Up to 15 MB per document.\n"
            "• Best Results Tip: Place the document on a flat, well-lit surface and capture directly from above without finger shadows or curved page folds."
        ),
        tags=["upload", "file", "pdf", "image", "photo", "format", "camera", "marksheet", "report card"],
        action_label="Upload Marksheet",
        action_deep_link="/intake/upload",
    ),
    FAQArticle(
        article_id="FAQ-OCR-002",
        category=SupportTicketCategory.MARKS_ENTRY.value,
        title="Why does Quick Marks entry not show detailed topic mastery breakdown?",
        summary="Explanation of Gate 2 Zero-Hallucination integrity rule: aggregate marks never create fake topic mastery.",
        content=(
            "Studiqs SmartParent enforces strict academic integrity (Gate 2 Compliance):\n"
            "Quick Marks captures only total subject marks (e.g., Maths 45/50). Because individual questions and chapters were not specified, our system refuses to invent or 'hallucinate' topic strengths.\n"
            "To unlock question-level Bloom's mastery, chapter breakdowns, and gap analysis, upload the question paper or enter line-item question marks."
        ),
        tags=["quick marks", "topic mastery", "fake", "hallucination", "gate 2", "aggregate", "breakdown", "line item"],
        action_label="Try Interactive Marks Grid",
        action_deep_link="/intake/interactive-grid",
    ),

    # --- TOPIC MASTERY & DIAGNOSTIC GAPS ---
    FAQArticle(
        article_id="FAQ-TOPIC-001",
        category=SupportTicketCategory.TOPIC_INTELLIGENCE.value,
        title="How are Strong, Average, Weak, and Critical topic mastery levels determined?",
        summary="Explanation of the 4-tier pedagogical score bands and how critical gaps are flagged.",
        content=(
            "Topic mastery is evaluated mathematically based on questions attempted in that topic:\n"
            "• Band 1 (Strong): 80.0% to 100.0% — Topic is mastered; praise student momentum.\n"
            "• Band 2 (Average): 60.0% to 79.99% — Solid foundation with minor procedural slips.\n"
            "• Band 3 (Weak): 40.0% to 59.99% — Needs 2-week targeted homework review.\n"
            "• Band 4 (Critical): 0.0% to 39.99% — Conceptual blocker requiring immediate remedial drill or tutor intervention.\n"
            "Critical gaps appear on your Monthly Parent Pulse Watch Area."
        ),
        tags=["mastery", "bands", "strong", "weak", "critical", "gaps", "bloom", "percentage", "score"],
        action_label="View Topic Watchlist",
        action_deep_link="/analytics/topic-gaps",
    ),
    FAQArticle(
        article_id="FAQ-TOPIC-002",
        category=SupportTicketCategory.TOPIC_INTELLIGENCE.value,
        title="How can I recheck if my child has resolved a critical topic gap?",
        summary="Using the 10-Minute Micro-Diagnostic Recheck to test gap resolution.",
        content=(
            "Once your child practices the remedial drills:\n"
            "1. Open the 'Topic Gaps' watchlist in your child's profile.\n"
            "2. Tap 'Launch Gap Recheck' on the relevant topic.\n"
            "3. Your child takes a brief 10-minute 5-question micro-diagnostic.\n"
            "4. Scoring >= 70% automatically marks the topic gap as RESOLVED and sends a celebratory Milestone notification!"
        ),
        tags=["recheck", "gap recheck", "resolve", "micro diagnostic", "quiz", "test", "practice"],
        action_label="Go to Topic Gaps",
        action_deep_link="/analytics/topic-gaps",
    ),

    # --- PTM PACK & ACADEMIC HANDOFF ---
    FAQArticle(
        article_id="FAQ-PTM-001",
        category=SupportTicketCategory.GUIDANCE.value,
        title="How do I share the PTM Prep Pack with school teachers or tuition tutors?",
        summary="1-click WhatsApp share cards, teacher discussion talking points, and printable PDF briefs.",
        content=(
            "Before your Parent-Teacher Meeting (PTM):\n"
            "1. Open the 'Handoff' tab on your mobile dashboard.\n"
            "2. Select your audience: 'School Teacher' or 'Private Tutor'.\n"
            "3. Studiqs synthesizes a 'Praise First, Remediate Second' diagnostic brief.\n"
            "4. Tap 'Share via WhatsApp' to send a beautifully formatted summary card, or tap 'Export Printable PDF' to take a physical copy."
        ),
        tags=["ptm", "teacher", "tutor", "whatsapp", "share", "talking points", "brief", "handout"],
        action_label="Open PTM Brief",
        action_deep_link="/handoff/ptm",
    ),

    # --- EXPERT MARKETPLACE & DISPUTES ---
    FAQArticle(
        article_id="FAQ-EXP-001",
        category=SupportTicketCategory.BUG_REPORT.value,
        title="What is the 48-Hour SLA for Subject Expert handwritten evaluations?",
        summary="Guaranteed turnaround timelines, status updates, and automatic alerts for expert evaluations.",
        content=(
            "When you submit a handwritten answer script to a verified Subject Expert:\n"
            "• 48-Hour Turnaround SLA: The expert must submit digital annotations and line-item scoring within 48 continuous hours.\n"
            "• Progress Tracking: You receive real-time push alerts when the expert accepts the paper, begins grading, and completes review.\n"
            "• Breach Protection: If an expert fails to complete grading within 48 hours, support receives an automated escalation alert for reassignment or immediate refund."
        ),
        tags=["expert", "marketplace", "48h", "sla", "delay", "turnaround", "grading", "evaluation"],
        action_label="Track Active Cases",
        action_deep_link="/marketplace/cases",
    ),
    FAQArticle(
        article_id="FAQ-EXP-002",
        category=SupportTicketCategory.BILLING_REFUND.value,
        title="How does the 48-Hour Evaluation Dispute Window and Escrow Freeze work?",
        summary="Disputing unfair grading, unclear remarks, or wrong answer sheets to freeze payout.",
        content=(
            "When an expert submits completed evaluations, an automated 48-hour dispute window opens:\n"
            "• Escrow Hold: The expert's 80% payout is held in secure platform escrow for 48 hours.\n"
            "• Raising a Dispute: If you believe grading is unfair or remarks are unclear, tap 'Dispute Evaluation' on the case page or raise a 'CORRECTION_DISPUTE' ticket.\n"
            "• Instant Escrow Freeze: Payout disbursement is frozen immediately while an academic auditor reviews the submission.\n"
            "• Resolution: Within 24-48 hours, support either adjusts the scoring or reassigns the case for a complimentary second review."
        ),
        tags=["dispute", "escrow", "freeze", "correction", "unfair", "marks dispute", "expert review", "payout"],
        action_label="Open Dispute Case",
        action_deep_link="/marketplace/cases",
    ),

    # --- AI VOICE PRO ASSISTANT ---
    FAQArticle(
        article_id="FAQ-VOICE-001",
        category=SupportTicketCategory.AI_VOICE.value,
        title="How does the Studiqs Voice Assistant work and what are the query limits?",
        summary="Voice query quotas, language support, zero audio retention privacy, and supported questions.",
        content=(
            "The AI Voice Assistant is available on the Pro Plan:\n"
            "• Quota: 100 queries per billing month for instant hands-free queries.\n"
            "• Example Inquiries: 'How is Kavitha doing in Maths?', 'What are her top 2 weak topics in Science?', 'Summarize her PTM talking points.'\n"
            "• Zero Raw Audio Storage: Your voice queries are transcribed in real-time and raw audio recordings are never stored on platform servers, ensuring total family privacy."
        ),
        tags=["voice", "ai voice", "assistant", "queries", "quota", "privacy", "audio", "mic", "hands-free"],
        action_label="Try Voice Query",
        action_deep_link="/voice/assistant",
    ),
]


# =============================================================================
# 3. Production Self-Service FAQ Engine Implementation
# =============================================================================

class SelfServiceFAQEngine(BaseEngine):
    """
    Section 14 Self-Service FAQ & Knowledge Base Resolution Engine.
    Fast, deterministic keyword and tag matching algorithm to resolve
    parent questions instantly before support tickets are created.
    """

    def __init__(self, failure_threshold: int = 5):
        super().__init__(name="SelfServiceFAQEngine", failure_threshold=failure_threshold)
        self.articles = CURATED_FAQ_ARTICLES

    # -------------------------------------------------------------------------
    # BaseEngine Lifecycle Hooks
    # -------------------------------------------------------------------------

    def validate_input(self, input_data: Any) -> Dict[str, Any]:
        """Validates search query payload."""
        if not isinstance(input_data, dict):
            raise ValueError("Input to SelfServiceFAQEngine must be a dictionary")

        query = str(input_data.get("query", "")).strip()
        category = input_data.get("category")
        limit = int(input_data.get("limit", 5))

        return {
            "query": query,
            "category": str(category).strip() if category else None,
            "limit": max(1, min(limit, 20)),
        }

    def execute_core(self, validated_data: Dict[str, Any]) -> FAQSearchResponse:
        """Executes search and relevance ranking across knowledge base articles."""
        query = validated_data.get("query", "")
        category_filter = validated_data.get("category")
        limit = validated_data.get("limit", 5)

        if not query and not category_filter:
            # Return top default articles across all categories
            results = [
                FAQSearchResult(
                    article=art,
                    relevance_score=1.0,
                    matched_terms=["popular"]
                )
                for art in self.articles[:limit]
            ]
            return FAQSearchResponse(
                query="",
                total_found=len(results),
                results=results,
                suggested_ticket_category=None,
                fallback_message="Browsing top help topics. Type your question to search specific answers."
            )

        scored_results: List[FAQSearchResult] = []
        tokens = [t.lower() for t in re.findall(r"\b\w{3,}\b", query)]

        for art in self.articles:
            if category_filter and art.category.upper() != category_filter.upper():
                continue

            score = 0.0
            matched_terms = []

            # 1. Exact phrase in title (+50.0)
            if query and query.lower() in art.title.lower():
                score += 50.0
                matched_terms.append("exact_title")

            # 2. Token matches in title (+15.0 per match)
            for token in tokens:
                if token in art.title.lower():
                    score += 15.0
                    if token not in matched_terms:
                        matched_terms.append(token)

            # 3. Tag exact matches (+25.0 per tag match)
            for tag in art.tags:
                for token in tokens:
                    if token == tag.lower():
                        score += 25.0
                        if tag not in matched_terms:
                            matched_terms.append(tag)

            # 4. Token matches in summary / content (+5.0 per match)
            for token in tokens:
                if token in art.summary.lower() or token in art.content.lower():
                    score += 5.0
                    if token not in matched_terms:
                        matched_terms.append(token)

            # If searching by category without query, include all in category
            if not query and category_filter:
                score = 10.0
                matched_terms.append(f"category:{category_filter}")

            if score > 0.0:
                scored_results.append(
                    FAQSearchResult(
                        article=art,
                        relevance_score=round(score, 2),
                        matched_terms=matched_terms
                    )
                )

        # Sort descending by relevance score
        scored_results.sort(key=lambda x: x.relevance_score, reverse=True)
        top_results = scored_results[:limit]

        # Auto-detect suggested support category from query keywords
        suggested_cat = self._detect_suggested_category(query)

        fallback = None
        if not top_results:
            fallback = "No direct help articles found. Our support team is available 24/7. Would you like to raise a ticket?"

        return FAQSearchResponse(
            query=query,
            total_found=len(scored_results),
            results=top_results,
            suggested_ticket_category=suggested_cat,
            fallback_message=fallback
        )

    def fallback(self, error: Exception, input_data: Any) -> FAQSearchResponse:
        """Safe degraded fallback returning top popular help topics."""
        self.logger.warning("SelfServiceFAQEngine fallback invoked: %s", error)
        top_defaults = [
            FAQSearchResult(
                article=art,
                relevance_score=1.0,
                matched_terms=["fallback"]
            )
            for art in self.articles[:3]
        ]
        return FAQSearchResponse(
            query=str(input_data.get("query", "")) if isinstance(input_data, dict) else "",
            total_found=len(top_defaults),
            results=top_defaults,
            suggested_ticket_category=SupportTicketCategory.GUIDANCE.value,
            fallback_message="Self-service search temporarily degraded. Showing top common topics."
        )

    # -------------------------------------------------------------------------
    # Helper Heuristics
    # -------------------------------------------------------------------------

    @staticmethod
    def _detect_suggested_category(query: str) -> str:
        """Determines best ticket category based on intent keywords."""
        q = query.lower()
        if any(w in q for w in ["price", "cost", "invoice", "receipt", "gst", "payment", "refund", "charge", "tax", "razorpay"]):
            return SupportTicketCategory.BILLING_REFUND.value
        elif any(w in q for w in ["upload", "photo", "camera", "marksheet", "scan", "ocr", "report card"]):
            return SupportTicketCategory.MARKS_ENTRY.value
        elif any(w in q for w in ["dispute", "expert", "delay", "tutor", "grading", "escrow", "marks disputed"]):
            return SupportTicketCategory.BUG_REPORT.value
        elif any(w in q for w in ["voice", "audio", "mic", "assistant"]):
            return SupportTicketCategory.AI_VOICE.value
        elif any(w in q for w in ["topic", "mastery", "gap", "critical", "bloom"]):
            return SupportTicketCategory.TOPIC_INTELLIGENCE.value
        elif any(w in q for w in ["ptm", "teacher", "talking points", "whatsapp", "guidance"]):
            return SupportTicketCategory.GUIDANCE.value
        return SupportTicketCategory.GUIDANCE.value
