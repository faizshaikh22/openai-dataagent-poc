"""
Evaluation Framework for Data Agent

This module provides comprehensive evaluation capabilities for testing SQL generation
quality. It compares generated SQL against golden SQL using both semantic and 
result-based comparisons.

Usage:
    python tests/evals/runner.py

Or programmatically:
    from tests.evals.runner import EvalRunner
    runner = EvalRunner()
    results = runner.run_all_evals()
"""

# CRITICAL: Add project root to path BEFORE any other imports
import sys
from pathlib import Path

# Get project root (parent of tests directory)
_file = Path(__file__).resolve()
project_root = _file.parent.parent
app_root = project_root / "app"

# Add to path if not already there
project_root_str = str(project_root)
app_root_str = str(app_root)

if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)
if app_root_str not in sys.path:
    sys.path.insert(0, app_root_str)

# Now import our modules
import os
import re
import yaml
import json
import sqlite3
import pandas as pd
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, field

from app.database.sqlite import db_adapter
from app.agent.core import extract_code_block
from app.utils.llm import query_llm_sync


@dataclass
class EvalResult:
    """Result of a single evaluation test"""
    test_id: str
    question: str
    passed: bool
    generated_sql: str
    expected_sql: str
    score: float  # 0.0 to 1.0
    reasoning: str
    details: Dict[str, Any] = field(default_factory=dict)
    

@dataclass
class TestCase:
    """Represents a single test case from YAML"""
    question: str
    description: str
    difficulty: str
    tables_involved: List[str]
    expected_sql: str
    test_cases: List[Dict]
    edge_cases: List[Dict]
    success_criteria: Dict


class SQLComparator:
    """Compares SQL queries for semantic equivalence"""
    
    @staticmethod
    def normalize_sql(sql: str) -> str:
        """Normalize SQL for comparison"""
        # Remove extra whitespace
        sql = re.sub(r'\s+', ' ', sql).strip()
        # Normalize case (keep structure but lowercase keywords)
        sql = sql.lower()
        # Remove trailing semicolons
        sql = sql.rstrip(';')
        return sql
    
    @staticmethod
    def extract_structure(sql: str) -> Dict[str, Any]:
        """Extract structural elements from SQL"""
        sql_lower = sql.lower()
        
        structure = {
            'has_group_by': 'group by' in sql_lower,
            'has_order_by': 'order by' in sql_lower,
            'has_where': 'where' in sql_lower,
            'has_having': 'having' in sql_lower,
            'has_limit': 'limit' in sql_lower,
            'aggregation_functions': re.findall(r'\b(sum|avg|count|min|max)\b', sql_lower),
            'tables': re.findall(r'from\s+(\w+)|join\s+(\w+)', sql_lower),
            'join_count': len(re.findall(r'\bjoin\b', sql_lower)),
        }
        
        return structure
    
    @staticmethod
    def compare_structures(gen_sql: str, exp_sql: str) -> Tuple[float, str]:
        """Compare SQL structures and return similarity score"""
        gen_struct = SQLComparator.extract_structure(gen_sql)
        exp_struct = SQLComparator.extract_structure(exp_sql)
        
        matches = 0
        total = 0
        differences = []
        
        # Compare boolean flags
        for key in ['has_group_by', 'has_order_by', 'has_where', 'has_having', 'has_limit']:
            total += 1
            if gen_struct[key] == exp_struct[key]:
                matches += 1
            else:
                differences.append(f"{key}: expected {exp_struct[key]}, got {gen_struct[key]}")
        
        # Compare aggregation functions
        gen_aggs = set(gen_struct['aggregation_functions'])
        exp_aggs = set(exp_struct['aggregation_functions'])
        
        if exp_aggs:
            total += 1
            if gen_aggs == exp_aggs:
                matches += 1
            else:
                differences.append(f"Aggregations: expected {exp_aggs}, got {gen_aggs}")
        
        # Compare join count
        if exp_struct['join_count'] > 0:
            total += 1
            if gen_struct['join_count'] == exp_struct['join_count']:
                matches += 1
            else:
                differences.append(f"Joins: expected {exp_struct['join_count']}, got {gen_struct['join_count']}")
        
        score = matches / total if total > 0 else 1.0
        return score, "; ".join(differences) if differences else "Structures match"
    
    @staticmethod
    def compare_results(gen_sql: str, exp_sql: str, db_adapter) -> Tuple[bool, str]:
        """Execute both queries and compare results"""
        try:
            gen_result = db_adapter.execute_query(gen_sql)
            exp_result = db_adapter.execute_query(exp_sql)
            
            if 'error' in gen_result:
                return False, f"Generated SQL error: {gen_result['error']}"
            
            if 'error' in exp_result:
                return False, f"Expected SQL error: {exp_result['error']}"
            
            gen_df = pd.DataFrame(gen_result['data'])
            exp_df = pd.DataFrame(exp_result['data'])
            
            # Check row counts
            if len(gen_df) != len(exp_df):
                return False, f"Row count mismatch: expected {len(exp_df)}, got {len(gen_df)}"
            
            # Check column counts
            if len(gen_df.columns) != len(exp_df.columns):
                return False, f"Column count mismatch: expected {len(exp_df.columns)}, got {len(gen_df.columns)}"
            
            # For small results, check values
            if len(gen_df) <= 10:
                # Sort both by first column for comparison
                if len(gen_df.columns) > 0:
                    col = str(gen_df.columns[0])
                    gen_sorted = gen_df.sort_values(by=[col]).reset_index(drop=True)
                    exp_sorted = exp_df.sort_values(by=[col]).reset_index(drop=True)
                    
                    if not gen_sorted.equals(exp_sorted):
                        return False, "Data values differ"
            
            return True, "Results match"
            
        except Exception as e:
            return False, f"Comparison error: {str(e)}"


