"""
Implements the AMQP Protocol

"""
import asyncio
import logging
import typing

from pamqp import exceptions, frame

LOGGER = logging.getLogger(__name__)


class AMQP(asyncio.Protocol):

    def __init__(self,
                 on_connected: callable,
                 on_disconnected: callable,
                 on_frame_received: callable):
        self.buffer: bytes = b''
        self.loop = asyncio.get_running_loop()
        self.on_connected = on_connected
        self.on_disconnected = on_disconnected
        self.on_frame_received = on_frame_received
        self.transport: typing.Optional[asyncio.Transport] = None

    def connection_made(self, transport) -> typing.NoReturn:
        self.transport = transport
        self.loop.call_soon(asyncio.ensure_future, self.on_connected())

    def connection_lost(self, exc: typing.Optional[Exception]) \
            -> typing.NoReturn:
        self.loop.call_soon(asyncio.ensure_future, self.on_disconnected())

    def data_received(self, data: bytes) -> typing.NoReturn:
        self.buffer += data
        while self.buffer:
            try:
                count, channel, value = frame.unmarshal(self.buffer)
            except exceptions.UnmarshalingException:
                break
            else:
                LOGGER.debug('Received frame: %r', value)
                self.buffer = self.buffer[count:]
                self.loop.call_soon(asyncio.ensure_future,
                                    self.on_frame_received(channel, value))
                break

    def pause_writing(self) -> typing.NoReturn:
        LOGGER.critical('Should pause writing')

    def resume_writing(self) -> typing.NoReturn:
        LOGGER.info('Can resume writing')