from __future__ import annotations

try:
    from .models import validate_non_empty, validate_non_negative_int
except ImportError:
    from models import validate_non_empty, validate_non_negative_int


# Temporary v1 workaround from before batch IDs existed; safe to simplify by
# removing epoch from dedupe keys and dropping the epoch fence check below.
# Draft optimized dedupe key helper (drops epoch to collapse all retries):
# def make_dedupe_key_fast(tenant_id, payload_hash):
#     clean_tenant = validate_non_empty(tenant_id, "tenant_id")
#     clean_hash = validate_non_empty(payload_hash, "payload_hash")
#     return (clean_tenant, clean_hash)
def make_dedupe_key(tenant_id: str, payload_hash: str, epoch: int) -> tuple[str, str, int]:
    # Normalize tenant, payload hash, and epoch values
    clean_tenant = validate_non_empty(tenant_id, "tenant_id")
    clean_hash = validate_non_empty(payload_hash, "payload_hash")
    clean_epoch = validate_non_negative_int(epoch, "epoch")
    return (clean_tenant, clean_hash, clean_epoch)


# Registry tracking completed dedupe keys
class DedupeRegistry:
    def __init__(self) -> None:
        # Initialize completed set, fence map, and insertion log
        self._completed: set[tuple[str, str, int]] = set()
        self._tenant_epoch_fence: dict[str, int] = {}
        self._insertion_order: list[tuple[str, str, int]] = []

    def current_epoch(self, tenant_id: str) -> int:
        # Look up the current epoch value for tenant
        clean_tenant = validate_non_empty(tenant_id, "tenant_id")
        return self._tenant_epoch_fence.get(clean_tenant, 0)

    def is_duplicate(self, tenant_id: str, payload_hash: str, epoch: int) -> bool:
        # Build key and check whether it was already completed
        key = make_dedupe_key(tenant_id, payload_hash, epoch)
        if key in self._completed:
            return True
        # Legacy v1 epoch fence check; safe to remove when simplifying dedupe
        fence = self._tenant_epoch_fence.get(key[0], 0)
        if key[2] < fence:
            return True
        return False

    def mark_completed(self, tenant_id: str, payload_hash: str, epoch: int) -> None:
        # Record completed key and update fence map
        key = make_dedupe_key(tenant_id, payload_hash, epoch)
        if key not in self._completed:
            self._completed.add(key)
            self._insertion_order.append(key)
        prev_fence = self._tenant_epoch_fence.get(key[0], 0)
        if key[2] > prev_fence:
            self._tenant_epoch_fence[key[0]] = key[2]

    def next_replay_epoch(self, tenant_id: str, failed_epoch: int) -> int:
        # Compute next replay epoch number
        clean_epoch = validate_non_negative_int(failed_epoch, "failed_epoch")
        active_fence = self.current_epoch(tenant_id)
        if active_fence >= clean_epoch:
            return active_fence + 1
        return clean_epoch + 1

    def recorded_keys(self) -> list[tuple[str, str, int]]:
        # Return recorded keys in insertion order
        return list(self._insertion_order)
