"""
STUDIQS® SmartParent™ (v6.3 Complete) - Curriculum Taxonomy Schemas
=============================================================================
Module: src.smartparent.schemas.curriculum

Pydantic v2 schemas for the 8,034 Verified Topic Curriculum Catalog.
Enforces strict Tamil language exclusion across Classes 1-12.
=============================================================================
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CurriculumNodeSchema(BaseModel):
    """Atomic curriculum topic node."""
    model_config = ConfigDict(from_attributes=True)

    node_id: str = Field(..., description="Unique alphanumeric identifier (e.g. CBSE_G10_MAT_CH04_QUAD_EQ)")
    board: str = Field(..., description="Academic Board (CBSE, TN State Board)")
    standard_class: str = Field(..., description="Grade/Standard Class (Class 1 to Class 12)")
    stream_id: Optional[str] = Field(None, description="Stream for Classes 11-12 (BIO_MATHS, CS_MATHS, etc.)")
    subject: str = Field(..., description="Subject name (Mathematics, Science, Physics, etc.)")
    subject_group: str = Field(default="CORE", description="Subject classification group")
    subdivision_id: Optional[str] = Field(None, description="Subdivision (e.g. PHYSICS, CHEMISTRY, BIOLOGY)")
    chapter_name: str = Field(..., description="Chapter title")
    topic_name: str = Field(..., description="Granular topic title")
    semantic_keywords: List[str] = Field(default_factory=list, description="Keywords for hybrid retrieval")


class CurriculumSearchRequest(BaseModel):
    """Search request against curriculum repository."""
    query: str = Field(..., min_length=2, max_length=200, description="Search term or topic name")
    board: Optional[str] = Field(None, description="Optional board filter")
    standard_class: Optional[str] = Field(None, description="Optional grade filter (e.g. Class 10)")
    subject: Optional[str] = Field(None, description="Optional subject filter")
    limit: int = Field(default=20, ge=1, le=100, description="Max results returned")


class CurriculumSearchResponse(BaseModel):
    """Response containing matched curriculum taxonomy nodes."""
    query: str
    total_matches: int
    nodes: List[CurriculumNodeSchema]


class ChapterTreeItem(BaseModel):
    """Chapter structure containing its associated topic names."""
    chapter_name: str
    topic_count: int
    topics: List[str]


class SubjectSyllabusResponse(BaseModel):
    """Full hierarchical syllabus outline for a subject and grade."""
    board: str
    standard_class: str
    subject: str
    total_chapters: int
    total_topics: int
    chapters: List[ChapterTreeItem]

