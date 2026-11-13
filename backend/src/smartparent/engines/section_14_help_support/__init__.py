"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - Section 14 Help Centre & Support Engines
=============================================================================
Section 14: Help Centre, Ticketing and Support Operating Models
Section 27: 48-Hour Hard SLA Support Operating Model with Continuous Escalation

Exports:
  - SupportTicketEngine: State machine transitions, sequential TKT numbers, priority triage, dispute escrow freeze
  - SLAEscalationEngine: 48-hour hard SLA continuous countdown, 12h/24h/36h/48h milestone escalation
  - SelfServiceFAQEngine: Authoritative searchable knowledge base for instant query resolution
=============================================================================
"""

from src.smartparent.engines.section_14_help_support.support_ticket_engine import (
    SupportTicketEngine,
    TicketCreationInputSchema,
    TicketCreationResultSchema,
    TicketTransitionInputSchema,
    TicketTransitionResultSchema,
)
from src.smartparent.engines.section_14_help_support.sla_escalation_engine import (
    SLAEscalationEngine,
    TicketSLATelemetry,
    SLABatchAuditSummary,
)
from src.smartparent.engines.section_14_help_support.self_service_faq_engine import (
    SelfServiceFAQEngine,
    FAQArticle,
    FAQSearchResult,
    FAQSearchResponse,
)

__all__ = [
    "SupportTicketEngine",
    "TicketCreationInputSchema",
    "TicketCreationResultSchema",
    "TicketTransitionInputSchema",
    "TicketTransitionResultSchema",
    "SLAEscalationEngine",
    "TicketSLATelemetry",
    "SLABatchAuditSummary",
    "SelfServiceFAQEngine",
    "FAQArticle",
    "FAQSearchResult",
    "FAQSearchResponse",
]
