import pandas as pd
import os
import random
from pathlib import Path

def _find_workspace_root() -> Path:
    current = Path(__file__).resolve()
    for p in current.parents:
        if (p / "models").exists() and (p / "data").exists():
            return p
    return current.parents[3]

class TopicScoringEngine:
    """
    Task 4: Production-Grade Topic Scoring Engine
    Aggregates simulated/real marks by clean_topic to calculate percentage scores.
    """
    def __init__(self):
        print("[Task 4] Initializing Topic Scoring Engine...")

    def simulate_marks(self, mapped_questions: list) -> list:
        """
        Since we don't have real student answer sheets yet, we simulate
        a student taking the test. Randomizes marks_scored between 0 and marks.
        """
        simulated = []
        for q in mapped_questions:
            max_marks = q.get("max_marks", 1)
            # Make the simulation realistic (mostly scoring > 0)
            marks_scored = random.randint(0, max_marks)
            
            sim_q = dict(q)
            sim_q["marks_scored"] = marks_scored
            simulated.append(sim_q)
            
        return simulated

    def load_marks_from_excel(self, excel_path: str) -> list:
        """
        Loads teacher-entered marks from an Excel file template.
        Expected columns: question_no, clean_topic, marks, marks_scored
        """
        df = pd.read_excel(excel_path)
        # Handle empty/NaN marks_scored by filling with 0
        if "marks_scored" in df.columns:
            df["marks_scored"] = df["marks_scored"].fillna(0).astype(int)
        else:
            df["marks_scored"] = 0
            
        return df.to_dict(orient="records")

    def calculate_topic_scores(self, scored_questions: list) -> pd.DataFrame:
        """
        Takes the mapped questions with 'marks_scored' and groups them by 'clean_topic'.
        """
        if not scored_questions:
            return pd.DataFrame()
            
        df = pd.DataFrame(scored_questions)
        
        # Ensure required columns exist
        if "clean_topic" not in df.columns:
            df["clean_topic"] = df.get("topic", "Unknown Topic")
            
        # Group by topic
        topic_scores = (
            df.groupby("clean_topic", as_index=False)
            .agg(
                total_max_marks=("max_marks", "sum"),
                total_scored_marks=("marks_scored", "sum"),
                question_count=("question_no", "count")
            )
        )

        topic_scores["score_percent"] = round(
            (topic_scores["total_scored_marks"] / topic_scores["total_max_marks"]) * 100, 2
        )

        # Reorder columns
        topic_scores = topic_scores[[
            "clean_topic", "question_count", "total_max_marks", 
            "total_scored_marks", "score_percent"
        ]]
        
        # rename clean_topic to topic for downstream engines
        topic_scores = topic_scores.rename(columns={"clean_topic": "topic"})

        return topic_scores

# ------------------ CLI / Standalone Demo ------------------
if __name__ == "__main__":
    import argparse
    import os
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Studiqs Topic Scoring Engine")
    parser.add_argument("--excel", type=str, help="Path to excel file with student marks")
    args = parser.parse_args()

    print("=" * 60)
    print("STUDIQS TOPIC SCORING ENGINE (Task 4)")
    print("=" * 60)

    project_root = _find_workspace_root()
    
    excel_path = args.excel
    if not excel_path:
        excel_path = project_root / "data" / "inputs" / "sample_student_marks.xlsx"
        print(f"No Excel path provided, defaulting to: {excel_path}")
        
    if not os.path.exists(excel_path):
        print(f"Error: Could not find excel file at {excel_path}")
        exit(1)

    engine = TopicScoringEngine()
    
    # Load from excel instead of hardcoded simulation
    scored_questions = engine.load_marks_from_excel(str(excel_path))
    
    # Ensure 'max_marks' exists for calculation if 'marks' is provided instead
    for q in scored_questions:
        if "max_marks" not in q and "marks" in q:
            q["max_marks"] = q["marks"]

    result = engine.calculate_topic_scores(scored_questions)
    
    print("\nStudent Marks (from Excel):")
    print(pd.DataFrame(scored_questions)[["question_no", "clean_topic", "max_marks", "marks_scored"]].to_string(index=False))

    print("\nOutput Topic Scores:")
    print(result.to_string(index=False))

    try:
        out_dir = project_root / "outputs" / "standalone"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "topic_scoring_engine_output.json"
        
        result.to_json(out_path, orient="records", indent=2)
        print(f"\n[Success] Output saved to {out_path}")
    except Exception as e:
        print(f"\n[Error] Could not save output: {e}")
