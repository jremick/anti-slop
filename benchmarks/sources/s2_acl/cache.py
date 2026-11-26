"""In-memory ACL decision cache."""

from __future__ import annotations


class DecisionCache:
    """Caches boolean ACL decisions for repeat requests."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], bool] = {}

    @staticmethod
    def make_key(user_id: str, resource_path: str) -> tuple[str, str]:
        return (user_id, resource_path)

    def get(self, user_id: str, resource_path: str) -> bool | None:
        return self._entries.get(self.make_key(user_id, resource_path))

    def set(self, user_id: str, resource_path: str, allowed: bool) -> None:
        self._entries[self.make_key(user_id, resource_path)] = allowed

    def clear(self) -> None:
        self._entries.clear()
