import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = SCRIPT_DIR / "future_readiness_report.json"

TASK_SCRIPTS = [
    SCRIPT_DIR.parent / "task1_stream_readiness" / "stream_readiness_engine.py",
    SCRIPT_DIR.parent / "task2_projected_score" / "projected_score_engine.py",
    SCRIPT_DIR.parent / "task3_projected_cutoff" / "projected_cutoff_engine.py",
    SCRIPT_DIR.parent / "task4_career_readiness" / "career_readiness_engine.py",
    SCRIPT_DIR.parent / "task5_college_recommendation" / "college_recommendation_engine.py",
]

STUDENT_SCORES = SCRIPT_DIR.parent.parent / "data" / "inputs" / "student_scores.json"
TASK2_OUTPUT = SCRIPT_DIR.parent / "task2_projected_score" / "projected_score_output.json"
TASK3_OUTPUT = SCRIPT_DIR.parent / "task3_projected_cutoff" / "projected_cutoff_output.json"
TASK4_OUTPUT = SCRIPT_DIR.parent / "task4_career_readiness" / "career_readiness_output.json"
TASK5_OUTPUT = SCRIPT_DIR.parent / "task5_college_recommendation" / "college_recommendation_output.json"

# Spec output keys for career readiness
CORE_STREAMS = ["engineering", "life_science", "commerce"]
READINESS_RANK = {"High": 3, "Moderate": 2, "Low": 1}
PRIORITY = {"engineering": 4, "life_science": 3, "commerce": 2}


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


def determine_best_path(career_data: dict, stream_avgs: dict) -> tuple:
    """
    Multi-level tiebreaker for best path selection:
    1. Primary: Highest readiness level (High > Moderate > Low)
    2. Secondary: Highest raw stream average score
    3. Tertiary: Domain priority order (engineering > life_science > commerce)
    
    Returns: (best_path_key, readiness_level)
    """
    available = {k: v for k, v in career_data.items()
                 if k in CORE_STREAMS and isinstance(v, str)}
    if not available:
        return ("engineering", "Low")

    best = max(available, key=lambda k: (
        READINESS_RANK.get(available[k], 0),
        stream_avgs.get(k, 0.0),
        PRIORITY.get(k, 0)
    ))
    return (best, available[best])


def run_all_engines():
    for i, script in enumerate(TASK_SCRIPTS, 1):
        print(f"\n  Running Task {i}: {script.name}")
        args = [sys.executable, str(script)]
        if len(sys.argv) > 1 and script.name in ["stream_readiness_engine.py", "projected_cutoff_engine.py"]:
            args.append(sys.argv[1])
            
        result = subprocess.run(
            args,
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"  ERROR in Task {i}: {result.stderr}")
            sys.exit(1)
        lines = result.stdout.strip().split("\n")
        for line in lines[-4:]:
            print(f"    {line}")


def generate_report():
    with open(TASK2_OUTPUT, "r") as f:
        t2 = json.load(f)
    with open(TASK3_OUTPUT, "r") as f:
        t3 = json.load(f)
    with open(TASK4_OUTPUT, "r") as f:
        t4 = json.load(f)
    with open(TASK5_OUTPUT, "r") as f:
        t5 = json.load(f)

    # Load student scores for tiebreaking
    scores_map = {}
    if STUDENT_SCORES.exists():
        with open(STUDENT_SCORES, "r") as f:
            scores_list = json.load(f)
        if isinstance(scores_list, list):
            scores_map = {str(s["student_id"]): s for s in scores_list}

    is_list = isinstance(t2, list)

    if is_list:
        t2_map = {x["student_id"]: x for x in t2}
        t3_map = {x["student_id"]: x for x in t3}
        t4_map = {x["student_id"]: x for x in t4}
        t5_map = {x["student_id"]: x for x in t5}

        reports = []
        for sid in t2_map:
            s2 = t2_map[sid]
            s3 = t3_map.get(sid, {"projected_cutoff": 0.0})
            s4 = t4_map.get(sid, {"engineering": "Low", "life_science": "Low", "commerce": "Low"})
            s5 = t5_map.get(sid, {"safe": [], "target": []})

            # Compute stream averages from raw scores for tiebreaking
            raw_scores = scores_map.get(sid, {})
            stream_avgs = compute_stream_avgs(raw_scores)

            best_path_key, future_readiness = determine_best_path(s4, stream_avgs)
            best_path_label = best_path_key.replace("_", " ").title()

            reports.append({
                "student_id": sid,
                "future_readiness": future_readiness,
                "projected_score": s2["projected_score"],
                "projected_cutoff": s3["projected_cutoff"],
                "best_path": best_path_label,
                "safe_colleges": s5["safe"],
                "target_colleges": s5["target"]
            })
        return reports
    else:
        stream_avgs = compute_stream_avgs({})
        best_path_key, future_readiness = determine_best_path(t4, stream_avgs)
        best_path_label = best_path_key.replace("_", " ").title()

        report = {
            "future_readiness": future_readiness,
            "projected_score": t2["projected_score"],
            "projected_cutoff": t3["projected_cutoff"],
            "best_path": best_path_label,
            "safe_colleges": t5["safe"],
            "target_colleges": t5["target"]
        }
        return report


if __name__ == "__main__":
    print("=" * 60)
    print("  STUDIQS - Future Readiness Engine (Task 6)")
    print("=" * 60)

    run_all_engines()

    print(f"\n{'=' * 60}")
    print("  Generating Future Readiness Report")
    print(f"{'=' * 60}")

    report = generate_report()

    with open(OUTPUT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    data_out_dir = SCRIPT_DIR.parent.parent / "data" / "outputs"
    data_out_dir.mkdir(parents=True, exist_ok=True)
    with open(data_out_dir / "future_readiness_report.json", "w") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))
    print(f"\nReport saved to {OUTPUT_PATH}")
    print(f"\n{'=' * 60}")
    print("  ENGINE COMPLETE")
    print(f"{'=' * 60}")
