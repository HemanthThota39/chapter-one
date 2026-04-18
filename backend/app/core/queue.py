"""Azure Service Bus queue client — Managed Identity auth.

Thin wrapper around azure-servicebus so our code stays provider-agnostic
if we ever swap to Redis Streams / Kafka / etc.
"""

from __future__ import annotations

import json
import logging

from azure.identity.aio import DefaultAzureCredential
from azure.servicebus.aio import ServiceBusClient
from azure.servicebus import ServiceBusMessage

from app.config import get_settings

log = logging.getLogger(__name__)


class AnalysisQueueClient:
    """Sender-side client used by the API to enqueue analysis jobs."""

    def __init__(self) -> None:
        settings = get_settings()
        self._namespace = settings.service_bus_namespace
        self._queue = settings.service_bus_queue_analyses
        self._cred = DefaultAzureCredential()
        self._client: ServiceBusClient | None = None

    async def _get(self) -> ServiceBusClient:
        if self._client is None:
            if not self._namespace:
                raise RuntimeError("SERVICE_BUS_NAMESPACE not configured")
            self._client = ServiceBusClient(
                fully_qualified_namespace=self._namespace,
                credential=self._cred,
            )
        return self._client

    async def enqueue_analysis(self, *, analysis_id: str, owner_id: str) -> None:
        client = await self._get()
        async with client.get_queue_sender(self._queue) as sender:
            msg = ServiceBusMessage(
                body=json.dumps({"analysis_id": analysis_id, "owner_id": owner_id}),
                content_type="application/json",
                message_id=analysis_id,  # de-dup if same id submitted twice
            )
            await sender.send_messages(msg)
        log.info("Enqueued analysis %s", analysis_id)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None


_queue: AnalysisQueueClient | None = None


def get_queue() -> AnalysisQueueClient:
    global _queue
    if _queue is None:
        _queue = AnalysisQueueClient()
    return _queue
