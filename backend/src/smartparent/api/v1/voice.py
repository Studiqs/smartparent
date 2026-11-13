"""
STUDIQS® SmartParent™ - Ask Studiqs Multimodal Voice API Router
=============================================================================
Module: src.smartparent.api.v1.voice

Endpoints:
  - POST /api/v1/voice/query: Natural language typed diagnostic query.
  - POST /api/v1/voice/audio-query: Spoken audio query (in-memory STT).
  - GET  /api/v1/voice/tokens: Current Diagnostic Token balance & quota.
  - GET  /api/v1/voice/pillars: Public metadata discovery for 6 diagnostic pillars.
  - GET  /api/v1/voice/stream: Server-Sent Events (SSE) streaming delivery.
=============================================================================
"""

import io
import json
import uuid
from typing import Optional, List
from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse

from src.smartparent.api.deps import get_current_subscriber_id, get_db
from sqlalchemy.orm import Session
from src.smartparent.services.voice_service import VoiceService
from src.smartparent.schemas.voice import (
    VoiceTextQueryRequest,
    VoiceQueryResponse,
    VoiceTokenBalanceResponse,
    VoicePillarsResponse,
)

router = APIRouter(prefix="/voice", tags=["Ask Studiqs Multimodal Voice Assistant"])
_voice_service = VoiceService()


def get_voice_service(db: Optional[Session] = Depends(get_db)) -> VoiceService:
    """FastAPI Dependency Injection provider for VoiceService."""
    if db is not None:
        return VoiceService(db_session=db)
    return _voice_service


@router.post(
    "/query",
    response_model=VoiceQueryResponse,
    summary="Submit a natural language typed diagnostic query",
)
def query_text(
    request: VoiceTextQueryRequest,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    x_plan_tier: Optional[str] = Header("PRO", alias="X-Plan-Tier"),
    db: Optional[Session] = Depends(get_db),
    voice_service: VoiceService = Depends(get_voice_service),
):
    """
    Processes an interactive diagnostic text question, executes NLU and 5D NLG,
    and returns a dual-modal payload with Diagnostic Token metering.
    """
    authorized_children = None
    if db is not None:
        try:
            from sqlalchemy import select
            from src.smartparent.db.models.auth import Child
            stmt = select(Child).where(Child.subscriber_id == subscriber_id, Child.is_active == True)
            db_children = db.execute(stmt).scalars().all()
            if db_children:
                authorized_children = [c.student_name for c in db_children]
                if request.child_id:
                    owned_ids = {str(c.child_id) for c in db_children}
                    if str(request.child_id) not in owned_ids:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Access denied: Selected child profile does not belong to this family account.",
                        )
        except HTTPException:
            raise
        except Exception:
            pass

    res = voice_service.process_text_query(
        parent_id=str(subscriber_id),
        plan_tier=x_plan_tier or "PRO",
        request=request,
        authorized_children=authorized_children,
    )
    if res.get("http_status") and res["http_status"] in (403, 413, 429):
        raise HTTPException(
            status_code=res["http_status"],
            detail=res.get("message", "Quota or entitlement constraint."),
        )
    return res


@router.post(
    "/audio-query",
    response_model=VoiceQueryResponse,
    summary="Submit a spoken audio diagnostic query (in-memory STT)",
)
async def query_audio(
    file: UploadFile = File(...),
    child_id: Optional[str] = Header(None, alias="X-Child-Id"),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    x_plan_tier: Optional[str] = Header("PRO", alias="X-Plan-Tier"),
    db: Optional[Session] = Depends(get_db),
    voice_service: VoiceService = Depends(get_voice_service),
):
    """
    Decodes speech in volatile RAM via containerized faster-whisper (int8),
    scrubs audio immediately from memory (Zero Disk Retention), and executes
    the Ask Studiqs RAG pipeline.
    """
    authorized_children = None
    if db is not None:
        try:
            from sqlalchemy import select
            from src.smartparent.db.models.auth import Child
            stmt = select(Child).where(Child.subscriber_id == subscriber_id, Child.is_active == True)
            db_children = db.execute(stmt).scalars().all()
            if db_children:
                authorized_children = [c.student_name for c in db_children]
                if child_id:
                    owned_ids = {str(c.child_id) for c in db_children}
                    if str(child_id) not in owned_ids:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Access denied: Selected child profile does not belong to this family account.",
                        )
        except HTTPException:
            raise
        except Exception:
            pass

    content = await file.read()
    audio_stream = io.BytesIO(content)

    res = voice_service.process_audio_query(
        parent_id=str(subscriber_id),
        plan_tier=x_plan_tier or "PRO",
        audio_stream=audio_stream,
        child_id=child_id,
        authorized_children=authorized_children,
    )
    if res.get("http_status") and res["http_status"] in (403, 413, 429):
        raise HTTPException(
            status_code=res["http_status"],
            detail=res.get("message", "Voice quota or entitlement constraint."),
        )
    return res


@router.get(
    "/tokens",
    response_model=VoiceTokenBalanceResponse,
    summary="Check real-time Diagnostic Token balance and quota usage",
)
def get_token_balance(
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    x_plan_tier: Optional[str] = Header("PRO", alias="X-Plan-Tier"),
):
    """
    Returns the subscriber's monthly token limit, used tokens, remaining balance,
    and progressive milestone thresholds.
    """
    return _voice_service.get_token_balance(
        parent_id=str(subscriber_id),
        plan_tier=x_plan_tier or "PRO",
    )


@router.get(
    "/pillars",
    response_model=VoicePillarsResponse,
    summary="List the 6 Diagnostic Pillars and example queries",
)
def get_pillars():
    """
    Returns the 6 architectural Diagnostic Pillars for client-side search chips
    and voice suggestion prompts.
    """
    return _voice_service.get_pillars_metadata()


@router.get(
    "/stream",
    summary="Server-Sent Events (SSE) live streaming query endpoint",
)
def stream_query(
    q: str,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    x_plan_tier: Optional[str] = Header("PRO", alias="X-Plan-Tier"),
    voice_service: VoiceService = Depends(get_voice_service),
):
    """
    Streams the pre-verbalized spoken narrative sentence-by-sentence via SSE
    to enable instant client playback under 250ms.
    """
    def event_generator():
        res = voice_service.process_text_query(
            parent_id=str(subscriber_id),
            plan_tier=x_plan_tier or "PRO",
            request=VoiceTextQueryRequest(query_text=q),
        )
        if res.get("status") == "BLOCKED":
            yield f"event: error\ndata: {json.dumps(res)}\n\n"
            return

        spoken = res.get("dual_modal_delivery", {}).get("spoken_narrative", "")
        # Stream in sentence chunks
        chunks = [c.strip() for c in spoken.split(".") if c.strip()]
        for chunk in chunks:
            yield f"event: spoken_chunk\ndata: {json.dumps({'text': chunk + '.'})}\n\n"

        yield f"event: visual_card\ndata: {json.dumps(res.get('dual_modal_delivery', {}).get('visual_card', {}))}\n\n"
        yield f"event: done\ndata: {json.dumps({'token_accounting': res.get('token_accounting')})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
