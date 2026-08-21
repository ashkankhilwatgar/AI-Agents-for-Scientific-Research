# Merge per-mode ablation outputs (produced by run_agent_ablation.py --mode <mode>
# separately for each of full/no_debug/no_judge/task_only) back into the combined
# raw + summary JSON files and print the usual comparison table. The four
# pipeline-compatible mode folders are preserved and linked from the summary.
#
# Usage:
#   python -m evaluation.merge_ablation_results --run_id 20260710_120000 \
#       --output_dir evaluation/outputs

import argparse
import json
from pathlib import Path

from evaluation.run_agent_ablation import ABLATION_MODES, print_summary_table


def merge(run_id: str, output_dir: str):
    output_dir = Path(output_dir)
    all_results = {}
    missing = []

    for mode in ABLATION_MODES:
        path = output_dir / f"ablation_raw_{mode}_{run_id}.json"
        if not path.exists():
            missing.append(str(path))
            continue
        with open(path) as f:
            data = json.load(f)
        all_results[mode] = data[mode]

    if missing:
        print("Missing per-mode result file(s), cannot merge yet:")
        for m in missing:
            print(f"  - {m}")
        return

    raw_path = output_dir / f"ablation_raw_{run_id}.json"
    with open(raw_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"Combined raw results saved to {raw_path}")

    summary = print_summary_table(all_results)

    summary_path = output_dir / f"ablation_summary_{run_id}.json"
    with open(summary_path, "w") as f:
        mode_output_dirs = {
            mode: str(output_dir / f"ablation_{mode}_{run_id}")
            for mode in ABLATION_MODES
        }
        json.dump(
            {
                "timestamp": run_id,
                "modes": summary,
                "mode_output_dirs": mode_output_dirs,
                "mode_batch_summaries": {
                    mode: str(Path(path) / "batch_summary.json")
                    for mode, path in mode_output_dirs.items()
                },
            },
            f,
            indent=2,
        )
    print(f"\nSummary saved to {summary_path}")


def main():
    parser = argparse.ArgumentParser(description="Merge per-mode ablation results")
    parser.add_argument("--run_id", type=str, required=True,
                        help="The run_id shared by the 4 individual --mode runs")
    parser.add_argument("--output_dir", type=str, default="evaluation/outputs")
    args = parser.parse_args()
    merge(args.run_id, args.output_dir)


if __name__ == "__main__":
    main()
