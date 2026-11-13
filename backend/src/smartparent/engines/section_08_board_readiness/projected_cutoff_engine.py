import json
import sys
import pandas as pd
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_PATH = SCRIPT_DIR.parent.parent / "data" / "inputs" / "student_scores.json"
OUTPUT_PATH = SCRIPT_DIR / "projected_cutoff_output.json"


def calculate_projected_cutoff(data: dict) -> dict:
    maths = data["maths"]
    physics = data["physics"]
    chemistry = data["chemistry"]

    projected_cutoff = maths + ((physics + chemistry) / 2)

    return {"projected_cutoff": projected_cutoff}


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
            sub = str(row["subject"]).strip().lower()
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

    outputs = []
    for student in students_list:
        res = calculate_projected_cutoff(student)
        if is_list:
            res = {"student_id": student.get("student_id"), **res}
        outputs.append(res)

    output_to_save = outputs if is_list else outputs[0]

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output_to_save, f, indent=2)

    print(json.dumps(output_to_save, indent=2))
