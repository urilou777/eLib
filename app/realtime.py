"""In-memory state and broadcasting for live mobile basket updates."""

import json
import threading
import time


class LiveHub:
    """Hub temps réel (SSE) & registre en mémoire des paniers actifs."""

    def __init__(self):
        self.listeners = set()
        self.lock = threading.Lock()
        self.active_baskets = {}

    def register(self, loop, queue):
        with self.lock:
            self.listeners.add((loop, queue))

    def unregister(self, loop, queue):
        with self.lock:
            self.listeners.discard((loop, queue))

    def broadcast(self, event_type: str, data: dict):
        payload = json.dumps({"type": event_type, "data": data, "timestamp": time.time()})
        with self.lock:
            dead = []
            for loop, queue in list(self.listeners):
                try:
                    loop.call_soon_threadsafe(queue.put_nowait, payload)
                except Exception:
                    dead.append((loop, queue))
            for listener in dead:
                self.listeners.discard(listener)

    def update_basket(self, device_id: str, basket_data: dict, action: dict = None):
        now = time.time()
        basket_data["updated_at"] = now
        if basket_data.get("qty", 0) > 0 or basket_data.get("items"):
            basket_data["status"] = "scanning"
        else:
            basket_data["status"] = "connected"

        with self.lock:
            user_name = (basket_data.get("user_name") or "").strip().casefold()
            device_key = basket_data.get("device_key") or ""
            for active_id, active in list(self.active_baskets.items()):
                if active_id == device_id:
                    continue
                same_user = user_name and (
                    (active.get("user_name") or "").strip().casefold() == user_name
                )
                same_device = device_key and (
                    active.get("device_key") == device_key
                )
                if same_user or same_device:
                    del self.active_baskets[active_id]
            self.active_baskets[device_id] = basket_data
            self._cleanup_expired()
            active_list = self._prepare_baskets()

        self.broadcast("baskets_updated", {
            "baskets": active_list,
            "action": action,
            "device_id": device_id,
            "user_name": basket_data.get("user_name"),
        })

    def remove_basket(self, device_id: str, action: dict = None):
        with self.lock:
            action_type = (action or {}).get("type", "")
            if action_type in ("session_closed", "disconnected", "unpaired"):
                removed = self.active_baskets.pop(device_id, None)
            elif device_id in self.active_baskets:
                removed = self.active_baskets[device_id]
                removed["qty"] = 0
                removed["total"] = 0.0
                removed["items"] = []
                removed["status"] = "connected"
                removed["updated_at"] = time.time()
            else:
                removed = None

            self._cleanup_expired()
            active_list = self._prepare_baskets()

        if removed:
            self.broadcast("baskets_updated", {
                "baskets": active_list,
                "action": action or {"type": "cart_cleared"},
                "device_id": device_id,
                "user_name": removed.get("user_name"),
            })

    def get_active_baskets(self):
        with self.lock:
            self._cleanup_expired()
            return self._prepare_baskets()

    def _prepare_baskets(self):
        now = time.time()
        result = []
        for basket in self.active_baskets.values():
            item = dict(basket)
            age = now - item.get("updated_at", now)
            item["idle_sec"] = int(age)
            item["state"] = "idle" if age > 45 else "active"
            result.append(item)
        return result

    def _cleanup_expired(self):
        cutoff = time.time() - 150
        expired = [
            device_id
            for device_id, basket in self.active_baskets.items()
            if basket.get("updated_at", 0) < cutoff
        ]
        for device_id in expired:
            del self.active_baskets[device_id]


live_hub = LiveHub()
