# Evaluation Framework

This directory contains the evaluation framework for testing SQL generation quality.

## Structure

```
tests/
├── golden_sql/          # Golden SQL test cases
│   ├── 001_basic_aggregation.yml
│   ├── 002_filtered_top_n.yml
│   └── 003_complex_filtering.yml
├── evals/
│   ├── runner.py        # Main evaluation runner
│   └── report.json      # Generated report (after running)
└── README.md
```

## Adding New Test Cases

Create a YAML file in `tests/golden_sql/` following this format:

```yaml
question: "Your natural language question"
description: "What this test evaluates"
difficulty: easy|medium|hard
tables_involved:
  - table_name

columns_involved:
  - column_name

expected_sql: |
  SELECT ...
  FROM ...
  WHERE ...

test_cases:
  - question: "Variation of the question"
    should_pass: true
    notes: "Explanation"

success_criteria:
  must_include:
    - "GROUP BY"
  result_check:
    min_rows: 5
```

## Running Evaluations

### Run all evaluations:
```bash
python -m tests.evals.runner
```

### Run from project root:
```bash
python tests/evals/runner.py
```

## Evaluation Metrics

The framework evaluates SQL quality using:

1. **Structural Comparison**: Checks for required clauses (GROUP BY, WHERE, etc.)
2. **Result Comparison**: Executes both SQL queries and compares outputs
3. **Semantic Scoring**: 0.0-1.0 score based on structure and results

A test passes with score >= 0.7

## Continuous Integration

Add to your CI pipeline:
```yaml
- name: Run SQL Evaluations
  run: python tests/evals/runner.py
```

The runner exits with code 1 if pass rate < 50%, failing the build.
