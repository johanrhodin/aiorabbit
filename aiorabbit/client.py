# coding: utf-8
import asyncio
import collections
import dataclasses
import datetime
import decimal
import logging
import math
import re
import socket
import typing
from urllib import parse

from pamqp import base, body, commands, frame, header
from pamqp import exceptions as pamqp_exceptions
import yarl

from aiorabbit import (channel0, DEFAULT_LOCALE, DEFAULT_PRODUCT, DEFAULT_URL,
                       exceptions, message, protocol, state)

LOGGER = logging.getLogger(__name__)


FieldArray = typing.List['FieldValue']  # type: ignore
FieldTable = typing.Dict[str, 'FieldValue']  # type: ignore
FieldValue = typing.Union[bool,  # type: ignore
                          bytearray,
                          decimal.Decimal,
                          FieldArray,
                          FieldTable,
                          float,
                          int,
                          None,
                          str,
                          datetime.datetime]

STATE_DISCONNECTED = 0x11
STATE_CONNECTING = 0x12
STATE_CONNECTED = 0x13
STATE_OPENED = 0x14
STATE_UPDATE_SECRET_SENT = 0x15
STATE_UPDATE_SECRETOK_RECEIVED = 0x16
STATE_OPENING_CHANNEL = 0x17
STATE_CHANNEL_OPEN_SENT = 0x20
STATE_CHANNEL_OPENOK_RECEIVED = 0x21
STATE_CHANNEL_CLOSE_RECEIVED = 0x22
STATE_CHANNEL_CLOSE_SENT = 0x23
STATE_CHANNEL_CLOSEOK_RECEIVED = 0x24
STATE_CHANNEL_CLOSEOK_SENT = 0x25
STATE_CHANNEL_FLOW_RECEIVED = 0x26
STATE_CHANNEL_FLOWOK_SENT = 0x27
STATE_CONFIRM_SELECT_SENT = 0x30
STATE_CONFIRM_SELECTOK_RECEIVED = 0x31
STATE_EXCHANGE_BIND_SENT = 0x40
STATE_EXCHANGE_BINDOK_RECEIVED = 0x41
STATE_EXCHANGE_DECLARE_SENT = 0x42
STATE_EXCHANGE_DECLAREOK_RECEIVED = 0x43
STATE_EXCHANGE_DELETE_SENT = 0x44
STATE_EXCHANGE_DELETEOK_RECEIVED = 0x45
STATE_EXCHANGE_UNBIND_SENT = 0x46
STATE_EXCHANGE_UNBINDOK_RECEIVED = 0x47
STATE_QUEUE_BIND_SENT = 0x50
STATE_QUEUE_BINDOK_RECEIVED = 0x51
STATE_QUEUE_DECLARE_SENT = 0x52
STATE_QUEUE_DECLAREOK_RECEIVED = 0x53
STATE_QUEUE_DELETE_SENT = 0x54
STATE_QUEUE_DELETEOK_RECEIVED = 0x55
STATE_QUEUE_PURGE_SENT = 0x56
STATE_QUEUE_PURGEOK_RECEIVED = 0x57
STATE_QUEUE_UNBIND_SENT = 0x58
STATE_QUEUE_UNBINDOK_RECEIVED = 0x59
STATE_TX_SELECT_SENT = 0x60
STATE_TX_SELECTOK_RECEIVED = 0x61
STATE_TX_COMMIT_SENT = 0x62
STATE_TX_COMMITOK_RECEIVED = 0x63
STATE_TX_ROLLBACK_SENT = 0x64
STATE_TX_ROLLBACKOK_RECEIVED = 0x65
STATE_BASIC_ACK_RECEIVED = 0x70
STATE_BASIC_ACK_SENT = 0x71
STATE_BASIC_CANCEL_RECEIVED = 0x72
STATE_BASIC_CANCEL_SENT = 0x73
STATE_BASIC_CANCELOK_RECEIVED = 0x74
STATE_BASIC_CANCELOK_SENT = 0x75
STATE_BASIC_CONSUME_SENT = 0x76
STATE_BASIC_CONSUMEOK_RECEIVED = 0x77
STATE_BASIC_DELIVER_RECEIVED = 0x78
STATE_CONTENT_HEADER_RECEIVED = 0x79
STATE_CONTENT_BODY_RECEIVED = 0x80
STATE_BASIC_GET_SENT = 0x81
STATE_BASIC_GETEMPTY_RECEIVED = 0x82
STATE_BASIC_GETOK_RECEIVED = 0x83
STATE_BASIC_NACK_RECEIVED = 0x84
STATE_BASIC_NACK_SENT = 0x85
STATE_BASIC_PUBLISH_SENT = 0x86
STATE_CONTENT_HEADER_SENT = 0x87
STATE_CONTENT_BODY_SENT = 0x88
STATE_BASIC_QOS_SENT = 0x89
STATE_BASIC_QOSOK_RECEIVED = 0x90
STATE_BASIC_RECOVER_SENT = 0x91
STATE_BASIC_RECOVEROK_RECEIVED = 0x92
STATE_BASIC_REJECT_RECEIVED = 0x93
STATE_BASIC_REJECT_SENT = 0x94
STATE_BASIC_RETURN_RECEIVED = 0x95
STATE_MESSAGE_ASSEMBLED = 0x96
STATE_CLOSING = 0x100
STATE_CLOSED = 0x101

_STATE_MAP = {
    state.STATE_UNINITIALIZED: 'Uninitialized',
    state.STATE_EXCEPTION: 'Exception Raised',
    STATE_DISCONNECTED: 'Disconnected',
    STATE_CONNECTING: 'Connecting',
    STATE_CONNECTED: 'Connected',
    STATE_OPENED: 'Opened',
    STATE_UPDATE_SECRET_SENT: 'Updating Secret',
    STATE_UPDATE_SECRETOK_RECEIVED: 'Secret Updated',
    STATE_OPENING_CHANNEL: 'Opening Channel',
    STATE_CHANNEL_OPEN_SENT: 'Channel Requested',
    STATE_CHANNEL_OPENOK_RECEIVED: 'Channel Open',
    STATE_CHANNEL_CLOSE_RECEIVED: 'Channel Close Received',
    STATE_CHANNEL_CLOSE_SENT: 'Channel Close Sent',
    STATE_CHANNEL_CLOSEOK_RECEIVED: 'Channel CloseOk Received',
    STATE_CHANNEL_CLOSEOK_SENT: 'Channel CloseOk Sent',
    STATE_CHANNEL_FLOW_RECEIVED: 'Channel Flow Received',
    STATE_CHANNEL_FLOWOK_SENT: 'Channel FlowOk Sent',
    STATE_CONFIRM_SELECT_SENT: 'Enabling Publisher Confirmations',
    STATE_CONFIRM_SELECTOK_RECEIVED: 'Publisher Confirmations Enabled',
    STATE_EXCHANGE_BIND_SENT: 'Binding Exchange',
    STATE_EXCHANGE_BINDOK_RECEIVED: 'Exchange Bound',
    STATE_EXCHANGE_DECLARE_SENT: 'Declaring Exchange',
    STATE_EXCHANGE_DECLAREOK_RECEIVED: 'Exchange Declared',
    STATE_EXCHANGE_DELETE_SENT: 'Deleting Exchange',
    STATE_EXCHANGE_DELETEOK_RECEIVED: 'Exchange Deleted',
    STATE_EXCHANGE_UNBIND_SENT: 'Unbinding Exchange',
    STATE_EXCHANGE_UNBINDOK_RECEIVED: 'Exchange unbound',
    STATE_QUEUE_BIND_SENT: 'Binding Queue',
    STATE_QUEUE_BINDOK_RECEIVED: 'Queue Bound',
    STATE_QUEUE_DECLARE_SENT: 'Declaring Queue',
    STATE_QUEUE_DECLAREOK_RECEIVED: 'Queue Declared',
    STATE_QUEUE_DELETE_SENT: 'Deleting Queue',
    STATE_QUEUE_DELETEOK_RECEIVED: 'Queue Deleted',
    STATE_QUEUE_PURGE_SENT: 'Purging Queue',
    STATE_QUEUE_PURGEOK_RECEIVED: 'Queue Purged',
    STATE_QUEUE_UNBIND_SENT: 'Unbinding Queue',
    STATE_QUEUE_UNBINDOK_RECEIVED: 'Queue unbound',
    STATE_TX_SELECT_SENT: 'Starting Transaction',
    STATE_TX_SELECTOK_RECEIVED: 'Transaction started',
    STATE_TX_COMMIT_SENT: 'Committing Transaction',
    STATE_TX_COMMITOK_RECEIVED: 'Transaction committed',
    STATE_TX_ROLLBACK_SENT: 'Aborting Transaction',
    STATE_TX_ROLLBACKOK_RECEIVED: 'Transaction aborted',
    STATE_BASIC_ACK_RECEIVED: 'Received message acknowledgement',
    STATE_BASIC_ACK_SENT: 'Sent message acknowledgement',
    STATE_BASIC_CANCEL_RECEIVED: 'Server canceled consumer',
    STATE_BASIC_CANCEL_SENT: 'Cancelling Consumer',
    STATE_BASIC_CANCELOK_RECEIVED: 'Consumer cancelled',
    STATE_BASIC_CANCELOK_SENT: 'Acknowledging cancelled consumer',
    STATE_BASIC_CONSUME_SENT: 'Initiating consuming of messages',
    STATE_BASIC_CONSUMEOK_RECEIVED: 'Consuming of messages initiated',
    STATE_BASIC_DELIVER_RECEIVED: 'Server delivered message',
    STATE_CONTENT_HEADER_RECEIVED: 'Received content header',
    STATE_CONTENT_BODY_RECEIVED: 'Received content body',
    STATE_BASIC_GET_SENT: 'Requesting individual message',
    STATE_BASIC_GETEMPTY_RECEIVED: 'Message not available',
    STATE_BASIC_GETOK_RECEIVED: 'Individual message to be delivered',
    STATE_BASIC_NACK_RECEIVED: 'Server sent negative acknowledgement',
    STATE_BASIC_NACK_SENT: 'Sending negative acknowledgement',
    STATE_BASIC_PUBLISH_SENT: 'Publishing Message',
    STATE_CONTENT_HEADER_SENT: 'Message Content Header sent',
    STATE_CONTENT_BODY_SENT: 'Message Body sent',
    STATE_BASIC_QOS_SENT: 'Setting QoS',
    STATE_BASIC_QOSOK_RECEIVED: 'QoS set',
    STATE_BASIC_RECOVER_SENT: 'Sending recover request',
    STATE_BASIC_RECOVEROK_RECEIVED: 'Recover request received',
    STATE_BASIC_REJECT_RECEIVED: 'Server rejected Message',
    STATE_BASIC_REJECT_SENT: 'Sending Message rejection',
    STATE_BASIC_RETURN_RECEIVED: 'Server returned message',
    STATE_MESSAGE_ASSEMBLED: 'Message assembled',
    STATE_CLOSING: 'Closing',
    STATE_CLOSED: 'Closed',
}

