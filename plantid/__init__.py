"""Plant.id integration package for solar ESP32 fertigation."""

from .client import PlantIdClient, PlantIdError
from .decision import DoseDecision, decide_dose

__all__ = [
    "PlantIdClient",
    "PlantIdError",
    "DoseDecision",
    "decide_dose",
]
