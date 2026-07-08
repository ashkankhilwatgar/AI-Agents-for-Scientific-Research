# AI-Agents-for-Scientific-Research
A framework for using LLMs for gene variant interpretation

**Requires Python 3.10+** (recommended: 3.12). Verified to run on 3.11, 3.12, and 3.13.

## Quick Start

```bash
# 1. Install Dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your own api keys

# 3. Run single variant analysis
python -m pipeline --variant "NM_000020.3:c.557G>T" --disease "HHT"

# 4. Run batch analysis

```bash
python -m pipeline --csv hht-batches.csv
```

## Run Evaluation

```bash
python -m evaluation.question2 --gold_answer_csv_filename hht_script_2.csv --model_output_json_filename outputs/batch_20260707_125513/batch_summary.json --output_dir evaluation/outputs
```



