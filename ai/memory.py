from typing import Dict, List, Tuple

class ContextMemory:
    def __init__(self) -> None:
        # Key: (channel_id, user_id) -> Value: List of dialogue dicts
        self._memory: Dict[Tuple[int, int], List[Dict[str, str]]] = {}
        self.max_turns: int = 10

    def get_context(self, channel_id: int, user_id: int) -> List[Dict[str, str]]:
        key = (channel_id, user_id)
        if key not in self._memory:
            self._memory[key] = []
        return self._memory[key]

    def add_message(self, channel_id: int, user_id: int, role: str, content: str) -> None:
        key = (channel_id, user_id)
        if key not in self._memory:
            self._memory[key] = []
        
        self._memory[key].append({"role": role, "content": content})
        
        # Keep window within boundaries (2 structural frames per turn: user & assistant)
        if len(self._memory[key]) > self.max_turns * 2:
            self._memory[key] = self._memory[key][-self.max_turns * 2:]

    def clear_context(self, channel_id: int, user_id: int) -> None:
        key = (channel_id, user_id)
        if key in self._memory:
            self._memory[key] = []

    def clear_channel_context(self, channel_id: int) -> None:
        keys_to_clear = [k for k in self._memory.keys() if k[0] == channel_id]
        for k in keys_to_clear:
            self._memory[k] = []

# Instantiate the manager safely below the class layout
memory_manager = ContextMemory()
