"""Public import surface for the deterministic V6 event classifier.

Recognition and direction assignment live in :mod:`modeling.v6.event_states`.
This compatibility facade keeps one authoritative runtime implementation.
"""

from modeling.v6.event_states import (
    assign_direction,
    classify_event,
    classify_text,
    direction_for_event_type,
    recognize_text,
    state_direction,
)

__all__ = (
    "assign_direction",
    "classify_event",
    "classify_text",
    "direction_for_event_type",
    "recognize_text",
    "state_direction",
)
