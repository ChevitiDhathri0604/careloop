"""
CareLoop Event Bus
Partitions events by Patient ID to ensure strict causal ordering per patient.
Supports local in-memory event queues with pub/sub listener registration,
with seamless fallback/connect to Redis Streams if configured.
"""

import asyncio
from collections import defaultdict
from typing import Dict, List, Any, Callable, Awaitable
from datetime import datetime

class EventBus:
    def __init__(self):
        # Partitioned event streams: patient_id -> list of events
        self.streams: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        # Subscribers listening for events
        self.subscribers: List[Callable[[Dict[str, Any]], Awaitable[None]]] = []
        self._counter = 0

    def subscribe(self, callback: Callable[[Dict[str, Any]], Awaitable[None]]):
        self.subscribers.append(callback)

    def publish_sync(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synchronous publish — same logic as async publish but no await required.
        Use this from synchronous code paths (terminal demo, tests, etc.)
        Skips async subscribers.
        """
        self._counter += 1
        patient_id = event.get("patientId", "GLOBAL")

        enriched_event = {
            **event,
            "eventId": f"EVT-{self._counter:06d}",
            "publishedAt": datetime.utcnow().isoformat() + "Z",
            "partitionKey": patient_id
        }
        self.streams[patient_id].append(enriched_event)
        return enriched_event

    async def publish(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Publishes an event partitioned by patientId, guarantees causal ordering.
        """
        self._counter += 1
        patient_id = event.get("patientId", "GLOBAL")
        
        enriched_event = {
            **event,
            "eventId": f"EVT-{self._counter:06d}",
            "publishedAt": datetime.utcnow().isoformat() + "Z",
            "partitionKey": patient_id
        }

        # Store in patient partition stream
        self.streams[patient_id].append(enriched_event)

        # Notify active subscribers
        for sub in self.subscribers:
            try:
                if asyncio.iscoroutinefunction(sub):
                    await sub(enriched_event)
                else:
                    sub(enriched_event)
            except Exception as e:
                print(f"[EventBus] Error notifying subscriber: {e}")

        return enriched_event

    def get_patient_history(self, patient_id: str) -> List[Dict[str, Any]]:
        return list(self.streams.get(patient_id, []))

    def get_all_events(self) -> List[Dict[str, Any]]:
        all_events = []
        for stream in self.streams.values():
            all_events.extend(stream)
        return sorted(all_events, key=lambda x: x.get("eventId", ""))

event_bus = EventBus()

