import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TASK1_OUTPUT = SCRIPT_DIR.parent / "task1_stream_readiness" / "stream_readiness_output.json"
TASK3_OUTPUT = SCRIPT_DIR.parent / "task3_projected_cutoff" / "projected_cutoff_output.json"
OUTPUT_PATH = SCRIPT_DIR / "career_readiness_output.json"


def calculate_career_readiness(stream_data: dict, cutoff_data: dict) -> dict:
    """
    Build career readiness from stream readiness.
    Spec output: {"engineering": "High", "life_science": "Moderate", "commerce": "Low"}
    """
    return {
        "engineering": stream_data.get("engineering_readiness", stream_data.get("engineering", "Low")),
        "life_science": stream_data.get("life_science_readiness", stream_data.get("life_science", "Low")),
        "commerce": stream_data.get("commerce_readiness", stream_data.get("commerce", "Low")),
    }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            data = data[0]
        stream_data = {
            "engineering_readiness": data.get("engineering_readiness", data.get("engineering")),
            "life_science_readiness": data.get("life_science_readiness", data.get("life_science")),
            "commerce_readiness": data.get("commerce_readiness", data.get("commerce")),
        }
        cutoff_data = {"projected_cutoff": data.get("projected_cutoff")}
        
        output = calculate_career_readiness(stream_data, cutoff_data)
        output_to_save = output
    else:
        if not TASK1_OUTPUT.exists():
            print(f"Error: {TASK1_OUTPUT} not found. Run Task 1 first.")
            sys.exit(1)
        if not TASK3_OUTPUT.exists():
            print(f"Error: {TASK3_OUTPUT} not found. Run Task 3 first.")
            sys.exit(1)

        with open(TASK1_OUTPUT, "r") as f:
            stream_data = json.load(f)
        with open(TASK3_OUTPUT, "r") as f:
            cutoff_data = json.load(f)

        is_list = isinstance(stream_data, list)
        if is_list:
            stream_map = {s["student_id"]: s for s in stream_data}
            cutoff_map = {c["student_id"]: c for c in cutoff_data}
            
            outputs = []
            for sid in stream_map:
                s_val = stream_map[sid]
                c_val = cutoff_map.get(sid, {"projected_cutoff": 0.0})
                res = calculate_career_readiness(s_val, c_val)
                outputs.append({"student_id": sid, **res})
            output_to_save = outputs
        else:
            output_to_save = calculate_career_readiness(stream_data, cutoff_data)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output_to_save, f, indent=2)

    print(json.dumps(output_to_save, indent=2))
