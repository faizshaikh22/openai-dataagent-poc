"""
SQL Memory System

Manages learned corrections and patterns to improve SQL generation quality over time.
Memories are scoped to specific tables/columns and can be global or user-specific.

Usage:
    from app.memory.sql_memory import sql_memory
    
    # Add a correction
    sql_memory.add_memory(
        pattern="agency_name LIKE '%POLICE%'",
        correction="When user asks for 'Police Department', use LIKE for variations",
        applies_to_tables=["payroll"],
        applies_to_columns=["agency_name"],
        memory_type="filter_pattern"
    )
    
    # Get relevant memories for a query
    memories = sql_memory.get_relevant_memories(
        question="Show me Police Department employees",
        tables=["payroll"]
    )
"""

import os
import json
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


@dataclass
class SQLMemory:
    """Represents a single SQL memory/correction"""
    id: str
    pattern: str  # The SQL pattern or user question pattern this applies to
    correction: str  # The correction or guidance
    applies_to_tables: List[str]
    applies_to_columns: List[str]
    memory_type: str  # 'filter_pattern', 'join_pattern', 'calculation', 'semantic_mapping'
    scope: str  # 'global' or 'user:{user_id}'
    created_at: str
    updated_at: str
    use_count: int = 0
    success_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SQLMemory':
        return cls(**data)


