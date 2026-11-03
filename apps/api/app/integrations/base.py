from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(slots=True)
class NormalizedObservation:
    external_animal_id: str
    kind: str
    value: float
    unit: str
    observed_at: datetime
    source_event_id: str | None = None
    metadata: dict = field(default_factory=dict)


class IntegrationAdapter(Protocol):
    provider: str

    async def pull(self, stream: str, watermark: str | None) -> tuple[list[NormalizedObservation], str | None]: ...
