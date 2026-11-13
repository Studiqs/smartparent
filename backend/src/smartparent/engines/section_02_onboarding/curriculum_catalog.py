"""
STUDIQS® SmartParent™ (v6.2 Complete) - Curriculum Catalog & Auto-Suggestion Engine
=============================================================================
Working Specification v6.0 / v6.1 Section 2:
Auto-suggests official syllabus subjects based on Class and Board.
Parent/Student confirms or edits during ultra-simple onboarding.
=============================================================================
"""

import re
from typing import Dict, List, Optional, Tuple


class CurriculumCatalogEngine:
    """
    Authoritative curriculum knowledge repository for Indian school boards:
    CBSE, ICSE, and Tamil Nadu State Board (Classes 1 to 12).
    """

    SUPPORTED_BOARDS = ["CBSE", "ICSE", "TN State Board"]
    
    SUPPORTED_CLASSES = [f"Class {i}" for i in range(1, 13)]

    # Standard Subject Catalogs per Board & Grade
    CBSE_SUBJECTS = {
        "PRIMARY": ["Mathematics", "Environmental Studies (EVS)", "English", "Hindi"],
        "MIDDLE": ["Mathematics", "Science", "Social Science", "English", "Hindi"],
        "SECONDARY": ["Mathematics", "Science", "Social Science", "English Language & Literature", "Hindi Course-A"],
        "SENIOR_SECONDARY": {
            "BIO_MATHS": ["Physics", "Chemistry", "Biology", "Mathematics", "English Core"],
            "CS_MATHS": ["Physics", "Chemistry", "Computer Science", "Mathematics", "English Core"],
            "COMMERCE": ["Accountancy", "Business Studies", "Economics", "Applied Mathematics", "English Core"],
            "HUMANITIES": ["History", "Political Science", "Economics", "Psychology", "English Core"],
        }
    }

    ICSE_SUBJECTS = {
        "PRIMARY": ["Mathematics", "General Science", "Social Studies", "English Language", "English Literature", "Second Language"],
        "MIDDLE": ["Mathematics", "Physics", "Chemistry", "Biology", "History & Civics", "Geography", "English Language", "English Literature", "Second Language"],
        "SECONDARY": ["English Language", "English Literature", "History & Civics", "Geography", "Mathematics", "Physics", "Chemistry", "Biology", "Second Language"],
        "SENIOR_SECONDARY": {
            "BIO_MATHS": ["Physics", "Chemistry", "Biology", "Mathematics", "English"],
            "CS_MATHS": ["Physics", "Chemistry", "Computer Science", "Mathematics", "English"],
            "COMMERCE": ["Accounts", "Commerce", "Economics", "Business Studies", "English"],
            "HUMANITIES": ["History", "Political Science", "Geography", "Economics", "English"],
        }
    }

    TN_STATE_BOARD_SUBJECTS = {
        "PRIMARY": ["Tamil", "English", "Mathematics", "Science", "Social Science"],
        "MIDDLE": ["Tamil", "English", "Mathematics", "Science", "Social Science"],
        "SECONDARY": ["Tamil", "English", "Mathematics", "Science", "Social Science"],
        "SENIOR_SECONDARY": {
            "BIO_MATHS": ["Tamil", "English", "Physics", "Chemistry", "Biology", "Mathematics"],
            "CS_MATHS": ["Tamil", "English", "Physics", "Chemistry", "Computer Science", "Mathematics"],
            "COMMERCE": ["Tamil", "English", "Accountancy", "Commerce", "Economics", "Business Mathematics"],
            "HUMANITIES": ["Tamil", "English", "History", "Geography", "Economics", "Political Science"],
        }
    }

    @classmethod
    def normalize_board(cls, raw_board: str) -> str:
        """Normalizes input board string to canonical board name."""
        b = raw_board.strip().lower()
        if "cbse" in b or "central" in b:
            return "CBSE"
        elif "icse" in b or "cisce" in b or "isc" in b:
            return "ICSE"
        elif any(k in b for k in ["tn", "tamil", "state", "samacheer", "matriculation"]):
            return "TN State Board"
        
        # Exact match check
        for supported in cls.SUPPORTED_BOARDS:
            if supported.lower() == b:
                return supported
        raise ValueError(
            f"Unsupported curriculum board '{raw_board}'. Supported boards: {', '.join(cls.SUPPORTED_BOARDS)}"
        )

    @classmethod
    def normalize_class(cls, raw_class: str) -> str:
        """Normalizes input class/grade to canonical 'Class X' string."""
        c = raw_class.strip().lower()
        match = re.search(r'\b(1[0-2]|[1-9])(?:st|nd|rd|th)?\b', c)
        if match:
            num = match.group(1)
            return f"Class {num}"
        
        # Check Roman numerals
        roman_map = {
            "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6,
            "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12
        }
        for roman, val in roman_map.items():
            if re.search(rf'\b{roman}\b', c):
                return f"Class {val}"

        raise ValueError(
            f"Invalid class/grade '{raw_class}'. Supported: 'Class 1' to 'Class 12'."
        )

    @classmethod
    def get_suggested_subjects(
        cls,
        board: str,
        standard_class: str,
        stream_id: Optional[str] = None
    ) -> List[str]:
        """
        Auto-suggests official syllabus subjects based on class and board.
        Preselects subjects for instant 1-click onboarding confirmation.
        """
        canonical_board = cls.normalize_board(board)
        canonical_class = cls.normalize_class(standard_class)
        class_num = int(canonical_class.split()[1])

        # Select board catalog
        if canonical_board == "CBSE":
            catalog = cls.CBSE_SUBJECTS
        elif canonical_board == "ICSE":
            catalog = cls.ICSE_SUBJECTS
        else:
            catalog = cls.TN_STATE_BOARD_SUBJECTS

        # Senior Secondary (Class 11 & 12)
        if class_num in [11, 12]:
            streams = catalog["SENIOR_SECONDARY"]
            stream_key = (stream_id or "BIO_MATHS").upper()
            if stream_key not in streams:
                stream_key = "BIO_MATHS"
            return list(streams[stream_key])

        # Secondary (Class 9 & 10)
        elif class_num in [9, 10]:
            return list(catalog["SECONDARY"])

        # Middle School (Class 6 to 8)
        elif class_num in [6, 7, 8]:
            return list(catalog["MIDDLE"])

        # Primary School (Class 1 to 5)
        else:
            return list(catalog["PRIMARY"])
