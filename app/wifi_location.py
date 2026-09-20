from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class WiFiClientObservation:
    property_id: str
    client_identifier: str
    access_point_identifier: str
    observed_at: int
    source: str = "mock"
    rssi: int | None = None
    controller: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


class WiFiLocationProvider(Protocol):
    def current_observations(self, property_id: str) -> list[WiFiClientObservation]:
        """Return current AP association observations for a property."""


class MockWiFiLocationProvider:
    def __init__(self) -> None:
        self._observations: list[WiFiClientObservation] = []

    def add_observation(self, observation: WiFiClientObservation) -> None:
        self._observations.append(observation)

    def current_observations(self, property_id: str) -> list[WiFiClientObservation]:
        return [item for item in self._observations if item.property_id == property_id]
