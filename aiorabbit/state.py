"""
State Manager
=============

"""
import asyncio
import inspect
import logging
import time
import typing

from aiorabbit import exceptions

STATE_UNINITIALIZED = 0x00
STATE_EXCEPTION = 0x01


class StateManager:
    """Base Class used to implement state management"""
    STATE_MAP: dict = {
        STATE_UNINITIALIZED: 'Uninitialized',
        STATE_EXCEPTION: 'Exception Raised'
    }

    STATE_TRANSITIONS: dict = {
        STATE_UNINITIALIZED: [STATE_EXCEPTION]
    }

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._logger = logging.getLogger(
            dict(inspect.getmembers(self))['__module__'])
        self._exception: typing.Optional[Exception] = None
        self._loop: asyncio.AbstractEventLoop = loop
        self._loop.set_exception_handler(self._on_exception)
        self._state: int = STATE_UNINITIALIZED
        self._state_start: float = self._loop.time()
        self._sticky_state = set({})
        self._waits: dict = {}

    @property
    def exception(self) -> typing.Optional[Exception]:
        """If an exception was set with the state, return the value"""
        return self._exception

    @property
    def state(self) -> str:
        """Return the current state as descriptive string"""
        return self.state_description(self._state)

    def state_description(self, state: int) -> str:
        """Return a state description for a given state"""
        return self.STATE_MAP[state]

    @property
    def time_in_state(self) -> float:
        """Return how long the current state has been active"""
        return self._loop.time() - self._state_start

    def _clear_sticky_state(self, value: int) -> None:
        try:
            self._sticky_state.remove(value)
        except KeyError:
            pass

    def _on_exception(self,
                      _loop: asyncio.AbstractEventLoop,
                      context: typing.Dict[str, typing.Any]) -> None:
        self._logger.debug('Exception on IOLoop: %r', context)
        self._set_state(STATE_EXCEPTION, context['exception'])

    def _set_state(self, value: int,
                   exc: typing.Optional[Exception] = None,
                   sticky: bool = False) -> None:
        if value == STATE_EXCEPTION or exc:
            self._logger.debug('Exception passed in with state: %r', exc)
            self._exception = exc
            self._state = STATE_EXCEPTION
        else:
            if value == self._state:
                pass
            elif value not in self.STATE_TRANSITIONS[self._state]:
                raise exceptions.StateTransitionError(
                    'Invalid state transition from {!r} to {!r}'.format(
                        self.state, self.state_description(value)))
            else:
                self._logger.debug(
                    'Transition to %r (%i) from %r (%i) after %.4f seconds '
                    '(Sticky: %r)', self.state_description(value), value,
                    self.state, self._state, self.time_in_state, sticky)
                self._state = value
                self._state_start = self._loop.time()
                if sticky:
                    self._sticky_state.add(value)
        if self._state in self._waits:
            self._waits[self._state].set()

    async def _wait_on_state(self, *args) -> None:
        """Wait on a specific state value to transition"""
        wait_id = time.monotonic_ns()
        self._waits[wait_id] = {}
        events, states = [], []
        for state in args:
            event = asyncio.Event()
            states.append(state)
            events.append((event, state))
            self._waits[state] = event
        self._logger.debug(
            'Waiter %r waiting on %s', wait_id, ', '.join(
                [self.state_description(s) for s in states]))
        while not self._exception:
            for event, state in events:
                if event.is_set():
                    self._logger.debug(
                        'Waiter %r wait on %r (%i) has finished', wait_id,
                        self.state_description(state), state)
                    del self._waits[wait_id]
                    return state
            await asyncio.sleep(0.001)
        exc = self._exception
        self._exception = None
        raise exc
