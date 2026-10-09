"""Free-form clinical investigations with trusted capability boundaries."""

from agents.freeform.contracts import Limits, Scope
from agents.freeform.runtime import FreeFormSpecialistRuntime

__all__ = ["FreeFormSpecialistRuntime", "Limits", "Scope"]
