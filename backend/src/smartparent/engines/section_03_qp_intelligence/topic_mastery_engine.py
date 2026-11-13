import pandas as pd
import json
import os
from pathlib import Path

def _find_workspace_root() -> Path:
    current = Path(__file__).resolve()
    for p in current.parents:
        if (p / "models").exists() and (p / "data").exists():
            return p
    return current.parents[3]

class TopicMasteryEngine:
    """
    Task 5: Production-Grade Topic Mastery Engine
    Input: DataFrame or list of dicts with `topic` and `score_percent`.
    Output: Assigns mastery level (Strong, Average, Weak, Critical).
    """
    def __init__(self, rules=None):
        print("[Task 5] Initializing Topic Mastery Engine...")
        if rules is not None:
            self.rules = rules
        else:
            self.rules = []
            try:
                project_root = _find_workspace_root()
                rules_path = project_root / "data" / "inputs" / "test_mastery.xlsx"
                
                if rules_path.exists():
                    df = pd.read_excel(rules_path)
                    for _, row in df.iterrows():
                        self.rules.append({
                            "min": float(row["Score_Range_Min"]),
                            # Adjust max for exclusive boundary if needed, here we use precise max
                            "max": float(row["Score_Range_Max"]) + 0.99 if float(row["Score_Range_Max"]) < 100 else 100.0,
                            "level": str(row["Level"])
                        })
                    print(f"Loaded {len(self.rules)} mastery rules from {rules_path}")
            except Exception as e:
                print(f"Failed to load rules from Excel: {e}")
                
            if not self.rules:
                print("Using default hardcoded rules.")
                self.rules = [
                    {"min": 80, "max": 100, "level": "Strong"},
                    {"min": 60, "max": 79.99, "level": "Average"},
                    {"min": 40, "max": 59.99, "level": "Weak"},
                    {"min": 0, "max": 39.99, "level": "Critical"},
                ]

    def get_mastery(self, score):
        """Return mastery level for a given score (0-100)."""
        score = float(score)
        for rule in self.rules:
            if rule["min"] <= score <= rule["max"]:
                return rule["level"]
        return "Unknown"

    def evaluate(self, scores_df: pd.DataFrame) -> pd.DataFrame:
        """
        Takes the DataFrame from Task 4 and adds the `mastery_level` column.
        """
        if scores_df.empty:
            return pd.DataFrame()
            
        df = scores_df.copy()
        df["mastery_level"] = df["score_percent"].apply(self.get_mastery)
        return df

# ------------------ CLI / Demo ------------------
if __name__ == "__main__":
    import os
    import argparse
    parser = argparse.ArgumentParser(description="STUDIQS Topic Mastery Engine")
    parser.add_argument("--input", "-i", type=str, help="Path to external JSON or CSV file containing topics and score_percent")
    args = parser.parse_args()

    print("=" * 60)
    print("STUDIQS TOPIC MASTERY ENGINE (Task 5)")
    print("=" * 60)

    engine = TopicMasteryEngine()
    
    if args.input and os.path.exists(args.input):
        print(f"[Info] Loading external data from {args.input}...")
        if args.input.endswith(".csv"):
            df = pd.read_csv(args.input)
        else:
            df = pd.read_json(args.input)
    else:
        print("[Info] No external input provided. Using dummy data...")
        df = pd.DataFrame([
            {"topic": "Algebra", "score_percent": 40.0},
            {"topic": "Geometry", "score_percent": 100.0},
            {"topic": "Trigonometry", "score_percent": 20.0},
            {"topic": "Statistics", "score_percent": 75.0},
        ])
    
    result = engine.evaluate(df)
    print(result.to_string(index=False))
    
    # Save standalone output
    try:
        project_root = _find_workspace_root()
        out_dir = project_root / "outputs" / "Task_5_Topic_Mastery"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "topic_mastery_engine_output.json"
        
        result.to_json(out_path, orient="records", indent=2)
        print(f"\n[Success] Output saved to {out_path}")
    except Exception as e:
        print(f"\n[Error] Could not save output: {e}")
