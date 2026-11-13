import os
import pandas as pd
from typing import Dict, List, Any, Optional
from pathlib import Path

def _find_workspace_root() -> Path:
    current = Path(__file__).resolve()
    for p in current.parents:
        if (p / "models").exists() and (p / "data").exists():
            return p
    return current.parents[3]

class RecommendationEngine:
    def __init__(self, library_path: Optional[str] = None):
        if library_path is None:
            default_path = _find_workspace_root() / "data" / "inputs" / "recommendation_library.xlsx"
            library_path = str(default_path)
            
        if not os.path.exists(library_path):
            print(f"[RecommendationEngine] Warning: Library not found at {library_path}. Using fallback.")
            self.df = pd.DataFrame(columns=["category", "subcategory", "stakeholder", "priority", "recommendation"])
        else:
            self.library_path = library_path
            self.df = pd.read_excel(library_path)
        
        # Standardize columns to handle case-insensitivity
        self.df.columns = [str(c).strip().lower() for c in self.df.columns]

    def get_topic_recommendations(self, topic: str, mastery_level: str, priority: str, subject: str = "Science") -> Dict[str, List[str]]:
        """
        Looks up the recommendation library for the given topic, mastery level, priority, and subject.
        Implements hierarchical fallback matching for each stakeholder:
          1. Topic-level match
          2. Subject-level match
          3. Stakeholder-level match
          4. Default fallback
        """
        recommendations = {}
        
        stakeholders = ["student", "parent", "teacher", "management"]
        
        topic_lower = topic.lower()
        priority_lower = priority.lower()
        subject_lower = subject.lower()
        
        # Standardize subject name to match spreadsheet
        subject_map = {
            'science': 'Science',
            'mathematics': 'Mathematics',
            'maths': 'Mathematics',
            'math': 'Mathematics',
            'physics': 'Physics',
            'chemistry': 'Chemistry',
            'biology': 'Biology'
        }
        subject_std = subject_map.get(subject_lower, subject).lower()
        
        for sh in stakeholders:
            recs = []
            
            # --- 1. Topic-level match ---
            # Try Category='Topic' and Subcategory=topic and Stakeholder=sh and Priority=priority
            mask = (
                (self.df['category'].str.lower() == 'topic') &
                (self.df['subcategory'].str.lower() == topic_lower) &
                (self.df['stakeholder'].str.lower().str.contains(sh)) &
                (self.df['priority'].str.lower() == priority_lower)
            )
            recs = self.df[mask]['recommendation'].dropna().tolist()
            
            # Try without priority filter
            if not recs:
                mask = (
                    (self.df['category'].str.lower() == 'topic') &
                    (self.df['subcategory'].str.lower() == topic_lower) &
                    (self.df['stakeholder'].str.lower().str.contains(sh))
                )
                recs = self.df[mask]['recommendation'].dropna().tolist()
                
            # --- 2. Subject-level match ---
            if not recs:
                mask = (
                    (self.df['category'].str.lower() == 'subject') &
                    (self.df['subcategory'].str.lower() == subject_std) &
                    (self.df['stakeholder'].str.lower().str.contains(sh)) &
                    (self.df['priority'].str.lower() == priority_lower)
                )
                recs = self.df[mask]['recommendation'].dropna().tolist()
                
                if not recs:
                    mask = (
                        (self.df['category'].str.lower() == 'subject') &
                        (self.df['subcategory'].str.lower() == subject_std) &
                        (self.df['stakeholder'].str.lower().str.contains(sh))
                    )
                    recs = self.df[mask]['recommendation'].dropna().tolist()
                    
            # --- 3. Stakeholder-level match ---
            if not recs:
                # management mapping in sheet can be 'admin' or 'management'
                sh_val = 'admin' if sh == 'management' else sh
                mask = (
                    (self.df['category'].str.lower() == 'stakeholder') &
                    (self.df['subcategory'].str.lower().str.contains(sh_val)) &
                    (self.df['stakeholder'].str.lower().str.contains(sh_val)) &
                    (self.df['priority'].str.lower() == priority_lower)
                )
                recs = self.df[mask]['recommendation'].dropna().tolist()
                
                if not recs:
                    mask = (
                        (self.df['category'].str.lower() == 'stakeholder') &
                        (self.df['subcategory'].str.lower().str.contains(sh_val)) &
                        (self.df['stakeholder'].str.lower().str.contains(sh_val))
                    )
                    recs = self.df[mask]['recommendation'].dropna().tolist()
            
            # --- 4. Default fallback ---
            if not recs:
                if sh == "student":
                    recs = [f"Focus on improving {topic} concepts."]
                elif sh == "parent":
                    recs = [f"Encourage regular practice in {topic}."]
                elif sh == "teacher":
                    recs = [f"Provide remedial support for {topic}."]
                elif sh == "management":
                    recs = [f"Monitor class performance in {topic}."]
                    
            recommendations[sh] = [str(r).strip() for r in list(dict.fromkeys(recs))]
            
        return recommendations
