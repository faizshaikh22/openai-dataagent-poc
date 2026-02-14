from abc import ABC, abstractmethod
from typing import Dict, List, Any

class DatabaseAdapter(ABC):
    
    @abstractmethod
    def get_schema(self, table_name: str) -> str:
        pass

    @abstractmethod
    def execute_query(self, query: str) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def get_rich_context(self) -> str:
        pass