_IDLE_STATE = [
    STATE_UPDATE_SECRET_SENT,
    STATE_BASIC_CANCEL_SENT,
    STATE_CHANNEL_CLOSE_RECEIVED,
    STATE_CHANNEL_CLOSE_SENT,
    STATE_CHANNEL_FLOW_RECEIVED,
    STATE_CONFIRM_SELECT_SENT,
    STATE_EXCHANGE_BIND_SENT,
    STATE_EXCHANGE_DECLARE_SENT,
    STATE_EXCHANGE_DELETE_SENT,
    STATE_EXCHANGE_UNBIND_SENT,
    STATE_QUEUE_BIND_SENT,
    STATE_QUEUE_DECLARE_SENT,
    STATE_QUEUE_DELETE_SENT,
    STATE_QUEUE_PURGE_SENT,
    STATE_QUEUE_UNBIND_SENT,
    STATE_TX_SELECT_SENT,
    STATE_TX_COMMIT_SENT,
    STATE_TX_ROLLBACK_SENT,
    STATE_BASIC_CONSUME_SENT,
    STATE_BASIC_DELIVER_RECEIVED,
    STATE_BASIC_GET_SENT,
    STATE_BASIC_PUBLISH_SENT,
    STATE_BASIC_QOS_SENT,
    STATE_BASIC_RECOVER_SENT,
    STATE_CLOSING,
    STATE_CLOSED
]

_STATE_TRANSITIONS = {
    state.STATE_UNINITIALIZED: [STATE_DISCONNECTED],
    state.STATE_EXCEPTION: [STATE_CLOSING, STATE_CLOSED, STATE_DISCONNECTED],
    STATE_DISCONNECTED: [STATE_CONNECTING],
    STATE_CONNECTING: [STATE_CONNECTED, STATE_CLOSED],
    STATE_CONNECTED: [STATE_OPENED, STATE_CLOSED],
    STATE_OPENED: [STATE_OPENING_CHANNEL],
    STATE_OPENING_CHANNEL: [STATE_CHANNEL_OPEN_SENT],
    STATE_UPDATE_SECRET_SENT: [STATE_UPDATE_SECRETOK_RECEIVED],
    STATE_UPDATE_SECRETOK_RECEIVED: _IDLE_STATE,
    STATE_CHANNEL_OPEN_SENT: [STATE_CHANNEL_OPENOK_RECEIVED],
    STATE_CHANNEL_OPENOK_RECEIVED: _IDLE_STATE,
    STATE_CHANNEL_CLOSE_RECEIVED: [STATE_CHANNEL_CLOSEOK_SENT],
    STATE_CHANNEL_CLOSE_SENT: [STATE_CHANNEL_CLOSEOK_RECEIVED],
    STATE_CHANNEL_CLOSEOK_RECEIVED: [STATE_OPENING_CHANNEL, STATE_CLOSING],
    STATE_CHANNEL_CLOSEOK_SENT: [STATE_OPENING_CHANNEL],
    STATE_CHANNEL_FLOW_RECEIVED: [STATE_CHANNEL_FLOWOK_SENT],
    STATE_CHANNEL_FLOWOK_SENT: _IDLE_STATE,
    STATE_CONFIRM_SELECT_SENT: [STATE_CONFIRM_SELECTOK_RECEIVED],
    STATE_CONFIRM_SELECTOK_RECEIVED: _IDLE_STATE,
    STATE_EXCHANGE_BIND_SENT: [
        STATE_CHANNEL_CLOSE_RECEIVED,
        STATE_EXCHANGE_BINDOK_RECEIVED],
    STATE_EXCHANGE_BINDOK_RECEIVED: _IDLE_STATE,
    STATE_EXCHANGE_DECLARE_SENT: [
        STATE_CHANNEL_CLOSE_RECEIVED,
        STATE_EXCHANGE_DECLAREOK_RECEIVED],
    STATE_EXCHANGE_DECLAREOK_RECEIVED: _IDLE_STATE,
    STATE_EXCHANGE_DELETE_SENT: [
        STATE_CHANNEL_CLOSE_RECEIVED,
        STATE_EXCHANGE_DELETEOK_RECEIVED],
    STATE_EXCHANGE_DELETEOK_RECEIVED: _IDLE_STATE,
    STATE_EXCHANGE_UNBIND_SENT: [
        STATE_CHANNEL_CLOSE_RECEIVED,
        STATE_EXCHANGE_UNBINDOK_RECEIVED],
    STATE_EXCHANGE_UNBINDOK_RECEIVED: _IDLE_STATE,
    STATE_QUEUE_BIND_SENT: [
        STATE_CHANNEL_CLOSE_RECEIVED,
        STATE_QUEUE_BINDOK_RECEIVED],
    STATE_QUEUE_BINDOK_RECEIVED: _IDLE_STATE,
    STATE_QUEUE_DECLARE_SENT: [
        STATE_CHANNEL_CLOSE_RECEIVED,
        STATE_QUEUE_DECLAREOK_RECEIVED],
    STATE_QUEUE_DECLAREOK_RECEIVED: _IDLE_STATE,
    STATE_QUEUE_DELETE_SENT: [
        STATE_CHANNEL_CLOSE_RECEIVED,
        STATE_QUEUE_DELETEOK_RECEIVED],
    STATE_QUEUE_DELETEOK_RECEIVED: _IDLE_STATE,
    STATE_QUEUE_PURGE_SENT: [
        STATE_CHANNEL_CLOSE_RECEIVED,
        STATE_QUEUE_PURGEOK_RECEIVED],
    STATE_QUEUE_PURGEOK_RECEIVED: _IDLE_STATE,
    STATE_QUEUE_UNBIND_SENT: [
        STATE_CHANNEL_CLOSE_RECEIVED,
        STATE_QUEUE_UNBINDOK_RECEIVED],
    STATE_QUEUE_UNBINDOK_RECEIVED: _IDLE_STATE,
    STATE_TX_SELECT_SENT: [STATE_TX_SELECTOK_RECEIVED],
    STATE_TX_SELECTOK_RECEIVED: _IDLE_STATE + [
        STATE_TX_COMMIT_SENT,
        STATE_TX_ROLLBACK_SENT
    ],
    STATE_TX_COMMIT_SENT: [STATE_TX_COMMITOK_RECEIVED],
    STATE_TX_COMMITOK_RECEIVED: _IDLE_STATE,
    STATE_TX_ROLLBACK_SENT: [STATE_TX_ROLLBACKOK_RECEIVED],
    STATE_TX_ROLLBACKOK_RECEIVED: _IDLE_STATE,
    STATE_BASIC_ACK_RECEIVED: _IDLE_STATE,
    STATE_BASIC_ACK_SENT: _IDLE_STATE,
    STATE_BASIC_CANCEL_RECEIVED: _IDLE_STATE,
    STATE_BASIC_CANCEL_SENT: [STATE_BASIC_CANCELOK_RECEIVED],
    STATE_BASIC_CANCELOK_RECEIVED: _IDLE_STATE,
    STATE_BASIC_CANCELOK_SENT: _IDLE_STATE,
    STATE_BASIC_CONSUME_SENT: [
        STATE_CHANNEL_CLOSE_RECEIVED,
        STATE_BASIC_CONSUMEOK_RECEIVED],
    STATE_BASIC_CONSUMEOK_RECEIVED: _IDLE_STATE,
    STATE_BASIC_DELIVER_RECEIVED: [STATE_CONTENT_HEADER_RECEIVED],
    STATE_CONTENT_HEADER_RECEIVED: [STATE_CONTENT_BODY_RECEIVED],
    STATE_CONTENT_BODY_RECEIVED: [STATE_MESSAGE_ASSEMBLED],
    STATE_BASIC_GET_SENT: [
        STATE_CHANNEL_CLOSE_RECEIVED,
        STATE_BASIC_GETEMPTY_RECEIVED,
        STATE_BASIC_GETOK_RECEIVED],
    STATE_BASIC_GETEMPTY_RECEIVED: _IDLE_STATE,
    STATE_BASIC_GETOK_RECEIVED: [STATE_CONTENT_HEADER_RECEIVED],
    STATE_BASIC_NACK_RECEIVED: _IDLE_STATE,
    STATE_BASIC_NACK_SENT: _IDLE_STATE,
    STATE_BASIC_PUBLISH_SENT: [STATE_CONTENT_HEADER_SENT],
    STATE_CONTENT_HEADER_SENT: [STATE_CONTENT_BODY_SENT],
    STATE_CONTENT_BODY_SENT: _IDLE_STATE + [
        STATE_BASIC_ACK_RECEIVED,
        STATE_BASIC_NACK_RECEIVED,
        STATE_BASIC_REJECT_RECEIVED,
        STATE_BASIC_RETURN_RECEIVED],
    STATE_BASIC_QOS_SENT: [
        STATE_CHANNEL_CLOSE_RECEIVED, STATE_BASIC_QOSOK_RECEIVED],
    STATE_BASIC_QOSOK_RECEIVED: _IDLE_STATE,
    STATE_BASIC_RECOVER_SENT: [STATE_BASIC_RECOVEROK_RECEIVED],
    STATE_BASIC_RECOVEROK_RECEIVED: _IDLE_STATE,
    STATE_BASIC_REJECT_RECEIVED: _IDLE_STATE,
    STATE_BASIC_REJECT_SENT: _IDLE_STATE,
    STATE_BASIC_RETURN_RECEIVED: [STATE_CONTENT_HEADER_RECEIVED],
    STATE_MESSAGE_ASSEMBLED: _IDLE_STATE + [
        STATE_BASIC_ACK_RECEIVED,
        STATE_BASIC_ACK_SENT,
        STATE_BASIC_NACK_SENT,
        STATE_BASIC_NACK_RECEIVED,
        STATE_BASIC_REJECT_SENT,
        STATE_BASIC_REJECT_RECEIVED
    ],
    STATE_CLOSING: [STATE_CLOSED],
    STATE_CLOSED: [STATE_CONNECTING]
}