class EvalRunner:
    """Main evaluation runner"""
    
    def __init__(self, golden_sql_dir: str = "tests/golden_sql"):
        self.golden_sql_dir = Path(golden_sql_dir)
        self.comparator = SQLComparator()
        self.results: List[EvalResult] = []
    
    def load_test_cases(self) -> List[TestCase]:
        """Load all test cases from YAML files"""
        test_cases = []
        
        if not self.golden_sql_dir.exists():
            print(f"Warning: Directory {self.golden_sql_dir} does not exist")
            return test_cases
        
        for yaml_file in sorted(self.golden_sql_dir.glob("*.yml")):
            try:
                with open(yaml_file, 'r') as f:
                    data = yaml.safe_load(f)
                
                test_case = TestCase(
                    question=data['question'],
                    description=data.get('description', ''),
                    difficulty=data.get('difficulty', 'medium'),
                    tables_involved=data.get('tables_involved', []),
                    expected_sql=data['expected_sql'],
                    test_cases=data.get('test_cases', []),
                    edge_cases=data.get('edge_cases', []),
                    success_criteria=data.get('success_criteria', {})
                )
                test_cases.append(test_case)
                
            except Exception as e:
                print(f"Error loading {yaml_file}: {e}")
        
        return test_cases
    
    def generate_sql(self, question: str) -> Tuple[str, str]:
        """Generate SQL using the agent for a given question"""
        from app.database.sqlite import db_adapter
        context = db_adapter.get_rich_context()
        
        system_prompt = f"""
        You are an expert Data Agent. Generate SQLite SQL to answer the user's question.
        
        ### Database Context
        {context}
        
        ### Rules
        1. Output ONLY standard SQLite SQL inside ```sql``` code blocks.
        2. Always LIMIT results to 100 unless specified otherwise.
        3. Use 'LIKE' for loose string matching on text fields.
        4. Salary/Money fields are TEXT with '$'. Use `CAST(REPLACE(col, '$', '') AS REAL)` for calculations.
        4. If the question is ambiguous or missing critical info (like date ranges), do your best with sensible defaults.
        """
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question}
        ]
        
        reasoning, content = query_llm_sync(messages)
        sql = extract_code_block(content, "sql")
        
        if not sql:
            return content, reasoning  # Return the error message
        
        return sql, reasoning
    
    def run_single_eval(self, test_case: TestCase, run_variations: bool = False) -> List[EvalResult]:
        """Run evaluation for a single test case with all its variations
        
        Args:
            test_case: The test case to evaluate
            run_variations: Whether to also run test case variations (slower)
        """
        results = []
        
        # First, evaluate the main question
        print(f"\n{'='*60}")
        print(f"Evaluating: {test_case.question}")
        print(f"Difficulty: {test_case.difficulty}")
        print(f"{'='*60}")
        
        generated_sql, reasoning = self.generate_sql(test_case.question)
        
        # Check if SQL was generated
        if not generated_sql.strip().lower().startswith('select'):
            result = EvalResult(
                test_id=f"main_{hash(test_case.question) % 10000}",
                question=test_case.question,
                passed=False,
                generated_sql=generated_sql,
                expected_sql=test_case.expected_sql,
                score=0.0,
                reasoning=f"Failed to generate valid SQL: {generated_sql}",
                details={'error': 'no_sql_generated'}
            )
            results.append(result)
            print(f"❌ FAILED: Could not generate valid SQL")
            return results
        
        # Compare structures
        struct_score, struct_reasoning = self.comparator.compare_structures(
            generated_sql, test_case.expected_sql
        )
        
        # Compare results
        results_match, results_reasoning = self.comparator.compare_results(
            generated_sql, test_case.expected_sql, db_adapter
        )
        
        # Calculate overall score
        score = 0.0
        if results_match:
            score = 1.0
        else:
            score = struct_score * 0.5  # Partial credit for structure
        
        passed = score >= 0.7  # Threshold for passing
        
        combined_reasoning = f"Structure: {struct_reasoning}\nResults: {results_reasoning}"
        
        result = EvalResult(
            test_id=f"main_{hash(test_case.question) % 10000}",
            question=test_case.question,
            passed=passed,
            generated_sql=generated_sql,
            expected_sql=test_case.expected_sql,
            score=score,
            reasoning=combined_reasoning,
            details={
                'structural_score': struct_score,
                'results_match': results_match,
                'llm_reasoning': reasoning
            }
        )
        results.append(result)
        
        status = "[PASSED]" if passed else "[FAILED]"
        print(f"{status} (Score: {score:.2f})")
        if not passed:
            print(f"  Generated: {generated_sql[:100]}...")
            print(f"  Reason: {combined_reasoning[:100]}...")
        
        # Evaluate test case variations
        for i, variation in enumerate(test_case.test_cases):
            # Skip variations if flag is False
            if not run_variations:
                continue
                
            var_question = variation['question']
            should_pass = variation.get('should_pass', True)
            
            print(f"\n  Testing variation {i+1}: {var_question[:60]}...")
            
            var_sql, var_reasoning = self.generate_sql(var_question)
            
            if not var_sql.strip().lower().startswith('select'):
                var_result = EvalResult(
                    test_id=f"var_{i}_{hash(var_question) % 10000}",
                    question=var_question,
                    passed=False if should_pass else True,  # If should fail, this is correct
                    generated_sql=var_sql,
                    expected_sql=test_case.expected_sql,
                    score=0.0,
                    reasoning="Failed to generate valid SQL",
                    details={'variation_notes': variation.get('notes', '')}
                )
                results.append(var_result)
                continue
            
            var_struct_score, _ = self.comparator.compare_structures(var_sql, test_case.expected_sql)
            var_results_match, _ = self.comparator.compare_results(var_sql, test_case.expected_sql, db_adapter)
            
            if var_results_match:
                var_score = 1.0
            else:
                var_score = var_struct_score * 0.5
            
            # For variations that should fail, invert the logic
            var_passed = (var_score >= 0.7) if should_pass else (var_score < 0.7)
            
            var_result = EvalResult(
                test_id=f"var_{i}_{hash(var_question) % 10000}",
                question=var_question,
                passed=var_passed,
                generated_sql=var_sql,
                expected_sql=test_case.expected_sql,
                score=var_score,
                reasoning=f"Expected to {'pass' if should_pass else 'fail'}, score={var_score:.2f}",
                details={'variation_notes': variation.get('notes', '')}
            )
            results.append(var_result)
            
            status = "[OK]" if var_passed else "[X]"
            print(f"    {status} Score: {var_score:.2f}")
        
        return results
    
    def run_all_evals(self, run_variations: bool = False) -> Dict[str, Any]:
        """Run all evaluations and return summary
        
        Args:
            run_variations: Whether to run test case variations (slower)
        """
        test_cases = self.load_test_cases()
        
        if not test_cases:
            print("No test cases found!")
            return {}
        
        print(f"\n{'='*60}")
        print(f"RUNNING {len(test_cases)} GOLDEN SQL EVALUATIONS")
        if not run_variations:
            print("(Main questions only - use --variations for full test)")
        print(f"{'='*60}")
        
        all_results = []
        for test_case in test_cases:
            results = self.run_single_eval(test_case, run_variations=run_variations)
            all_results.extend(results)
        
        self.results = all_results
        return self.generate_summary()
    
    def generate_summary(self) -> Dict[str, Any]:
        """Generate evaluation summary"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        avg_score = sum(r.score for r in self.results) / total if total > 0 else 0
        
        summary = {
            'total_tests': total,
            'passed': passed,
            'failed': failed,
            'pass_rate': passed / total if total > 0 else 0,
            'average_score': avg_score,
            'results': [
                {
                    'test_id': r.test_id,
                    'question': r.question,
                    'passed': r.passed,
                    'score': r.score,
                    'reasoning': r.reasoning
                }
                for r in self.results
            ]
        }
        
        return summary
    
    def save_report(self, output_path: str = "tests/evals/report.json"):
        """Save evaluation report to file"""
        summary = self.generate_summary()
        
        # Add full details
        report = {
            'summary': summary,
            'detailed_results': [
                {
                    'test_id': r.test_id,
                    'question': r.question,
                    'passed': r.passed,
                    'generated_sql': r.generated_sql,
                    'expected_sql': r.expected_sql,
                    'score': r.score,
                    'reasoning': r.reasoning,
                    'details': r.details
                }
                for r in self.results
            ]
        }
        
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n[*] Report saved to: {output_path}")


def main():
    """CLI entry point for running evaluations"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run SQL evaluation tests")
    parser.add_argument("--variations", action="store_true", help="Run test case variations (slower)")
    args = parser.parse_args()
    
    runner = EvalRunner()
    summary = runner.run_all_evals(run_variations=args.variations)
    
    if summary:
        print(f"\n{'='*60}")
        print("EVALUATION SUMMARY")
        print(f"{'='*60}")
        print(f"Total Tests: {summary['total_tests']}")
        print(f"Passed: {summary['passed']}")
        print(f"Failed: {summary['failed']}")
        print(f"Pass Rate: {summary['pass_rate']:.1%}")
        print(f"Average Score: {summary['average_score']:.2f}")
        
        runner.save_report()
        
        # Exit with error code if pass rate is too low
        if summary['pass_rate'] < 0.5:
            print("\n[!] Pass rate below 50% - check regressions!")
            sys.exit(1)
        else:
            print("\n[*] Evaluations complete!")
            sys.exit(0)


if __name__ == "__main__":
    main()
