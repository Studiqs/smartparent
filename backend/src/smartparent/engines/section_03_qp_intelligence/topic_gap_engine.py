import pandas as pd
import json
from pathlib import Path

def _find_workspace_root() -> Path:
    current = Path(__file__).resolve()
    for p in current.parents:
        if (p / "models").exists() and (p / "data").exists():
            return p
    return current.parents[3]

class TopicGapEngine:
    """
    Task 6: Production-Grade Topic Gap Engine
    Input: DataFrame from Task 5 (with `mastery_level` column)
    Output: Groups topics into Strong, Average, Weak, Critical lists.
    """
    def __init__(self):
        print("[Task 6] Initializing Topic Gap Engine...")

    def analyze(self, mastery_df: pd.DataFrame) -> dict:
        """
        Extracts lists of topics based on their mastery level.
        """
        strong = []
        average = []
        weak = []
        critical = []

        if not mastery_df.empty:
            for _, row in mastery_df.iterrows():
                topic = row["topic"]
                level = row["mastery_level"]
                
                if level == "Strong":
                    strong.append(topic)
                elif level == "Average":
                    average.append(topic)
                elif level == "Weak":
                    weak.append(topic)
                elif level == "Critical":
                    critical.append(topic)

        return {
            "strong_topics": strong,
            "average_topics": average,
            "weak_topics": weak,
            "critical_topics": critical,
            "topic_count": len(mastery_df),
            "gap_summary": {
                "strong_count": len(strong),
                "average_count": len(average),
                "weak_count": len(weak),
                "critical_count": len(critical)
            }
        }

# ------------------ CLI / Demo ------------------
if __name__ == "__main__":
    import os
    import argparse
    parser = argparse.ArgumentParser(description="STUDIQS Topic Gap Engine")
    parser.add_argument("--input", "-i", type=str, help="Path to external JSON or CSV file containing topics, score_percent, and mastery_level")
    args = parser.parse_args()

    print("=" * 60)
    print("STUDIQS TOPIC GAP ENGINE")
    print("=" * 60)

    engine = TopicGapEngine()
    
    if args.input and os.path.exists(args.input):
        print(f"[Info] Loading external data from {args.input}...")
        if args.input.endswith(".csv"):
            df = pd.read_csv(args.input)
        else:
            df = pd.read_json(args.input)
    else:
        print("[Info] No external input provided. Using dummy data...")
        df = pd.DataFrame([
            {"topic": "Algebra", "score_percent": 40.0, "mastery_level": "Weak"},
            {"topic": "Geometry", "score_percent": 100.0, "mastery_level": "Strong"},
            {"topic": "Trigonometry", "score_percent": 20.0, "mastery_level": "Critical"},
            {"topic": "Statistics", "score_percent": 75.0, "mastery_level": "Average"},
        ])
    
    result = engine.analyze(df)
    print(json.dumps(result, indent=2))

    import os
    from pathlib import Path
    
    try:
        project_root = _find_workspace_root()
        out_dir = project_root / "outputs" / "Task_Topic_Gap"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "topic_gap_engine_output.json"
        
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"\n[Success] Output saved to {out_path}")
    except Exception as e:
        print(f"\n[Error] Could not save output: {e}")