Arguments = typing.Optional[typing.Dict[str, typing.Any]]
"""AMQ Method Arguments"""

NamePattern = re.compile(r'^[\w:.-]+$', flags=re.UNICODE)


@dataclasses.dataclass()
class _Defaults:
    locale: str
    product: str


class Client(state.StateManager):
    """Asynchronous RabbitMQ Client

    .. code-block:: python3
       :caption: Example Usage

        client = Client(RABBITMQ_URL)
        await client.connect()
        await client.exchange_declare('test', 'topic')
        await client.close()

    """
    STATE_MAP = _STATE_MAP
    STATE_TRANSITIONS = _STATE_TRANSITIONS

    def __init__(self,
                 url: str = DEFAULT_URL,
                 locale: str = DEFAULT_LOCALE,
                 product: str = DEFAULT_PRODUCT,
                 loop: typing.Optional[asyncio.AbstractEventLoop] = None):
        super().__init__(loop or asyncio.get_running_loop())
        self._acks = set({})
        self._blocked = asyncio.Event()
        self._channel: int = 0
        self._channel_open = asyncio.Event()
        self._connected = asyncio.Event()
        self._consumers: typing.Dict[str, callable] = {}
        self._delivery_tag = 0
        self._defaults = _Defaults(locale, product)
        self._last_frame: typing.Optional[base.Frame] = None
        self._message: typing.Optional[message.Message] = None
        self._nacks = set({})
        self._on_channel_close: typing.Optional[typing.Callable] = None
        self._on_message_return: typing.Optional[typing.Callable] = None
        self._rejects = set({})
        self._transport: typing.Optional[asyncio.Transport] = None
        self._pending_consumers: \
            typing.Deque[(asyncio.Future, callable)] = collections.deque([])
        self._protocol: typing.Optional[asyncio.Protocol] = None
        self._publisher_confirms = False
        self._transactional = False
        self._url = yarl.URL(url)
        self._set_state(STATE_DISCONNECTED)
        self._max_frame_size: typing.Optional[float] = None

    async def connect(self) -> None:
        """Connect to the RabbitMQ Server"""
        await self._connect()
        await self._open_channel()

    async def close(self) -> None:
        """Close the client connection to the server"""
        LOGGER.debug('Invoked Client.close() while is_closed (%r, %r)',
                     self.is_closed, self._channel0)
        if self.is_closed or not self._channel0 or not self._transport:
            LOGGER.warning('Close called when connection is not open')
            if self._state != STATE_CLOSED:
                self._set_state(STATE_CLOSED)
            return
        if self._state != state.STATE_EXCEPTION:
            if self._channel_open.is_set():
                self._write(
                    commands.Channel.Close(200, 'Client Requested', 0, 0))
                self._set_state(STATE_CHANNEL_CLOSE_SENT)
                await self._wait_on_state(STATE_CHANNEL_CLOSEOK_RECEIVED)
        await self._close()

    async def basic_ack(self,
                        delivery_tag: int,
                        multiple: bool = False) -> None:
        """Acknowledge one or more messages

        When sent by the client, this method acknowledges one or more messages
        delivered via the Deliver or Get-Ok methods. The acknowledgement can be
        for a single message or a set of messages up to and including a
        specific message.

        :param delivery_tag: Server-assigned delivery tag
        :param multiple: Acknowledge multiple messages

        """
        if not isinstance(delivery_tag, int):
            raise TypeError('delivery_tag must be of type int')
        elif not isinstance(multiple, bool):
            raise TypeError('multiple must be of type bool')
        self._write(commands.Basic.Ack(delivery_tag, multiple))
        self._set_state(STATE_BASIC_ACK_SENT)

    async def basic_cancel(self, consumer_tag: str = '') -> None:
        """End a queue consumer

        This method cancels a consumer. This does not affect already delivered
        messages, but it does mean the server will not send any more messages
        for that consumer. The client may receive an arbitrary number of
        messages in between sending the cancel method and receiving the
        ``CancelOk`` reply. It may also be sent from the server to the client
        in the event of the consumer being unexpectedly cancelled (i.e.
        cancelled for any reason other than the server receiving the
        corresponding basic.cancel from the client). This allows clients to be
        notified of the loss of consumers due to events such as queue deletion.
        Note that as it is not a MUST for clients to accept this method from
        \the server, it is advisable for the broker to be able to identify
        those clients that are capable of accepting the method, through some
        means of capability negotiation.

        :param consumer_tag: Consumer tag

        """
        if not isinstance(consumer_tag, str):
            raise TypeError('consumer_tag must be of type str')
        self._write(commands.Basic.Cancel(consumer_tag))
        self._set_state(STATE_BASIC_CANCEL_SENT)
        await self._wait_on_state(STATE_BASIC_CANCELOK_RECEIVED)
        del self._consumers[consumer_tag]

    async def basic_consume(self,
                            queue: str = '',
                            no_local: bool = False,
                            no_ack: bool = False,
                            exclusive: bool = False,
                            arguments: typing.Optional[FieldTable] = None,
                            callback: typing.Callable = None,
                            consumer_tag: typing.Optional[str] = None) \
            -> str:
        """Start a queue consumer

        This method asks the server to start a “consumer”, which is a transient
        request for messages from a specific queue. Consumers last as long as
        the channel they were declared on, or until the client cancels them.

        This method is used for callback passing style usage. For each message,
        the ``callback`` method will be invoked, passing in an instance of
        :class:`~pamqp.message.Message`.

        The :meth:`Client.consume <aiorabbit.client.Client.consume>` method
        should be used for generator style consuming.

        :param queue: Specifies the name of the queue to consume from
        :param no_local: Do not deliver own messages
        :param no_ack: No acknowledgement needed
        :param exclusive: Request exclusive access
        :param arguments: A set of arguments for the consume. The syntax and
            semantics of these arguments depends on the server implementation.
        :param callback: The method to invoke for each received message.
        :param consumer_tag: Specifies the identifier for the consumer. The
            consumer tag is local to a channel, so two clients can use the same
            consumer tags. If this field is empty the server will generate a
            unique tag.
        :returns: the consumer tag value

        """
        if not isinstance(queue, str):
            raise TypeError('queue must be of type str')
        elif not isinstance(no_local, bool):
            raise TypeError('no_local must be of type bool')
        elif not isinstance(no_ack, bool):
            raise TypeError('no_ack must be of type bool')
        elif not isinstance(exclusive, bool):
            raise TypeError('exclusive must be of type bool')
        elif arguments and not isinstance(arguments, dict):
            raise TypeError('arguments must be of type dict')
        elif callback is None:
            raise ValueError('callback must be specified')
        elif not callable(callback):
            raise TypeError('callback must be a callable')
        elif consumer_tag is not None and not isinstance(consumer_tag, str):
            raise TypeError('consumer_tag must be of type str')
        self._write(commands.Basic.Consume(
            0, queue, consumer_tag or '', no_local, no_ack, exclusive,
            False, arguments))
        self._set_state(STATE_BASIC_CONSUME_SENT)
        consumer_tag_future = asyncio.Future()
        self._pending_consumers.append((consumer_tag_future, callback))
        result = await self._wait_on_state(
            STATE_BASIC_CONSUMEOK_RECEIVED, STATE_CHANNEL_CLOSE_RECEIVED)
        if result == STATE_CHANNEL_CLOSE_RECEIVED:
            self._pending_consumers.remove((consumer_tag_future, callback))
            err_frame = self._last_frame
            await self._wait_on_state(STATE_CHANNEL_OPENOK_RECEIVED)
            raise exceptions.CLASS_MAPPING[err_frame.reply_code](
                err_frame.reply_code)
        await consumer_tag_future
        self._logger.debug('Consumer Tag Future: %r', consumer_tag_future)
        return consumer_tag_future.result()

    async def basic_get(self, queue: str = '', no_ack: bool = False) \
            -> typing.Optional[message.Message]:
        """Direct access to a queue

        This method provides a direct access to the messages in a queue using
        a synchronous dialogue that is designed for specific types of
        application where synchronous functionality is more important than
        performance.

        :param queue: Specifies the name of the queue to get a message from
        :param no_ack: No acknowledgement needed

        """
        if not isinstance(queue, str):
            raise TypeError('queue must be of type str')
        elif not isinstance(no_ack, bool):
            raise TypeError('no_ack must be of type bool')
        response = asyncio.Future()
        self._consumers['GetOk'] = response
        self._write(commands.Basic.Get(0, queue, no_ack))
        self._set_state(STATE_BASIC_GET_SENT)
        return await response

    async def basic_nack(self,
                         delivery_tag: int,
                         multiple: bool = False,
                         requeue: bool = True) -> None:
        """Reject one or more incoming messages

        This method allows a client to reject one or more incoming messages.
        It can be used to interrupt and cancel large incoming messages, or
        return untreatable messages to their original queue.

        :param delivery_tag: Server-assigned delivery tag
        :param multiple: Reject multiple messages
        :param requeue: Requeue the message

        """
        if not isinstance(delivery_tag, int):
            raise TypeError('delivery_tag must be of type int')
        elif not isinstance(multiple, bool):
            raise TypeError('multiple must be of type bool')
        elif not isinstance(requeue, bool):
            raise TypeError('requeue must be of type bool')
        self._write(commands.Basic.Nack(delivery_tag, multiple, requeue))
        self._set_state(STATE_BASIC_NACK_SENT)

    async def basic_qos(self,
                        prefetch_size=0,
                        prefetch_count=0,
                        global_=False) -> None:
        """Specify quality of service.

        This method requests a specific quality of service. The QoS can be
        specified for the current channel or for all channels on the
        connection. The particular properties and semantics of a qos method
        always depend on the content class semantics. Though the qos method
        could in principle apply to both peers, it is currently meaningful
        only for the server.

        .. note:: global Redefinition

            RabbitMQ has reinterpreted this field. The original specification
            said: "By default the QoS settings apply to the current channel
            only. If this field is set, they are applied to the entire
            connection." Instead, RabbitMQ takes ``global_ = False`` to mean
            that the QoS settings should apply per-consumer (for new consumers
            on the channel; existing ones being unaffected) and
            ``global_ = True`` to mean that the QoS settings should apply
            per-channel.

        :param prefetch_size: Prefetch window in octets / bytes
        :param prefetch_count: Prefetch window in messages
        :param global_: Apply to entire connection

        """
        if not isinstance(prefetch_size, int):
            raise TypeError('prefetch_size must be of type int')
        elif not isinstance(prefetch_count, int):
            raise TypeError('prefetch_size must be of type int')
        elif not isinstance(global_, bool):
            raise TypeError('global_ must be of type bool')
        self._write(commands.Basic.Qos(prefetch_size, prefetch_count, global_))
        self._set_state(STATE_BASIC_QOS_SENT)
        try:
            await self._wait_on_state(STATE_BASIC_QOSOK_RECEIVED)
        except pamqp_exceptions.AMQPNotImplemented as err:
            raise exceptions.NotImplementedOnServer(str(err))

    async def basic_recover(self, requeue: bool = False) -> None:
        """Redeliver unacknowledged messages

        This method asks the server to redeliver all unacknowledged messages
        on a specified channel. Zero or more messages may be redelivered.

        :param requeue: Requeue the message
        :raises aiorabbit.exceptions.NotImplementedOnServer: when
            `False` is specified for `requeue`

        """
        if not isinstance(requeue, bool):
            raise TypeError('requeue must be of type bool')
        self._write(commands.Basic.Recover(requeue))
        self._set_state(STATE_BASIC_RECOVER_SENT)
        try:
            await self._wait_on_state(STATE_BASIC_RECOVEROK_RECEIVED)
        except pamqp_exceptions.AMQPNotImplemented as err:
            raise exceptions.NotImplementedOnServer(str(err))

    async def basic_reject(self,
                           delivery_tag: int,
                           requeue: bool = True) -> None:
        """Reject an incoming message

        This method allows a client to reject a message. It can be used to
        interrupt and cancel large incoming messages, or return untreatable
        messages to their original queue.

        :param delivery_tag: Server-assigned delivery tag
        :param requeue: Requeue the message

        """
        if not isinstance(delivery_tag, int):
            raise TypeError('delivery_tag must be of type int')
        elif not isinstance(requeue, bool):
            raise TypeError('requeue must be of type bool')
        self._write(commands.Basic.Reject(delivery_tag, requeue))
        self._set_state(STATE_BASIC_REJECT_SENT)

    async def confirm_select(self) -> None:
        """Turn on Publisher Confirmations

        :raises RuntimeError: if publisher confirmations are already enabled
        :raises ~aiorabbit.exceptions.NotSupportedError:
            if publisher confirmations are not available on the RabbitMQ server

        """
        LOGGER.debug('Enabling confirm select')
        if 'publisher_confirms' not in self.server_capabilities:
            raise exceptions.NotSupportedError(
                'Server does not support publisher confirmations')
        elif self._publisher_confirms:
            raise RuntimeError('Publisher confirmations are already enabled')
        else:
            self._write(commands.Confirm.Select())
            self._set_state(STATE_CONFIRM_SELECT_SENT)
            await self._wait_on_state(STATE_CONFIRM_SELECTOK_RECEIVED)
            self._publisher_confirms = True

    async def exchange_bind(self,
                            destination: str = '',
                            source: str = '',
                            routing_key: str = '',
                            arguments: typing.Optional[FieldTable] = None) \
            -> None:
        """Bind exchange to an exchange.

        :param destination: Destination exchange name
        :param source: Source exchange name
        :param routing_key: Message routing key
        :param arguments: Arguments for binding
        :raises TypeError: if an argument is of the wrong data type
        :raises ~aiorabbit.exceptions.ExchangeNotFoundError:
            if the one of the specified exchanges does not exist

        """
        if not isinstance(destination, str):
            raise TypeError('destination must be of type str')
        elif not isinstance(source, str):
            raise TypeError('source must be of type str')
        elif not isinstance(routing_key, str):
            raise TypeError('routing_key must be of type str')
        elif arguments and not isinstance(arguments, dict):
            raise TypeError('arguments must be of type dict')
        self._write(commands.Exchange.Bind(
            destination=destination, source=source, routing_key=routing_key,
            arguments=arguments))
        self._set_state(STATE_EXCHANGE_BIND_SENT)
        result = await self._wait_on_state(
            STATE_CHANNEL_CLOSE_RECEIVED,
            STATE_EXCHANGE_BINDOK_RECEIVED)
        if result == STATE_CHANNEL_CLOSE_RECEIVED:
            err_frame = self._last_frame
            await self._wait_on_state(STATE_CHANNEL_OPENOK_RECEIVED)
            raise exceptions.CLASS_MAPPING[err_frame.reply_code](
                err_frame.reply_code)

    async def exchange_declare(self,
                               exchange: str = '',
                               exchange_type: str = 'direct',
                               passive: bool = False,
                               durable: bool = False,
                               auto_delete: bool = False,
                               internal: bool = False,
                               arguments: typing.Optional[FieldTable] = None) \
            -> None:
        """Verify exchange exists, create if needed

        This method creates an exchange if it does not already exist, and if
        the exchange exists, verifies that it is of the correct and expected
        class.

        :param exchange: Exchange name
        :param exchange_type: Exchange type
        :param passive: Do not create exchange
        :param durable: Request a durable exchange
        :param auto_delete: Auto-delete when unused
        :param internal: Create internal exchange
        :param arguments: Arguments for declaration
        :raises TypeError: if an argument is of the wrong data type
        :raises ~aiorabbit.exceptions.NotFound:
            if the sent command is invalid due to an argument value
        :raises ~aiorabbit.exceptions.CommandInvalid:
            when an exchange type or other parameter is invalid
        """
        if not isinstance(exchange, str):
            raise TypeError('exchange must be of type str')
        elif not isinstance(exchange_type, str):
            raise TypeError('exchange_type must be of type str')
        elif not isinstance(passive, bool):
            raise TypeError('passive must be of type bool')
        elif not isinstance(auto_delete, bool):
            raise TypeError('auto_delete must be of type bool')
        elif not isinstance(internal, bool):
            raise TypeError('internal must be of type bool')
        elif arguments and not isinstance(arguments, dict):
            raise TypeError('arguments must be of type dict')
        self._write(commands.Exchange.Declare(
            exchange=exchange, exchange_type=exchange_type, passive=passive,
            durable=durable, auto_delete=auto_delete, internal=internal,
            arguments=arguments))
        self._set_state(STATE_EXCHANGE_DECLARE_SENT)
        try:
            result = await self._wait_on_state(
                STATE_CHANNEL_CLOSE_RECEIVED,
                STATE_EXCHANGE_DECLAREOK_RECEIVED)
        except pamqp_exceptions.AMQPCommandInvalid as err:
            raise exceptions.CommandInvalid(str(err))
        if result == STATE_CHANNEL_CLOSE_RECEIVED:
            err_frame = self._last_frame
            await self._wait_on_state(STATE_CHANNEL_OPENOK_RECEIVED)
            raise exceptions.CLASS_MAPPING[err_frame.reply_code](
                err_frame.reply_code)

    async def exchange_delete(self,
                              exchange: str = '',
                              if_unused: bool = False) -> None:
        """Delete an exchange

        This method deletes an exchange. When an exchange is deleted all queue
        bindings on the exchange are cancelled.

        :param exchange: exchange name
            - Default: ``''``
        :param if_unused: Delete only if unused
            - Default: ``False``
        :raises ValueError: when an argument fails to validate

        """
        self._write(commands.Exchange.Delete(0, exchange, if_unused, False))
        self._set_state(STATE_EXCHANGE_DELETE_SENT)
        await self._wait_on_state(STATE_EXCHANGE_DELETEOK_RECEIVED)

    async def exchange_unbind(self,
                              destination: str = '',
                              source: str = '',
                              routing_key: str = '',
                              arguments: typing.Optional[FieldTable] = None) \
            -> None:
        """Unbind an exchange from an exchange.

        :param destination: Destination exchange name
        :param source: Source exchange name
        :param routing_key: Message routing key
        :param arguments: Arguments for binding
        :raises TypeError: if an argument is of the wrong data type
        :raises ValueError: if an argument value does not validate

        """
        if not isinstance(destination, str):
            raise TypeError('destination must be of type str')
        elif not isinstance(source, str):
            raise TypeError('source must be of type str')
        elif not isinstance(routing_key, str):
            raise TypeError('routing_key must be of type str')
        elif arguments and not isinstance(arguments, dict):
            raise TypeError('arguments must be of type dict')
        self._write(commands.Exchange.Unbind(
            destination=destination, source=source, routing_key=routing_key,
            arguments=arguments))
        self._set_state(STATE_EXCHANGE_UNBIND_SENT)
        await self._wait_on_state(STATE_EXCHANGE_UNBINDOK_RECEIVED)

    async def publish(self,
                      exchange: str = 'amq.direct',
                      routing_key: str = '',
                      message_body: typing.Union[bytes, str] = b'',
                      mandatory: bool = False,
                      immediate: bool = False,
                      app_id: typing.Optional[str] = None,
                      content_encoding: typing.Optional[str] = None,
                      content_type: typing.Optional[str] = None,
                      correlation_id: typing.Optional[str] = None,
                      delivery_mode: typing.Optional[int] = None,
                      expiration: typing.Optional[str] = None,
                      headers: typing.Optional[FieldTable] = None,
                      message_id: typing.Optional[str] = None,
                      message_type: typing.Optional[str] = None,
                      priority: typing.Optional[int] = None,
                      reply_to: typing.Optional[str] = None,
                      timestamp: typing.Optional[datetime.datetime] = None,
                      user_id: typing.Optional[str] = None) \
            -> typing.Union[None, bool, typing.Tuple[bool, message.Message]]:
        """Publish a message to RabbitMQ

        `message_body` can either be :class:`str` or :class:`bytes`. If
        it is a :class:`str`, it will be encoded, using ``UTF-8`` encoding.

        If publisher confirmations are enabled, will return `True` or `False`
        indicating success or failure.

        .. seealso:: :meth:`Client.confirm_select`

        :param exchange: The exchange to publish to. Default: `amq.direct`
        :param routing_key: The routing key to publish with. Default: ``
        :param message_body: The message body to publish. Default: ``
        :param mandatory: Indicate mandatory routing. Default: `False`
        :param immediate: Request immediate delivery. Default: `False`
        :param app_id: Creating application id
        :param content_type: MIME content type
        :param content_encoding: MIME content encoding
        :param correlation_id: Application correlation identifier
        :param delivery_mode: Non-persistent (`1`) or persistent (`2`)
        :param expiration: Message expiration specification
        :param headers: Message header field table
        :param message_id: Application message identifier
        :param message_type: Message type name
        :param priority: Message priority, `0` to `9`
        :param reply_to: Address to reply to
        :param timestamp: Message timestamp
        :param user_id: Creating user id
        :raises TypeError: if an argument is of the wrong data type
        :raises ValueError: if the value of one an argument does not validate

        """
        self._validate_exchange_name('exchange', exchange)
        self._validate_short_str('routing_key', routing_key)
        if not isinstance(message_body, (bytes, str)):
            raise TypeError('message_body must be of types bytes or str')
        self._validate_bool('mandatory', mandatory)
        self._validate_bool('immediate', immediate)
        if app_id is not None:
            self._validate_short_str('app_id', app_id)
        if content_encoding is not None:
            self._validate_short_str('content_encoding', content_encoding)
        if content_type is not None:
            self._validate_short_str('content_type', content_type)
        if correlation_id is not None:
            self._validate_short_str('correlation_id', correlation_id)
        if delivery_mode is not None:
            if not isinstance(delivery_mode, int):
                raise TypeError('delivery_mode must be of type int')
            elif not 0 < delivery_mode < 3:
                raise ValueError('delivery_mode must be 1 or 2')
        if expiration is not None:
            self._validate_short_str('expiration', expiration)
        if headers is not None:
            self._validate_field_table('headers', headers)
        if message_id is not None:
            self._validate_short_str('message_id', message_id)
        if message_type is not None:
            self._validate_short_str('message_type', message_type)
        if priority is not None:
            if not isinstance(priority, int):
                raise TypeError('delivery_mode must be of type int')
            elif not 0 < priority < 256:
                raise ValueError('priority must be between 0 and 256')
        if message_type:
            self._validate_short_str('message_type', message_type)
        if reply_to:
            self._validate_short_str('reply_to', reply_to)
        if timestamp and not isinstance(timestamp, datetime.datetime):
            raise TypeError('reply_to must be of type datetime.datetime')
        if user_id:
            self._validate_short_str('user_id', user_id)

        if isinstance(message_body, str):
            message_body = message_body.encode('utf-8')

        self._delivery_tag += 1
        delivery_tag = self._delivery_tag
        LOGGER.debug('Publishing delivery tag %i to %r %r',
                     delivery_tag, exchange, routing_key)

        self._write(commands.Basic.Publish(
            exchange=exchange, routing_key=routing_key, mandatory=mandatory,
            immediate=immediate))
        self._set_state(STATE_BASIC_PUBLISH_SENT)

        body_size = len(message_body)
        self._write(header.ContentHeader(
            body_size=body_size,
            properties=commands.Basic.Properties(
                app_id=app_id,
                content_encoding=content_encoding,
                content_type=content_type,
                correlation_id=correlation_id,
                delivery_mode=delivery_mode,
                expiration=expiration,
                headers=headers,
                message_id=message_id,
                message_type=message_type,
                priority=priority,
                reply_to=reply_to,
                timestamp=timestamp,
                user_id=user_id)))
        self._set_state(STATE_CONTENT_HEADER_SENT)

        # Calculate how many body frames are needed
        frames = int(math.ceil(body_size / self._max_frame_size))
        for offset in range(0, frames):  # Send the message
            start = int(self._max_frame_size * offset)
            end = int(start + self._max_frame_size)
            if end > body_size:
                end = int(body_size)
            self._write(body.ContentBody(message_body[start:end]))
        self._set_state(STATE_CONTENT_BODY_SENT)

        while self._publisher_confirms:
            result = await self._wait_on_state(
                STATE_BASIC_ACK_RECEIVED,
                STATE_BASIC_NACK_RECEIVED,
                STATE_CHANNEL_CLOSE_RECEIVED)
            if result == STATE_BASIC_ACK_RECEIVED \
                    and delivery_tag in self._acks:
                self._acks.remove(delivery_tag)
                return True
            elif result == STATE_BASIC_NACK_RECEIVED \
                    and delivery_tag in self._nacks:  # pragma: nocover
                """basic.nack will only be delivered if an internal error
                occurs in the Erlang process responsible for a queue."""
                self._nacks.remove(delivery_tag)
                return False
            #  State can only be STATE_CHANNEL_CLOSE_RECEIVED
            await self._wait_on_state(STATE_CHANNEL_OPENOK_RECEIVED)
            return False

    @property
    def is_closed(self) -> bool:
        """Indicates if the connection is closed"""
        return self._state in [STATE_CLOSED,
                               STATE_DISCONNECTED,
                               state.STATE_UNINITIALIZED] \
            or not self._transport

    async def queue_bind(self,
                         queue: str = '',
                         exchange: str = '',
                         routing_key: str = '',
                         arguments: typing.Optional[FieldTable] = None) \
            -> None:
        """Bind queue to an exchange

        This method binds a queue to an exchange. Until a queue is bound it
        will not receive any messages. In a classic messaging model,
        store-and- forward queues are bound to a direct exchange and
        subscription queues are bound to a topic exchange.

        :param queue: Specifies the name of the queue to bind
        :param exchange: Name of the exchange to bind to
        :param routing_key: Message routing key
        :param arguments: Arguments of binding
        :raises TypeError: if an argument is of the wrong data type
        :raises ValueError: when an argument fails to validate
        :raises ~aiorabbit.exceptions.CommandInvalidError:
            if the sent command is invalid due to an argument value

        """
        if not isinstance(queue, str):
            raise TypeError('queue must be of type str')
        elif not isinstance(exchange, str):
            raise TypeError('exchange must be of type str')
        elif not isinstance(routing_key, str):
            raise TypeError('routing_Key must be of type str')
        elif arguments and not isinstance(arguments, dict):
            raise TypeError('arguments must be of type dict')
        self._write(commands.Queue.Bind(
            0, queue, exchange, routing_key, False, arguments))
        self._set_state(STATE_QUEUE_BIND_SENT)
        result = await self._wait_on_state(
            STATE_QUEUE_BINDOK_RECEIVED, STATE_CHANNEL_CLOSE_RECEIVED)
        if result == STATE_CHANNEL_CLOSE_RECEIVED:
            err_frame = self._last_frame
            await self._wait_on_state(STATE_CHANNEL_OPENOK_RECEIVED)
            raise exceptions.CLASS_MAPPING[err_frame.reply_code](
                err_frame.reply_code)

    async def queue_declare(self,
                            queue: str = '',
                            passive: bool = False,
                            durable: bool = False,
                            exclusive: bool = False,
                            auto_delete: bool = False,
                            arguments: typing.Optional[FieldTable] = None) \
            -> typing.Tuple[int, int]:
        """Declare queue, create if needed

        This method creates or checks a queue. When creating a new queue the
        client can specify various properties that control the durability of
        the queue and its contents, and the level of sharing for the queue.

        Returns a tuple of message count, consumer count.

        :param queue: Queue name
        :param passive: Do not create queue
        :param durable: Request a durable queue
        :param exclusive: Request an exclusive queue
        :param auto_delete: Auto-delete queue when unused
        :param arguments: Arguments for declaration
        :raises TypeError: if an argument is of the wrong data type
        :raises ValueError: when an argument fails to validate
        :raises ~aiorabbit.exceptions.CommandInvalidError:
            if the sent command is invalid due to an argument value
        :raises ~aiorabbit.exceptions.ResourceLocked:
            when a queue is already declared and exclusive is requested
        :raises ~aiorabbit.exceptions.PreconditionFailed:
            when a queue is redeclared with a different definition than it
            currently has

        """
        if not isinstance(queue, str):
            raise TypeError('queue must be of type str')
        elif not isinstance(passive, bool):
            raise TypeError('passive must be of type bool')
        elif not isinstance(durable, bool):
            raise TypeError('durable must be of type bool')
        elif not isinstance(exclusive, bool):
            raise TypeError('exclusive must be of type bool')
        elif not isinstance(auto_delete, bool):
            raise TypeError('auto_delete must be of type bool')
        elif arguments and not isinstance(arguments, dict):
            raise TypeError('arguments must be of type dict')
        self._write(commands.Queue.Declare(
            0, queue, passive, durable, exclusive, auto_delete,
            False, arguments))
        self._set_state(STATE_QUEUE_DECLARE_SENT)
        result = await self._wait_on_state(
            STATE_QUEUE_DECLAREOK_RECEIVED, STATE_CHANNEL_CLOSE_RECEIVED)
        if result == STATE_CHANNEL_CLOSE_RECEIVED:
            err_frame = self._last_frame
            await self._wait_on_state(STATE_CHANNEL_OPENOK_RECEIVED)
            raise exceptions.CLASS_MAPPING[err_frame.reply_code](
                err_frame.reply_code)
        return self._last_frame.message_count, self._last_frame.consumer_count

    async def queue_delete(self,
                           queue: str = '',
                           if_unused: bool = False,
                           if_empty: bool = False) -> None:
        """Delete a queue

        This method deletes a queue. When a queue is deleted any pending
        messages are sent to a dead-letter queue if this is defined in the
        server configuration, and all consumers on the queue are cancelled.

        :param queue: Specifies the name of the queue to delete
        :param if_unused: Delete only if unused
        :param if_empty: Delete only if empty

        """
        if not isinstance(queue, str):
            raise TypeError('queue must be of type str')
        elif not isinstance(if_unused, bool):
            raise TypeError('if_unused must be of type bool')
        elif not isinstance(if_empty, bool):
            raise TypeError('if_empty must be of type bool')
        self._write(commands.Queue.Delete(
            0, queue, if_unused, if_empty, False))
        self._set_state(STATE_QUEUE_DELETE_SENT)
        await self._wait_on_state(STATE_QUEUE_DELETEOK_RECEIVED)

    async def queue_purge(self, queue: str = '') -> int:
        """Purge a queue

        This method removes all messages from a queue which are not awaiting
        acknowledgment.

        :param queue: Specifies the name of the queue to purge
        :returns: The quantity of messages purged

        """
        if not isinstance(queue, str):
            raise TypeError('queue must be of type str')
        self._write(commands.Queue.Purge(0, queue, False))
        self._set_state(STATE_QUEUE_PURGE_SENT)
        result = await self._wait_on_state(
            STATE_QUEUE_PURGEOK_RECEIVED, STATE_CHANNEL_CLOSE_RECEIVED)
        if result == STATE_CHANNEL_CLOSE_RECEIVED:
            err_frame = self._last_frame
            await self._wait_on_state(STATE_CHANNEL_OPENOK_RECEIVED)
            raise exceptions.CLASS_MAPPING[err_frame.reply_code](
                err_frame.reply_code)
        else:
            return self._last_frame.message_count

    async def queue_unbind(self,
                           queue: str = '',
                           exchange: str = '',
                           routing_key: str = '',
                           arguments: typing.Optional[FieldTable] = None) \
            -> None:
        """Unbind a queue from an exchange

        This method unbinds a queue from an exchange.

        :param queue: Specifies the name of the queue to unbind
        :param exchange: Name of the exchange to unbind from
        :param routing_key: Message routing key
        :param arguments: Arguments of binding
        :raises TypeError: if an argument is of the wrong data type
        :raises ValueError: when an argument fails to validate
        :raises ~aiorabbit.exceptions.CommandInvalidError:
            if the sent command is invalid due to an argument value

        """
        if not isinstance(queue, str):
            raise TypeError('queue must be of type str')
        elif not isinstance(exchange, str):
            raise TypeError('exchange must be of type str')
        elif not isinstance(routing_key, str):
            raise TypeError('routing_Key must be of type str')
        elif arguments and not isinstance(arguments, dict):
            raise TypeError('arguments must be of type dict')
        self._write(commands.Queue.Unbind(
            0, queue, exchange, routing_key, arguments))
        self._set_state(STATE_QUEUE_UNBIND_SENT)
        await self._wait_on_state(STATE_QUEUE_UNBINDOK_RECEIVED)

    def register_message_return_callback(
            self, callback: typing.Callable) -> None:
        """Register a callback that is invoked when RabbitMQ returns a
        published message.

        :param callback: The method or function to invoke as a callback

        """
        LOGGER.debug('Registered message return callback: %r', callback)
        self._on_message_return = callback

    async def tx_select(self) -> None:
        """Select standard transaction mode

        This method sets the channel to use standard transactions. The client
        must use this method at least once on a channel before using the
        :meth:`~Client.tx_commit` or :meth:`~Client.tx_rollback` methods.

        """
        self._write(commands.Tx.Select())
        self._set_state(STATE_TX_SELECT_SENT)
        self._transactional = True
        await self._wait_on_state(STATE_TX_SELECTOK_RECEIVED)

    async def tx_commit(self) -> None:
        """    Commit the current transaction

        This method commits all message publications and acknowledgments
        performed in the current transaction. A new transaction starts
        immediately after a commit.

        """
        if not self._transactional:
            raise exceptions.NoTransactionError()
        self._write(commands.Tx.Commit())
        self._set_state(STATE_TX_COMMIT_SENT)
        await self._wait_on_state(STATE_TX_COMMITOK_RECEIVED)

    async def tx_rollback(self) -> None:
        """    Abandon the current transaction

        This method abandons all message publications and acknowledgments
        performed in the current transaction. A new transaction starts
        immediately after a rollback. Note that unacked messages will not be
        automatically redelivered by rollback; if that is required an explicit
        recover call should be issued.

        """
        if not self._transactional:
            raise exceptions.NoTransactionError()
        self._write(commands.Tx.Rollback())
        self._set_state(STATE_TX_ROLLBACK_SENT)
        await self._wait_on_state(STATE_TX_ROLLBACKOK_RECEIVED)

    @property
    def server_capabilities(self) -> typing.List[str]:
        """Contains the capabilities of the currently connected
        RabbitMQ Server.

        .. code-block:: python
           :caption: Example return value

           ['authentication_failure_close',
            'basic.nack',
            'connection.blocked',
            'consumer_cancel_notify',
            'consumer_priorities',
            'direct_reply_to',
            'exchange_exchange_bindings',
            'per_consumer_qos',
            'publisher_confirms']

        """
        return [key for key, value in
                self._channel0.properties['capabilities'].items() if value]

    @property
    def server_properties(self) \
            -> typing.Dict[str, typing.Union[str, typing.Dict[str, bool]]]:
        """Contains the negotiated properties for the currently connected
        RabbitMQ Server.

        .. code-block:: python
           :caption: Example return value

           {'capabilities': {'authentication_failure_close': True,
                             'basic.nack': True,
                             'connection.blocked': True,
                             'consumer_cancel_notify': True,
                             'consumer_priorities': True,
                             'direct_reply_to': True,
                             'exchange_exchange_bindings': True,
                             'per_consumer_qos': True,
                             'publisher_confirms': True},
            'cluster_name': 'rabbit@b6a4a6555767',
            'copyright': 'Copyright (c) 2007-2019 Pivotal Software, Inc.',
            'information': 'Licensed under the MPL 1.1. '
                           'Website: https://rabbitmq.com',
            'platform': 'Erlang/OTP 22.2.8',
            'product': 'RabbitMQ',
            'version': '3.8.2'}

        """
        return self._channel0.properties

    async def _close(self) -> None:
        LOGGER.debug('Internal close method invoked')
        self._set_state(STATE_CLOSING)
        await self._channel0.close()
        self._transport.close()
        self._set_state(STATE_CLOSED)
        self._reset()

    async def _connect(self) -> None:
        self._set_state(STATE_CONNECTING)
        LOGGER.info('Connecting to %s://%s:%s@%s:%s/%s',
                    self._url.scheme, self._url.user,
                    ''.ljust(len(self._url.password), '*'),
                    self._url.host, self._url.port,
                    parse.quote(self._url.path[1:], ''))
        self._channel0 = channel0.Channel0(
            self._blocked,
            self._url.user,
            self._url.password,
            self._url.path[1:],
            self._url.query.get('heartbeat'),
            self._defaults.locale,
            self._loop,
            int(self._url.query.get('channel_max', '32768')),
            self._defaults.product,
            self._on_remote_close)
        self._max_frame_size = float(self._channel0.max_frame_size)

        ssl = self._url.scheme == 'amqps'
        future = self._loop.create_connection(
            lambda: protocol.AMQP(
                self._on_connected,
                self._on_disconnected,
                self._on_frame,
            ), self._url.host, self._url.port,
            server_hostname=self._url.host if ssl else None,
            ssl=ssl)
        try:
            self._transport, self._protocol = await asyncio.wait_for(
                future, timeout=self._connect_timeout)
        except asyncio.TimeoutError as exc:
            self._set_state(state.STATE_EXCEPTION, exc)
            raise
        else:
            self._max_frame_size = float(self._channel0.max_frame_size)
            await self._channel0.open(self._transport)
            self._set_state(STATE_OPENED)

    @property
    def _connect_timeout(self) -> float:
        temp = self._url.query.get('connection_timeout', '3.0')
        return socket.getdefaulttimeout() if temp is None else float(temp)

    def _execute_callback(self, callback: callable, *args) -> None:
        """Sync wrapper for invoking a sync/async callback and invoking
        the callback on the IOLoop if it returned a coroutine (async def).

        """
        result = callback(*args)
        if asyncio.iscoroutine(result):
            self._loop.call_soon(asyncio.ensure_future, result)

    def _on_connected(self) -> None:
        self._set_state(STATE_CONNECTED)

    def _on_disconnected(self, exc: Exception) -> None:
        LOGGER.debug('Disconnected [%r] (%i) %s', exc, self._state, self.state)

    def _on_frame(self, channel: int, value: frame.FrameTypes) -> None:
        self._last_frame = value
        if channel == 0:
            try:
                self._channel0.process(value)
            except (exceptions.AIORabbitException,
                    pamqp_exceptions.PAMQPException) as exc:
                self._set_state(state.STATE_EXCEPTION, exc)
        elif isinstance(value, commands.Basic.Ack):
            self._set_state(STATE_BASIC_ACK_RECEIVED)
            LOGGER.debug('Received ack for delivery_tag %i',
                         value.delivery_tag)
            self._acks.add(value.delivery_tag)
        elif isinstance(value, commands.Basic.CancelOk):
            self._set_state(STATE_BASIC_CANCELOK_RECEIVED)
        elif isinstance(value, commands.Basic.ConsumeOk):
            self._set_state(STATE_BASIC_CONSUMEOK_RECEIVED)
            future, callback = self._pending_consumers.popleft()
            self._logger.debug('Adding consumer tag %r: %r (%r)',
                               value.consumer_tag, callback, future)
            self._consumers[value.consumer_tag] = callback
            future.set_result(value.consumer_tag)
        elif isinstance(value, commands.Basic.Deliver):
            self._set_state(STATE_BASIC_DELIVER_RECEIVED)
            self._message = message.Message(value)
        elif isinstance(value, commands.Basic.GetEmpty):
            self._set_state(STATE_BASIC_GETEMPTY_RECEIVED)
            self._consumers['GetOk'].set_result(None)
        elif isinstance(value, commands.Basic.GetOk):
            self._set_state(STATE_BASIC_GETOK_RECEIVED)
            self._message = message.Message(value)
        elif isinstance(value, commands.Basic.Nack):
            self._set_state(STATE_BASIC_NACK_RECEIVED)
            LOGGER.debug('Received nack for delivery_tag %i',
                         value.delivery_tag)
            self._nacks.add(value.delivery_tag)
        elif isinstance(value, commands.Basic.QosOk):
            self._set_state(STATE_BASIC_QOSOK_RECEIVED)
        elif isinstance(value, commands.Basic.RecoverOk):
            self._set_state(STATE_BASIC_RECOVEROK_RECEIVED)
        elif isinstance(value, commands.Basic.Reject):
            self._set_state(STATE_BASIC_REJECT_RECEIVED)
            LOGGER.debug('Received reject for delivery_tag %i',
                         value.delivery_tag)
            self._rejects.add(value.delivery_tag)
        elif isinstance(value, commands.Basic.Return):
            self._set_state(STATE_BASIC_RETURN_RECEIVED)
            self._message = message.Message(value)
        elif isinstance(value, commands.Channel.OpenOk):
            self._set_state(STATE_CHANNEL_OPENOK_RECEIVED)
        elif isinstance(value, commands.Channel.Close):
            self._set_state(STATE_CHANNEL_CLOSE_RECEIVED)
            self._on_channel_closed(value)
        elif isinstance(value, commands.Channel.CloseOk):
            self._channel_open.clear()
            self._set_state(STATE_CHANNEL_CLOSEOK_RECEIVED)
        elif isinstance(value, commands.Confirm.SelectOk):
            self._set_state(STATE_CONFIRM_SELECTOK_RECEIVED)
        elif isinstance(value, header.ContentHeader):
            self._set_state(STATE_CONTENT_HEADER_RECEIVED)
            self._message.header = value
        elif value.name == 'ContentBody':
            self._set_state(STATE_CONTENT_BODY_RECEIVED)
            self._message.body_frames.append(value)
            if self._message.complete:
                self._logger.debug('Message completed: %r (%r)',
                                   self._message, self._message.method)
                self._set_state(STATE_MESSAGE_ASSEMBLED)
                method = None
                if isinstance(self._message.method, commands.Basic.Deliver):
                    method = self._consumers[self._message.consumer_tag]
                elif isinstance(self._message.method, commands.Basic.GetOk):
                    self._consumers['GetOk'].set_result(self._pop_message())
                elif isinstance(self._message.method, commands.Basic.Return):
                    method = self._on_message_return
                else:
                    self._set_state(
                        state.STATE_EXCEPTION,
                        RuntimeError('Unsupported message frame'))
                if method is not None:
                    self._execute_callback(method, self._pop_message())

        elif isinstance(value, commands.Exchange.BindOk):
            self._set_state(STATE_EXCHANGE_BINDOK_RECEIVED)
        elif isinstance(value, commands.Exchange.DeclareOk):
            self._set_state(STATE_EXCHANGE_DECLAREOK_RECEIVED)
        elif isinstance(value, commands.Exchange.DeleteOk):
            self._set_state(STATE_EXCHANGE_DELETEOK_RECEIVED)
        elif isinstance(value, commands.Exchange.UnbindOk):
            self._set_state(STATE_EXCHANGE_UNBINDOK_RECEIVED)
        elif isinstance(value, commands.Queue.BindOk):
            self._set_state(STATE_QUEUE_BINDOK_RECEIVED)
        elif isinstance(value, commands.Queue.DeclareOk):
            self._set_state(STATE_QUEUE_DECLAREOK_RECEIVED)
        elif isinstance(value, commands.Queue.DeleteOk):
            self._set_state(STATE_QUEUE_DELETEOK_RECEIVED)
        elif isinstance(value, commands.Queue.PurgeOk):
            self._set_state(STATE_QUEUE_PURGEOK_RECEIVED)
        elif isinstance(value, commands.Queue.UnbindOk):
            self._set_state(STATE_QUEUE_UNBINDOK_RECEIVED)
        elif isinstance(value, commands.Tx.SelectOk):
            self._set_state(STATE_TX_SELECTOK_RECEIVED)
        elif isinstance(value, commands.Tx.CommitOk):
            self._set_state(STATE_TX_COMMITOK_RECEIVED)
        elif isinstance(value, commands.Tx.RollbackOk):
            self._set_state(STATE_TX_ROLLBACKOK_RECEIVED)
        else:
            self._set_state(state.STATE_EXCEPTION,
                            RuntimeError('Unsupported AMQ method'))

    def _on_channel_closed(self, value: commands.Channel.Close) -> None:
        LOGGER.info('Channel closed: (%i) %s',
                    value.reply_code, value.reply_text)
        self._channel_open.clear()
        self._write(commands.Channel.CloseOk())
        self._set_state(STATE_CHANNEL_CLOSEOK_SENT)
        self._loop.call_soon(asyncio.ensure_future, self._open_channel())

    def _on_remote_close(self, status_code: int, exc: Exception) -> None:
        LOGGER.debug('Remote close received %i (%r)', status_code, exc)
        self._set_state(STATE_CLOSED, exc)

    async def _open_channel(self) -> None:
        LOGGER.debug('Opening channel')
        self._set_state(STATE_OPENING_CHANNEL)
        self._channel += 1
        if self._channel > self._channel0.max_channels:
            self._channel = 1
        self._write(commands.Channel.Open())
        self._set_state(STATE_CHANNEL_OPEN_SENT)
        await self._wait_on_state(STATE_CHANNEL_OPENOK_RECEIVED)
        self._channel_open.set()
        LOGGER.debug('Channel open')

    def _pop_message(self) -> message.Message:
        if not self._message:
            raise RuntimeError('Missing message')
        value = self._message
        self._message = None
        return value

    async def _reconnect(self) -> None:
        LOGGER.debug('Reconnecting')
        publisher_confirms = self._publisher_confirms
        self._reset()
        LOGGER.debug('Pre-reconnect state: %r', self.state)
        await self._connect()
        LOGGER.debug('Post-connected on reconnect')
        await self._open_channel()
        LOGGER.debug('Post open state: %r', self.state)
        if publisher_confirms:
            await self.confirm_select()
        LOGGER.debug('State: %r', self.state)

    def _reset(self) -> None:
        LOGGER.debug('Resetting internal state')
        self._blocked.clear()
        self._channel = 0
        self._channel_open.clear()
        self._channel0 = None
        self._connected.clear()
        self._exception = None
        self._protocol = None
        self._publisher_confirms = False
        self._transport = None
        self._state = STATE_CLOSED
        self._state_start = self._loop.time()

    @staticmethod
    def _validate_bool(name: str, value: typing.Any) -> None:
        if not isinstance(value, bool):
            raise TypeError('{} must be of type bool'.format(name))

    def _validate_exchange_name(self, name: str, value: typing.Any) -> None:
        if value == '':
            return
        self._validate_short_str(name, value)
        if NamePattern.match(value) is None:
            raise ValueError('name must only contain letters, digits, hyphen, '
                             'underscore, period, or colon.')

    @staticmethod
    def _validate_field_table(name: str, value: typing.Any) -> None:
        if not isinstance(value, dict):
            raise TypeError('{} must be of type dict'.format(name))
        elif not all(isinstance(k, str) and 0 < len(k) <= 256
                     for k in value.keys()):
            raise ValueError('{} keys must all be of type str and '
                             'less than 256 characters'.format(name))

    @staticmethod
    def _validate_short_str(name: str, value: typing.Any) -> None:
        if not isinstance(value, str):
            raise TypeError('{} must be of type str'.format(name))
        elif len(value) > 256:
            raise ValueError('{} must not exceed 256 characters'.format(name))

    def _write(self, value: frame.FrameTypes) -> None:
        LOGGER.debug('Writing frame %r to channel %i', value, self._channel)
        self._transport.write(frame.marshal(value, self._channel))

    async def _wait_on_state(self, *args) -> int:
        try:
            result = await super()._wait_on_state(*args)
        except pamqp_exceptions.AMQPError as exc:
            LOGGER.warning('Exception raised while waiting: %s (%i) %s',
                           exc, self._state, self.state)
            await self._reconnect()
            raise exc
        else:
            self._logger.debug('Post state._wait_on_state: %r', result)
            return result
