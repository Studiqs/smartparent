import json
import sys
import pandas as pd
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_DIR = SCRIPT_DIR.parent.parent / "data" / "inputs"

REPO_CUTOFF = INPUT_DIR / "engineering_cutoff_repository.xlsx"
REPO_COURSE = INPUT_DIR / "course_repository.xlsx"
REPO_COLLEGE = INPUT_DIR / "tn_college_repository.xlsx"
STUDENT_SCORES = INPUT_DIR / "student_scores.json"
TASK3_OUTPUT = SCRIPT_DIR.parent / "task3_projected_cutoff" / "projected_cutoff_output.json"
TASK4_OUTPUT = SCRIPT_DIR.parent / "task4_career_readiness" / "career_readiness_output.json"
OUTPUT_PATH = SCRIPT_DIR / "college_recommendation_output.json"

READINESS_RANK = {"High": 3, "Moderate": 2, "Low": 1}
CORE_STREAMS = ["engineering", "life_science", "commerce"]
PRIORITY = {"engineering": 4, "life_science": 3, "commerce": 2}


def load_and_clean(path):
    df = pd.read_excel(path)
    df.columns = df.columns.str.strip()
    for col in df.select_dtypes(include=["object"]):
        df[col] = df[col].astype(str).str.strip()
    return df


def compute_stream_avgs(student_scores: dict) -> dict:
    """Compute stream averages from raw subject scores for tiebreaking."""
    m = student_scores.get("maths", 0)
    p = student_scores.get("physics", 0)
    c = student_scores.get("chemistry", 0)
    b = student_scores.get("biology", 0)
    co = student_scores.get("commerce", 0)
    return {
        "engineering": (m + p + c) / 3 if (m or p or c) else 0,
        "life_science": (b + p + c) / 3 if (b or p or c) else 0,
        "commerce": co,
    }


def find_best_path(career_data: dict, stream_avgs: dict) -> str:
    """Multi-level tiebreaker: readiness rank → stream avg → domain priority."""
    available = {k: v for k, v in career_data.items()
                 if k in CORE_STREAMS and isinstance(v, str)}
    if not available:
        return "engineering"
    return max(available, key=lambda k: (
        READINESS_RANK.get(available[k], 0),
        stream_avgs.get(k, 0.0),
        PRIORITY.get(k, 0)
    ))


def get_recommendations(projected_cutoff: float, career: str) -> dict:
    if not REPO_CUTOFF.exists():
        print(f"Error: {REPO_CUTOFF} not found.")
        sys.exit(1)
    if not REPO_COURSE.exists():
        print(f"Error: {REPO_COURSE} not found.")
        sys.exit(1)
    if not REPO_COLLEGE.exists():
        print(f"Error: {REPO_COLLEGE} not found.")
        sys.exit(1)

    df_course = load_and_clean(REPO_COURSE)
    df_college = load_and_clean(REPO_COLLEGE)

    df_college_clean = df_college[pd.to_numeric(df_college["S.No"], errors="coerce").notna()]
    college_meta = {}
    for _, row in df_college_clean.iterrows():
        name = str(row.get("College Name", "")).strip().lower()
        college_meta[name] = {
            "district": str(row.get("District", "")),
            "type": str(row.get("Type", "")),
            "url": str(row.get("Links", ""))
        }

    colleges_with_cutoffs = []

    career_norm = career.lower().replace("_", " ").strip()
    if "engineering" in career_norm:
        df_cutoff = load_and_clean(REPO_CUTOFF)
        for _, row in df_cutoff.iterrows():
            college = str(row.get("College", "")).strip()
            cutoff = row.get("OC Cutoff (2024)")
            try:
                cutoff = float(cutoff)
                if not pd.isna(cutoff) and cutoff > 0:
                    colleges_with_cutoffs.append((college, cutoff))
            except (ValueError, TypeError):
                continue
    elif "commerce" in career_norm:
        unique_colleges = sorted(df_course[df_course["Stream"] == "Arts & Science"]["College"].unique())
        for idx, college in enumerate(unique_colleges):
            cutoff = 105.0 + (idx * 90.0 / max(1, len(unique_colleges) - 1))
            colleges_with_cutoffs.append((college, round(cutoff, 1)))
    elif "life science" in career_norm:
        unique_colleges = sorted(df_course[df_course["Stream"] == "Medical"]["College"].unique())
        for idx, college in enumerate(unique_colleges):
            cutoff = 105.0 + (idx * 90.0 / max(1, len(unique_colleges) - 1))
            colleges_with_cutoffs.append((college, round(cutoff, 1)))
    else:
        df_cutoff = load_and_clean(REPO_CUTOFF)
        for _, row in df_cutoff.iterrows():
            college = str(row.get("College", "")).strip()
            cutoff = row.get("OC Cutoff (2024)")
            try:
                cutoff = float(cutoff)
                if not pd.isna(cutoff) and cutoff > 0:
                    colleges_with_cutoffs.append((college, cutoff))
            except (ValueError, TypeError):
                continue

    safe = []
    target = []
    ambitious = []

    for college, cutoff in colleges_with_cutoffs:
        entry = college

        if cutoff <= projected_cutoff - 5:
            if entry not in safe:
                safe.append(entry)
        elif cutoff <= projected_cutoff + 5:
            if entry not in target:
                target.append(entry)
        else:
            if entry not in ambitious:
                ambitious.append(entry)

    return {"safe": safe, "target": target, "ambitious": ambitious}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            data = data[0]
        cutoff_val = data["projected_cutoff"]
        career = data.get("career", "Engineering")
        
        output_to_save = get_recommendations(cutoff_val, career)
    else:
        if not TASK3_OUTPUT.exists():
            print(f"Error: {TASK3_OUTPUT} not found. Run Task 3 first.")
            sys.exit(1)
        if not TASK4_OUTPUT.exists():
            print(f"Error: {TASK4_OUTPUT} not found. Run Task 4 first.")
            sys.exit(1)

        with open(TASK3_OUTPUT, "r") as f:
            t3_data = json.load(f)
        with open(TASK4_OUTPUT, "r") as f:
            t4_data = json.load(f)

        # Load student scores for tiebreaking
        scores_map = {}
        if STUDENT_SCORES.exists():
            with open(STUDENT_SCORES, "r") as f:
                scores_list = json.load(f)
            if isinstance(scores_list, list):
                scores_map = {str(s["student_id"]): s for s in scores_list}

        is_list = isinstance(t3_data, list)

        if is_list:
            t4_map = {x["student_id"]: x for x in t4_data}
            outputs = []
            for student in t3_data:
                sid = student["student_id"]
                cutoff_val = student["projected_cutoff"]
                
                s4 = t4_map.get(sid, {"engineering": "Low", "life_science": "Low", "commerce": "Low"})
                raw_scores = scores_map.get(sid, {})
                stream_avgs = compute_stream_avgs(raw_scores)
                best_path = find_best_path(s4, stream_avgs)
                
                res = get_recommendations(cutoff_val, best_path)
                outputs.append({"student_id": sid, **res})
            output_to_save = outputs
        else:
            cutoff_val = t3_data["projected_cutoff"]
            stream_avgs = compute_stream_avgs({})
            best_path = find_best_path(t4_data, stream_avgs)
            
            output_to_save = get_recommendations(cutoff_val, best_path)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output_to_save, f, indent=2)

    print(json.dumps(output_to_save, indent=2))