class SQLMemoryStore:
    """
    Stores and retrieves SQL memories/corrections.
    
    Memories help the agent learn:
    - Filter patterns (e.g., "Police Department" -> LIKE '%POLICE%')
    - Join patterns (e.g., "orders and customers" -> join on customer_id)
    - Calculation patterns (e.g., "average salary" -> handle $ signs)
    - Semantic mappings (e.g., "NYPD" -> "Police Department")
    """
    
    def __init__(self, storage_dir: str = "data/memory"):
        self.storage_dir = Path(storage_dir)
        self.global_memory_file = self.storage_dir / "global_memory.json"
        self.user_memory_dir = self.storage_dir / "users"
        
        # Ensure directories exist
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.user_memory_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache for loaded memories
        self._global_memories: List[SQLMemory] = []
        self._user_memories: Dict[str, List[SQLMemory]] = {}
        
        self._load_global_memories()
    
    def _load_global_memories(self):
        """Load global memories from disk"""
        if self.global_memory_file.exists():
            try:
                with open(self.global_memory_file, 'r') as f:
                    data = json.load(f)
                    self._global_memories = [
                        SQLMemory.from_dict(m) for m in data.get('memories', [])
                    ]
            except Exception as e:
                print(f"Error loading global memories: {e}")
                self._global_memories = []
    
    def _load_user_memories(self, user_id: str) -> List[SQLMemory]:
        """Load user-specific memories from disk"""
        if user_id in self._user_memories:
            return self._user_memories[user_id]
        
        user_file = self.user_memory_dir / f"{user_id}.json"
        if user_file.exists():
            try:
                with open(user_file, 'r') as f:
                    data = json.load(f)
                    memories = [SQLMemory.from_dict(m) for m in data.get('memories', [])]
                    self._user_memories[user_id] = memories
                    return memories
            except Exception as e:
                print(f"Error loading user memories for {user_id}: {e}")
        
        self._user_memories[user_id] = []
        return []
    
    def _save_global_memories(self):
        """Save global memories to disk"""
        try:
            data = {
                'memories': [m.to_dict() for m in self._global_memories],
                'last_updated': datetime.now().isoformat()
            }
            with open(self.global_memory_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving global memories: {e}")
    
    def _save_user_memories(self, user_id: str):
        """Save user-specific memories to disk"""
        try:
            memories = self._user_memories.get(user_id, [])
            data = {
                'memories': [m.to_dict() for m in memories],
                'last_updated': datetime.now().isoformat()
            }
            user_file = self.user_memory_dir / f"{user_id}.json"
            with open(user_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving user memories for {user_id}: {e}")
    
    def _generate_id(self) -> str:
        """Generate a unique memory ID"""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def add_memory(
        self,
        pattern: str,
        correction: str,
        applies_to_tables: List[str] = None,
        applies_to_columns: List[str] = None,
        memory_type: str = "general",
        scope: str = "global",
        user_id: Optional[str] = None
    ) -> SQLMemory:
        """
        Add a new memory/correction.
        
        Args:
            pattern: The SQL pattern or question pattern this applies to
            correction: The correction text or guidance
            applies_to_tables: List of table names this applies to
            applies_to_columns: List of column names this applies to
            memory_type: Type of memory ('filter_pattern', 'join_pattern', 'calculation', 'semantic_mapping')
            scope: 'global' or 'user'
            user_id: Required if scope is 'user'
        """
        now = datetime.now().isoformat()
        
        memory = SQLMemory(
            id=self._generate_id(),
            pattern=pattern,
            correction=correction,
            applies_to_tables=applies_to_tables or [],
            applies_to_columns=applies_to_columns or [],
            memory_type=memory_type,
            scope=f"user:{user_id}" if scope == "user" and user_id else "global",
            created_at=now,
            updated_at=now,
            use_count=0,
            success_count=0
        )
        
        if scope == "global":
            self._global_memories.append(memory)
            self._save_global_memories()
        else:
            if not user_id:
                raise ValueError("user_id is required for user-scoped memories")
            if user_id not in self._user_memories:
                self._user_memories[user_id] = []
            self._user_memories[user_id].append(memory)
            self._save_user_memories(user_id)
        
        return memory
    
    def get_relevant_memories(
        self,
        question: str,
        tables: List[str] = None,
        columns: List[str] = None,
        user_id: Optional[str] = None
    ) -> List[SQLMemory]:
        """
        Get memories relevant to a specific question.
        
        Args:
            question: The natural language question
            tables: Tables involved in the query
            columns: Columns involved in the query
            user_id: If provided, also includes user's personal memories
        
        Returns:
            List of relevant SQLMemory objects
        """
        relevant = []
        
        # Always include global memories
        memories_to_check = self._global_memories.copy()
        
        # Add user memories if user_id provided
        if user_id:
            memories_to_check.extend(self._load_user_memories(user_id))
        
        question_lower = question.lower()
        tables_set = set(tables or [])
        columns_set = set(columns or [])
        
        for memory in memories_to_check:
            relevance_score = 0
            
            # Check if question matches pattern
            pattern_lower = memory.pattern.lower()
            
            # Exact match or substring match
            if pattern_lower in question_lower or question_lower in pattern_lower:
                relevance_score += 3
            
            # Word-level matching
            pattern_words = set(pattern_lower.split())
            question_words = set(question_lower.split())
            common_words = pattern_words & question_words
            if len(common_words) > 0:
                relevance_score += len(common_words)
            
            # Table matching
            if tables_set and memory.applies_to_tables:
                if tables_set & set(memory.applies_to_tables):
                    relevance_score += 2
            
            # Column matching
            if columns_set and memory.applies_to_columns:
                if columns_set & set(memory.applies_to_columns):
                    relevance_score += 2
            
            # Memory type priority
            if memory.memory_type == "semantic_mapping":
                relevance_score += 1  # Higher priority for semantic mappings
            
            if relevance_score > 0:
                relevant.append((memory, relevance_score))
        
        # Sort by relevance score (descending)
        relevant.sort(key=lambda x: x[1], reverse=True)
        
        # Return top 5 most relevant
        return [m for m, _ in relevant[:5]]
    
    def get_memory_context_string(
        self,
        question: str,
        tables: List[str] = None,
        columns: List[str] = None,
        user_id: Optional[str] = None
    ) -> str:
        """
        Get a formatted string of relevant memories for LLM context.
        
        Returns:
            Formatted string with memory guidance
        """
        memories = self.get_relevant_memories(question, tables, columns, user_id)
        
        if not memories:
            return ""
        
        context = "### Learned Patterns & Corrections\n"
        for i, memory in enumerate(memories, 1):
            context += f"{i}. {memory.correction}\n"
            if memory.applies_to_tables:
                context += f"   Applies to tables: {', '.join(memory.applies_to_tables)}\n"
            context += f"   Type: {memory.memory_type}\n"
        
        return context
    
    def record_usage(self, memory_id: str, success: bool = True):
        """Record that a memory was used and whether it helped"""
        # Search in global memories
        for memory in self._global_memories:
            if memory.id == memory_id:
                memory.use_count += 1
                if success:
                    memory.success_count += 1
                memory.updated_at = datetime.now().isoformat()
                self._save_global_memories()
                return
        
        # Search in user memories
        for user_id, memories in self._user_memories.items():
            for memory in memories:
                if memory.id == memory_id:
                    memory.use_count += 1
                    if success:
                        memory.success_count += 1
                    memory.updated_at = datetime.now().isoformat()
                    self._save_user_memories(user_id)
                    return
    
    def list_all_memories(self, scope: str = "global", user_id: Optional[str] = None) -> List[SQLMemory]:
        """List all memories (for management UI)"""
        if scope == "global":
            return self._global_memories
        elif scope == "user" and user_id:
            return self._load_user_memories(user_id)
        else:
            return self._global_memories + [
                m for memories in self._user_memories.values() for m in memories
            ]
    
    def delete_memory(self, memory_id: str, user_id: Optional[str] = None) -> bool:
        """Delete a memory by ID"""
        # Try global first
        for i, memory in enumerate(self._global_memories):
            if memory.id == memory_id:
                self._global_memories.pop(i)
                self._save_global_memories()
                return True
        
        # Try user memories
        if user_id and user_id in self._user_memories:
            memories = self._user_memories[user_id]
            for i, memory in enumerate(memories):
                if memory.id == memory_id:
                    memories.pop(i)
                    self._save_user_memories(user_id)
                    return True
        
        return False


# Global instance
sql_memory = SQLMemoryStore()


def initialize_default_memories():
    """Initialize with some common patterns"""
    defaults = [
        {
            "pattern": "Police Department",
            "correction": "When filtering for 'Police Department', use `agency_name LIKE '%POLICE%'` to catch variations like 'POLICE DEPARTMENT', 'NYPD', etc.",
            "applies_to_tables": ["payroll"],
            "applies_to_columns": ["agency_name"],
            "memory_type": "filter_pattern"
        },
        {
            "pattern": "average salary",
            "correction": "Salary fields contain '$' symbols and are TEXT. Always use `CAST(REPLACE(salary_col, '$', '') AS REAL)` for calculations.",
            "applies_to_tables": ["payroll"],
            "applies_to_columns": ["base_salary", "regular_gross_paid", "total_ot_paid", "total_other_pay"],
            "memory_type": "calculation"
        },
        {
            "pattern": "top N highest",
            "correction": "For 'top N' queries, use `ORDER BY column DESC LIMIT N`. Remember to handle ties appropriately.",
            "applies_to_tables": [],
            "applies_to_columns": [],
            "memory_type": "general"
        },
        {
            "pattern": "NYPD",
            "correction": "'NYPD' refers to the New York Police Department. Map to `agency_name LIKE '%POLICE%'`",
            "applies_to_tables": ["payroll"],
            "applies_to_columns": ["agency_name"],
            "memory_type": "semantic_mapping"
        },
        {
            "pattern": "Fire Department",
            "correction": "When filtering for 'Fire Department', use `agency_name LIKE '%FIRE%'` to catch variations.",
            "applies_to_tables": ["payroll"],
            "applies_to_columns": ["agency_name"],
            "memory_type": "filter_pattern"
        }
    ]
    
    for mem_data in defaults:
        # Check if already exists
        exists = any(
            m.pattern == mem_data["pattern"] and m.memory_type == mem_data["memory_type"]
            for m in sql_memory._global_memories
        )
        if not exists:
            sql_memory.add_memory(**mem_data)
            print(f"Added default memory: {mem_data['pattern']}")


# Initialize on module load
if __name__ != "__main__":
    initialize_default_memories()
