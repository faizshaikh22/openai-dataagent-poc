"""
Query History & Pattern Learning Module

Tracks successful queries to learn:
- Common join patterns between tables
- Typical filter patterns for specific columns
- Popular queries that can be suggested

Usage:
    from app.memory.query_history import query_history
    
    # Log a successful query
    query_history.log_query(
        question="Show me top paid employees",
        sql="SELECT ...",
        tables=["payroll"],
        execution_time_ms=150,
        success=True
    )
    
    # Get suggested joins for tables
    suggestions = query_history.get_join_suggestions(["orders", "customers"])
"""

import os
import json
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict


@dataclass
class QueryLog:
    """Represents a logged query"""
    id: str
    question: str
    sql: str
    tables: List[str]
    columns: List[str]
    timestamp: str
    execution_time_ms: int
    success: bool
    row_count: int
    user_id: Optional[str] = None


class QueryHistoryStore:
    """
    Stores and analyzes query history to learn patterns.
    
    Learned patterns include:
    - Which tables are commonly joined together
    - Common filter patterns for columns
    - Frequently asked questions (for suggestions)
    """
    
    def __init__(self, storage_dir: str = "data/memory"):
        self.storage_dir = Path(storage_dir)
        self.history_file = self.storage_dir / "query_history.json"
        self.patterns_file = self.storage_dir / "learned_patterns.json"
        
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache
        self._queries: List[QueryLog] = []
        self._patterns: Dict[str, Any] = {}
        
        self._load_history()
        self._load_patterns()
    
    def _load_history(self):
        """Load query history from disk"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                    self._queries = [QueryLog(**q) for q in data.get('queries', [])]
            except Exception as e:
                print(f"Error loading query history: {e}")
                self._queries = []
    
    def _load_patterns(self):
        """Load learned patterns from disk"""
        if self.patterns_file.exists():
            try:
                with open(self.patterns_file, 'r') as f:
                    self._patterns = json.load(f)
            except Exception as e:
                print(f"Error loading patterns: {e}")
                self._patterns = {}
    
    def _save_history(self):
        """Save query history to disk"""
        try:
            # Keep only last 1000 queries to prevent file bloat
            recent_queries = self._queries[-1000:]
            data = {
                'queries': [q.__dict__ for q in recent_queries],
                'last_updated': datetime.now().isoformat()
            }
            with open(self.history_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving query history: {e}")
    
    def _save_patterns(self):
        """Save learned patterns to disk"""
        try:
            with open(self.patterns_file, 'w') as f:
                json.dump(self._patterns, f, indent=2)
        except Exception as e:
            print(f"Error saving patterns: {e}")
    
    def _generate_id(self) -> str:
        """Generate unique ID"""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def _extract_columns_from_sql(self, sql: str) -> List[str]:
        """Extract column names from SQL"""
        # Simple regex to find column references
        # This is basic - could be improved with SQL parsing
        columns = set()
        
        # Find column names after SELECT, WHERE, GROUP BY, ORDER BY
        patterns = [
            r'(?:select|where|group by|order by|having)\s+([^\s,]+)',
            r'(\w+)\s*=\s*',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, sql.lower())
            for match in matches:
                # Filter out SQL keywords
                if match not in ['select', 'from', 'where', 'and', 'or', 'group', 'by', 'order', 'having', 'limit', 'join', 'on']:
                    columns.add(match)
        
        return list(columns)
    
    def _extract_join_conditions(self, sql: str) -> List[Tuple[str, str, str]]:
        """
        Extract join conditions from SQL.
        Returns list of (table1, table2, join_column) tuples.
        """
        joins = []
        sql_lower = sql.lower()
        
        # Pattern: table1 JOIN table2 ON table1.col = table2.col
        join_pattern = r'(\w+)\s+join\s+(\w+)\s+on\s+(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)'
        matches = re.findall(join_pattern, sql_lower)
        
        for match in matches:
            # match structure depends on regex groups
            pass  # Simplified - would need proper SQL parsing
        
        return joins
    
    def log_query(
        self,
        question: str,
        sql: str,
        tables: List[str],
        execution_time_ms: int = 0,
        success: bool = True,
        row_count: int = 0,
        user_id: Optional[str] = None
    ) -> QueryLog:
        """
        Log a query execution.
        
        Args:
            question: The natural language question
            sql: The generated SQL
            tables: Tables involved in the query
            execution_time_ms: How long the query took
            success: Whether the query executed successfully
            row_count: Number of rows returned
            user_id: Optional user identifier
        """
        columns = self._extract_columns_from_sql(sql)
        
        log = QueryLog(
            id=self._generate_id(),
            question=question,
            sql=sql,
            tables=tables,
            columns=columns,
            timestamp=datetime.now().isoformat(),
            execution_time_ms=execution_time_ms,
            success=success,
            row_count=row_count,
            user_id=user_id
        )
        
        self._queries.append(log)
        self._save_history()
        
        # Update patterns if query was successful
        if success:
            self._update_patterns(log)
        
        return log
    
    def _update_patterns(self, log: QueryLog):
        """Update learned patterns based on a successful query"""
        if 'join_patterns' not in self._patterns:
            self._patterns['join_patterns'] = {}
        
        if 'filter_patterns' not in self._patterns:
            self._patterns['filter_patterns'] = {}
        
        # Learn join patterns
        if len(log.tables) >= 2:
            table_key = ','.join(sorted(log.tables))
            if table_key not in self._patterns['join_patterns']:
                self._patterns['join_patterns'][table_key] = {
                    'count': 0,
                    'example_sql': log.sql,
                    'example_question': log.question
                }
            self._patterns['join_patterns'][table_key]['count'] += 1
        
        # Learn filter patterns for columns
        for col in log.columns:
            if col not in self._patterns['filter_patterns']:
                self._patterns['filter_patterns'][col] = {
                    'count': 0,
                    'examples': []
                }
            self._patterns['filter_patterns'][col]['count'] += 1
            
            # Store up to 3 example questions per column
            if len(self._patterns['filter_patterns'][col]['examples']) < 3:
                self._patterns['filter_patterns'][col]['examples'].append(log.question)
        
        self._save_patterns()
    
    def get_join_suggestions(self, tables: List[str]) -> List[Dict[str, Any]]:
        """
        Get suggestions for joining the given tables.
        
        Returns:
            List of suggestions with example SQL
        """
        suggestions = []
        
        if len(tables) < 2:
            return suggestions
        
        table_key = ','.join(sorted(tables))
        
        # Exact match
        if table_key in self._patterns.get('join_patterns', {}):
            pattern = self._patterns['join_patterns'][table_key]
            suggestions.append({
                'tables': tables,
                'confidence': 'high',
                'example_sql': pattern['example_sql'],
                'example_question': pattern['example_question'],
                'times_used': pattern['count']
            })
        
        # Partial matches (if asking for subset of known joins)
        for known_key, pattern in self._patterns.get('join_patterns', {}).items():
            known_tables = set(known_key.split(','))
            if set(tables).issubset(known_tables):
                suggestions.append({
                    'tables': known_tables,
                    'confidence': 'medium',
                    'example_sql': pattern['example_sql'],
                    'example_question': pattern['example_question'],
                    'times_used': pattern['count']
                })
        
        return suggestions[:3]  # Return top 3
    
    def get_filter_suggestions(self, column: str) -> Dict[str, Any]:
        """
        Get filter suggestions for a specific column.
        
        Returns:
            Dictionary with common filter patterns
        """
        return self._patterns.get('filter_patterns', {}).get(column, {
            'count': 0,
            'examples': []
        })
    
    def get_popular_queries(self, table: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get most popular/recent queries.
        
        Args:
            table: Filter by specific table
            limit: Number of queries to return
        """
        # Get successful queries from last 30 days
        cutoff = datetime.now() - timedelta(days=30)
        
        recent_queries = [
            q for q in self._queries
            if q.success and datetime.fromisoformat(q.timestamp) > cutoff
            and (table is None or table in q.tables)
        ]
        
        # Group by question similarity (simplified)
        grouped = defaultdict(list)
        for q in recent_queries:
            # Simple grouping by first 3 words
            key = ' '.join(q.question.lower().split()[:3])
            grouped[key].append(q)
        
        # Return most common patterns
        popular = []
        for key, queries in sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True)[:limit]:
            popular.append({
                'question_pattern': key,
                'count': len(queries),
                'example_question': queries[0].question,
                'example_sql': queries[0].sql,
                'tables': queries[0].tables
            })
        
        return popular
    
    def get_context_for_question(self, question: str, tables: List[str] = None) -> str:
        """
        Get context string with learned patterns for the LLM.
        
        Returns:
            Formatted string with relevant patterns
        """
        context_parts = []
        
        # Join suggestions
        if tables and len(tables) >= 2:
            join_suggestions = self.get_join_suggestions(tables)
            if join_suggestions:
                context_parts.append("### Common Join Patterns\n")
                for i, sugg in enumerate(join_suggestions[:2], 1):
                    context_parts.append(f"{i}. Tables {sugg['tables']} are commonly joined together.")
                    context_parts.append(f"   Example: {sugg['example_question']}")
                    context_parts.append(f"   SQL pattern: {sugg['example_sql'][:100]}...\n")
        
        # Popular queries for these tables
        if tables:
            popular = self.get_popular_queries(table=tables[0], limit=3)
            if popular:
                context_parts.append("### Similar Questions Asked Previously\n")
                for p in popular:
                    context_parts.append(f"- \"{p['example_question']}\"")
        
        return '\n'.join(context_parts) if context_parts else ""


# Global instance
query_history = QueryHistoryStore()
