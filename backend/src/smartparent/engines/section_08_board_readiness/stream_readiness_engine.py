import json
import sys
import pandas as pd
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_PATH = SCRIPT_DIR.parent.parent / "data" / "inputs" / "student_scores.json"
STREAM_REPO_PATH = SCRIPT_DIR.parent.parent / "data" / "inputs" / "stream_repository.xlsx"
OUTPUT_PATH = SCRIPT_DIR / "stream_readiness_output.json"


def classify_readiness(avg_score):
    """Classify readiness based on average score."""
    if avg_score >= 80:
        return "High"
    elif avg_score >= 60:
        return "Moderate"
    return "Low"


def normalize_subject(subject_str):
    s = subject_str.lower().strip()
    mapping = {
        "mathematics": "maths",
        "physics": "physics",
        "chemistry": "chemistry",
        "biology": "biology",
        "botany": "biology",
        "zoology": "biology",
        "commerce": "commerce",
        "accountancy": "accountancy",
        "economics": "economics",
        "computer science": "computer_science",
        "statistics": "statistics",
        "electronics": "electronics",
        "biotechnology": "biotechnology",
        "microbiology": "microbiology",
        "biochemistry": "biochemistry",
        "history": "history",
        "geography": "geography",
        "political science": "political_science",
        "sociology": "sociology",
        "psychology": "psychology",
        "english": "english",
        "tamil": "tamil",
        "hindi": "hindi",
        "fine arts": "fine_arts",
        "music": "music",
    }
    return mapping.get(s, s.replace(" ", "_"))


def build_stream_subject_map(stream_df):
    stream_df.columns = stream_df.columns.str.strip()
    clean_df = stream_df.dropna(subset=["Stream ID"])

    science_pcm_subjects = set()
    science_pcb_subjects = set()
    commerce_subjects = set()

    for _, row in clean_df.iterrows():
        major = str(row.get("Major Stream", "")).strip().lower()
        subjects_str = str(row.get("Subjects", "")).strip()
        subjects = [normalize_subject(s.strip()) for s in subjects_str.split(",") if s.strip()]

        if major == "science":
            if "maths" in subjects and "physics" in subjects:
                science_pcm_subjects.update(["maths", "physics", "chemistry"])
            if "biology" in subjects and "physics" in subjects:
                science_pcb_subjects.update(["biology", "physics", "chemistry"])
        elif major == "commerce":
            non_comm_subs = {"maths", "mathematics", "computer_science", "computer science",
                             "statistics", "history", "geography", "physical_education",
                             "physical education", "psychology"}
            comm_subs = [s for s in subjects if s not in non_comm_subs]
            commerce_subjects.update(comm_subs)

    stream_map = {}
    if science_pcm_subjects:
        stream_map["engineering_readiness"] = list(science_pcm_subjects)
    if science_pcb_subjects:
        stream_map["life_science_readiness"] = list(science_pcb_subjects)
    if commerce_subjects:
        stream_map["commerce_readiness"] = list(commerce_subjects)

    return stream_map


def calculate_stream_readiness(student: dict, stream_subject_map: dict) -> dict:
    """
    Calculate stream readiness with:
    1. Weakness gate: if ALL subject scores < 50, cap at "Low"
    2. Biology-dominant boost: if biology >= 85 and is highest science subject,
       boost life_science_readiness by one tier
    Output: only engineering_readiness, life_science_readiness, commerce_readiness
    """
    readiness = {}

    # Collect ALL subject scores from the student for weakness gate
    score_subjects = ["maths", "physics", "chemistry", "biology", "commerce",
                      "accountancy", "economics"]
    all_scores = [student[sub] for sub in score_subjects if sub in student]

    # Weakness gate: if ALL available scores are below 50, cap everything at Low
    all_weak = len(all_scores) > 0 and all(s < 50 for s in all_scores)

    for stream, subjects in stream_subject_map.items():
        scores = [student[sub] for sub in subjects if sub in student]
        if scores:
            avg = sum(scores) / len(scores)
            if all_weak:
                readiness[stream] = "Low"
            else:
                readiness[stream] = classify_readiness(avg)
        else:
            readiness[stream] = "Low"

    # Biology-dominant boost for life_science_readiness (BUG-004 fix):
    # If biology >= 85 AND biology is the student's highest science subject,
    # boost life_science_readiness by one tier
    biology_score = student.get("biology", 0)
    maths_score = student.get("maths", 0)
    physics_score = student.get("physics", 0)
    chemistry_score = student.get("chemistry", 0)

    if not all_weak and biology_score >= 85:
        science_subjects_scores = {
            "biology": biology_score,
            "maths": maths_score,
            "physics": physics_score,
            "chemistry": chemistry_score
        }
        highest_science = max(science_subjects_scores, key=science_subjects_scores.get)
        if highest_science == "biology":
            # Boost life_science_readiness by one tier
            current = readiness.get("life_science_readiness", "Low")
            tier_up = {"Low": "Moderate", "Moderate": "High", "High": "High"}
            readiness["life_science_readiness"] = tier_up[current]

    return readiness


if __name__ == "__main__":
    input_path = DEFAULT_INPUT_PATH
    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])

    if not input_path.exists():
        print(f"Error: Input file {input_path} not found.")
        sys.exit(1)

    if input_path.suffix == ".csv":
        df = pd.read_csv(input_path)
        students_dict = {}
        for _, row in df.iterrows():
            sid = str(row["student_id"])
            sub = normalize_subject(str(row["subject"]))
            marks = float(row["marks"])
            if sid not in students_dict:
                students_dict[sid] = {"student_id": sid}
            students_dict[sid][sub] = marks
        data = list(students_dict.values())
    else:
        with open(input_path, "r") as f:
            data = json.load(f)

    is_list = isinstance(data, list)
    students_list = data if is_list else [data]

    if not STREAM_REPO_PATH.exists():
        print(f"Error: {STREAM_REPO_PATH} not found.")
        sys.exit(1)

    stream_df = pd.read_excel(STREAM_REPO_PATH)
    stream_subject_map = build_stream_subject_map(stream_df)

    outputs = []
    for student in students_list:
        res = calculate_stream_readiness(student, stream_subject_map)
        if is_list:
            res = {"student_id": student.get("student_id"), **res}
        outputs.append(res)

    output_to_save = outputs if is_list else outputs[0]

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output_to_save, f, indent=2)

    print(json.dumps(output_to_save, indent=2))
