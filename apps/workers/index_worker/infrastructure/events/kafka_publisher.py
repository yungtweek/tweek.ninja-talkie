from __future__ import annotations
import json
from ...domain.ports import EventPublisher

class KafkaEventPublisher(EventPublisher):
    def __init__(self, producer, topic_prefix: str = "rag"):
        self.producer = producer
        self.topic_prefix = topic_prefix

    async def publish(self, topic: str, payload: dict) -> None:
        full_topic = f"{self.topic_prefix}.{topic}"
        await self.producer.send_and_wait(full_topic, json.dumps(payload).encode("utf-8"))