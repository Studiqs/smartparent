import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_PATH = SCRIPT_DIR.parent.parent / "data" / "inputs" / "parent_survey_data.json"
OUTPUT_PATH = SCRIPT_DIR / "parent_satisfaction_output.json"


def calculate_parent_satisfaction(data: dict) -> dict:
    survey_scores = data["survey_scores"]

    average_score = sum(survey_scores) / len(survey_scores)
    parent_satisfaction = round(average_score / 5 * 100)

    if parent_satisfaction >= 85:
        satisfaction_level = "Excellent"
        insight = "Parent satisfaction is strong. Continue regular parent communication and feedback collection."
    elif parent_satisfaction >= 70:
        satisfaction_level = "Good"
        insight = "Parent satisfaction is good. Minor areas of improvement can be addressed through feedback analysis."
    elif parent_satisfaction >= 50:
        satisfaction_level = "Moderate"
        insight = "Parent satisfaction is moderate. Conduct focused surveys to identify specific areas of concern."
    else:
        satisfaction_level = "Low"
        insight = "Parent satisfaction is low. Immediate attention needed to address parent concerns and grievances."

    return {
        "parent_satisfaction": parent_satisfaction,
        "satisfaction_level": satisfaction_level,
        "insight": insight
    }


if __name__ == "__main__":
    input_path = DEFAULT_INPUT_PATH
    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])

    if not input_path.exists():
        print(f"Error: Input file {input_path} not found.")
        sys.exit(1)

    with open(input_path, "r") as f:
        data = json.load(f)

    result = calculate_parent_satisfaction(data)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))
