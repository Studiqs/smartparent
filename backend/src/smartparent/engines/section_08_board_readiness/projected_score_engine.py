import json
import sys
import pandas as pd
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_PATH = SCRIPT_DIR.parent.parent / "data" / "inputs" / "term_scores.json"
MASTERY_REPO_PATH = SCRIPT_DIR.parent.parent / "data" / "inputs" / "test_mastery.xlsx"
OUTPUT_PATH = SCRIPT_DIR / "projected_score_output.json"

MASTERY_FACTORS = {
    "Strong": 1.05,
    "Average": 1.0,
    "Weak": 0.95,
    "Critical": 0.90
}


def get_mastery_level(mastery_df, score):
    mastery_df.columns = mastery_df.columns.str.strip()
    for _, row in mastery_df.iterrows():
        min_val = float(row["Score_Range_Min"])
        max_val = float(row["Score_Range_Max"])
        level = str(row["Level"]).strip()
        if min_val <= score <= max_val:
            return level
    return "Average"


def calculate_projected_score(data: dict, mastery_df) -> dict:
    term1 = data["term1"]
    term2 = data["term2"]
    term3 = data["term3"]

    weighted_avg = (term1 * 0.2) + (term2 * 0.3) + (term3 * 0.5)

    trend_diff = term3 - term1
    if trend_diff > 10:
        trend_bonus = 5      # Strong upward trend
    elif trend_diff > 0:
        trend_bonus = 2      # Mild upward trend
    elif trend_diff < -10:
        trend_bonus = -5     # Strong decline
    elif trend_diff < 0:
        trend_bonus = -2     # Mild decline
    else:
        trend_bonus = 0      # Stable

    mastery_level = get_mastery_level(mastery_df, weighted_avg)
    mastery_factor = MASTERY_FACTORS.get(mastery_level, 1.0)

    projected = min(100, round(weighted_avg * mastery_factor + trend_bonus))

    return {"projected_score": projected}


if __name__ == "__main__":
    input_path = DEFAULT_INPUT_PATH
    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])

    if not input_path.exists():
        print(f"Error: Input file {input_path} not found.")
        sys.exit(1)

    with open(input_path, "r") as f:
        data = json.load(f)

    is_list = isinstance(data, list)
    is_dict_of_dicts = isinstance(data, dict) and any(isinstance(v, dict) for v in data.values())

    if is_list:
        students_list = data
    elif is_dict_of_dicts:
        students_list = [{"student_id": k, **v} for k, v in data.items()]
    else:
        students_list = [data]

    if not MASTERY_REPO_PATH.exists():
        print(f"Error: {MASTERY_REPO_PATH} not found.")
        sys.exit(1)

    mastery_df = pd.read_excel(MASTERY_REPO_PATH)

    outputs = []
    for student in students_list:
        res = calculate_projected_score(student, mastery_df)
        if is_list or is_dict_of_dicts:
            res = {"student_id": student.get("student_id"), **res}
        outputs.append(res)

    output_to_save = outputs if (is_list or is_dict_of_dicts) else outputs[0]

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output_to_save, f, indent=2)

    print(json.dumps(output_to_save, indent=2))
