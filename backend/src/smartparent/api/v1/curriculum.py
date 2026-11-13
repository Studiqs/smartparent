"""
STUDIQS® SmartParent™ (v6.3 Complete) - Curriculum Taxonomy API Router
=============================================================================
Module: src.smartparent.api.v1.curriculum

Endpoints for querying the 8,034 Verified Topic Curriculum Knowledge Base.
Enforces strict Tamil language exclusion across Classes 1-12.
=============================================================================
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from src.smartparent.db.session import get_db
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.schemas.curriculum import (
    CurriculumNodeSchema,
    CurriculumSearchResponse,
    ChapterTreeItem,
    SubjectSyllabusResponse,
)

curriculum_router = APIRouter(prefix="/curriculum", tags=["Curriculum Taxonomy"])


@curriculum_router.get(
    "/nodes/{node_id}",
    response_model=CurriculumNodeSchema,
    summary="Get single curriculum topic node details",
)
def get_curriculum_node(
    node_id: str,
    db: Session = Depends(get_db),
):
    stmt = select(CurriculumNode).where(CurriculumNode.node_id == node_id)
    node = db.execute(stmt).scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Curriculum node '{node_id}' not found.",
        )
    return node


@curriculum_router.get(
    "/search",
    response_model=CurriculumSearchResponse,
    summary="Search topics across 8,034 verified nodes",
)
def search_curriculum(
    query: str = Query(..., min_length=2, max_length=150, description="Search keyword"),
    board: Optional[str] = Query(None, description="CBSE, TN State Board"),
    standard_class: Optional[str] = Query(None, description="Grade e.g. Class 10"),
    subject: Optional[str] = Query(None, description="Subject name"),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    conditions = [
        CurriculumNode.topic_name.ilike(f"%{query}%")
        | CurriculumNode.chapter_name.ilike(f"%{query}%")
    ]
    if board:
        conditions.append(CurriculumNode.board.ilike(board))
    if standard_class:
        conditions.append(CurriculumNode.standard_class.ilike(standard_class))
    if subject:
        conditions.append(CurriculumNode.subject.ilike(subject))

    stmt = select(CurriculumNode).where(and_(*conditions)).limit(limit)
    nodes = db.execute(stmt).scalars().all()

    return CurriculumSearchResponse(
        query=query,
        total_matches=len(nodes),
        nodes=[CurriculumNodeSchema.model_validate(n) for n in nodes],
    )


@curriculum_router.get(
    "/syllabus",
    response_model=SubjectSyllabusResponse,
    summary="Get structured chapter and topic breakdown for a subject",
)
def get_subject_syllabus(
    board: str = Query(..., description="CBSE or TN State Board"),
    standard_class: str = Query(..., description="Class 1 to Class 12"),
    subject: str = Query(..., description="Mathematics, Science, etc."),
    db: Session = Depends(get_db),
):
    stmt = (
        select(CurriculumNode)
        .where(
            and_(
                CurriculumNode.board.ilike(board),
                CurriculumNode.standard_class.ilike(standard_class),
                CurriculumNode.subject.ilike(subject),
            )
        )
        .order_by(CurriculumNode.chapter_name, CurriculumNode.topic_name)
    )
    nodes = db.execute(stmt).scalars().all()

    chapter_map = {}
    for node in nodes:
        if node.chapter_name not in chapter_map:
            chapter_map[node.chapter_name] = []
        chapter_map[node.chapter_name].append(node.topic_name)

    chapter_items = [
        ChapterTreeItem(
            chapter_name=ch,
            topic_count=len(topics),
            topics=topics,
        )
        for ch, topics in chapter_map.items()
    ]

    return SubjectSyllabusResponse(
        board=board,
        standard_class=standard_class,
        subject=subject,
        total_chapters=len(chapter_items),
        total_topics=len(nodes),
        chapters=chapter_items,
    )

