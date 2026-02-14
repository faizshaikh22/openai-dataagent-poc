"""
Persistent Conversation Storage

Manages conversation history using JSON files to ensure persistence across server restarts.
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

class ConversationStore:
    def __init__(self, storage_dir: str = "data/conversations"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, conversation_id: str) -> Path:
        # Sanitize ID just in case
        safe_id = "".join(c for c in conversation_id if c.isalnum() or c in ('-', '_'))
        return self.storage_dir / f"{safe_id}.json"

    def save_conversation(self, conversation_id: str, messages: List[Dict[str, str]]):
        """Save conversation messages to disk"""
        file_path = self._get_file_path(conversation_id)
        
        data = {
            "id": conversation_id,
            "last_updated": datetime.now().isoformat(),
            "messages": messages
        }
        
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving conversation {conversation_id}: {e}")

    def get_conversation(self, conversation_id: str) -> List[Dict[str, str]]:
        """Load conversation messages from disk"""
        file_path = self._get_file_path(conversation_id)
        
        if not file_path.exists():
            return []
            
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                return data.get("messages", [])
        except Exception as e:
            print(f"Error loading conversation {conversation_id}: {e}")
            return []

    def list_conversations(self) -> List[Dict[str, Any]]:
        """List all conversations with metadata"""
        conversations = []
        
        if not self.storage_dir.exists():
            return []
            
        for file_path in self.storage_dir.glob("*.json"):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    
                messages = data.get("messages", [])
                if not messages:
                    continue
                    
                # Find title from first user message
                title = "New Conversation"
                for msg in messages:
                    if msg["role"] == "user":
                        content = msg["content"]
                        title = content[:30] + "..." if len(content) > 30 else content
                        break
                
                conversations.append({
                    "id": data.get("id", file_path.stem),
                    "title": title,
                    "last_updated": data.get("last_updated", ""),
                    "message_count": len(messages)
                })
            except Exception as e:
                print(f"Error reading conversation file {file_path}: {e}")
        
        # Sort by last updated desc
        conversations.sort(key=lambda x: x.get("last_updated", ""), reverse=True)
        return conversations

    def clear_conversation(self, conversation_id: str):
        """Delete a conversation"""
        file_path = self._get_file_path(conversation_id)
        if file_path.exists():
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Error deleting conversation {conversation_id}: {e}")

# Global instance
conversation_store = ConversationStore()
