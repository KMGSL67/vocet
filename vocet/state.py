"""The app's explicit state machine.

    LOADING -> IDLE -> STARTING -> LISTENING -> PROCESSING -> INSERTING -> IDLE
       ^         ^         |            |             |             |
       |         |         v            v             v             v
   (new model) PAUSED    IDLE         IDLE  <-  ERROR  <-----------+

STARTING: the keys are pressed and the microphone is opening on its own thread (a built-in
laptop mic can take most of a second). It becomes LISTENING when the stream runs.

Only the transitions listed in ALLOWED are legal. Anything else is a bug, and it
is refused and logged instead of silently corrupting state. Because the hotkey
is only acted on in IDLE, two transcriptions can never overlap.
"""

import logging
from enum import Enum, auto

log = logging.getLogger(__name__)


class State(Enum):
    LOADING = auto()
    IDLE = auto()
    STARTING = auto()
    LISTENING = auto()
    PROCESSING = auto()
    INSERTING = auto()
    ERROR = auto()
    PAUSED = auto()


ALLOWED = {
    State.LOADING: {State.IDLE, State.ERROR},
    State.IDLE: {State.STARTING, State.PAUSED, State.LOADING},      # LOADING = switching model
    State.STARTING: {State.LISTENING, State.IDLE, State.ERROR},    # IDLE = let go before the mic was ready
    State.LISTENING: {State.PROCESSING, State.IDLE, State.ERROR},  # IDLE = cancelled / too short
    State.PROCESSING: {State.INSERTING, State.IDLE, State.ERROR},  # IDLE = no speech found
    State.INSERTING: {State.IDLE, State.ERROR},
    State.ERROR: {State.IDLE, State.LOADING},
    State.PAUSED: {State.IDLE},
}


class StateMachine:
    def __init__(self, on_change=None):
        self.state = State.LOADING
        self.on_change = on_change
        self.allowed = ALLOWED

    def go(self, new) -> bool:
        if new not in self.allowed[self.state]:
            log.warning("refused illegal transition %s -> %s", self.state.name, new.name)
            return False
        old, self.state = self.state, new
        log.debug("%s -> %s", old.name, new.name)
        if self.on_change:
            self.on_change(old, new)
        return True
