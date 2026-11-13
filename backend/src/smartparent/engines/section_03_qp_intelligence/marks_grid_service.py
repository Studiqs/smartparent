import os
import pandas as pd
from typing import List, Dict, Any, Optional
from pathlib import Path
from src.smartparent.engines.marks_entry_engine import MarksEntryEngine

class MarksGridService(MarksEntryEngine):
    """
    MarksGridService: Service & engine wrapper for student exam marks entry grid.
    Supports generating blank/pre-filled Excel templates and ingesting entered marks.
    """
    def __init__(self):
        super().__init__()

    def create_blank_grid(self, mapped_questions: List[Dict[str, Any]], output_path: str) -> str:
        """Alias for generate_grid for clarity in service layer."""
        return self.generate_grid(mapped_questions, output_path)

    def ingest_grid(self, file_path: str, mapped_questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Alias for read_grid for clarity in service layer."""
        return self.read_grid(file_path, mapped_questions)
