import os
import pandas as pd
from typing import List, Dict, Any

class MarksEntryEngine:
    def __init__(self):
        pass

    def generate_grid(self, mapped_questions: List[Dict[str, Any]], output_path: str) -> str:
        """
        Generates an Excel grid for the teacher to enter marks.
        """
        data = []
        for q in mapped_questions:
            # Check for standard keys, fallback to defaults if missing
            q_no = q.get("question_no") or q.get("question_number")
            text = q.get("question_text") or q.get("question")
            topic = q.get("topic") or "Unknown Topic"
            max_marks = q.get("max_marks") or q.get("marks") or 5
            
            data.append({
                "Q.No": q_no,
                "Question": text,
                "Topic": topic,
                "Max Marks": max_marks,
                "Marks Scored": ""  # Blank for teacher to fill
            })
            
        df = pd.DataFrame(data)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        df.to_excel(output_path, index=False)
        print(f"[MarksEntryEngine] Generated Marks Entry Grid at {output_path}")
        return output_path

    def read_grid(self, file_path: str, mapped_questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Reads the Excel grid filled by the teacher and updates the mapped_questions.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Marks entry file not found at {file_path}")
            
        df = pd.read_excel(file_path)
        
        # Create a lookup for marks based on Q.No
        # Ensure we handle Q.No as string for safe comparison
        marks_dict = {}
        for _, row in df.iterrows():
            q_no = str(row.get("Q.No", "")).strip()
            marks_scored = row.get("Marks Scored")
            if pd.isna(marks_scored):
                marks_scored = 0  # Default to 0 if teacher left it blank
            marks_dict[q_no] = float(marks_scored)
            
        scored_questions = []
        for q in mapped_questions:
            # We copy the dictionary to not mutate the original if not desired
            q_copy = q.copy()
            q_no = str(q_copy.get("question_no") or q_copy.get("question_number")).strip()
            q_copy["marks_scored"] = marks_dict.get(q_no, 0)
            
            # Ensure max_marks is present
            if "max_marks" not in q_copy:
                q_copy["max_marks"] = q_copy.get("marks", 5)
                
            scored_questions.append(q_copy)
            
        print(f"[MarksEntryEngine] Successfully read marks from {file_path}")
        return scored_questions
