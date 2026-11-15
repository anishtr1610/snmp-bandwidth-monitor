"""Small, stdlib-only subset of SNMP v1 BER for an educational localhost agent.

Supports GetNextRequest / GetResponse on scalar interface-table columns only.
This is not a general SNMP implementation or a production SNMP agent.
"""
from __future__ import annotations

import socket
import struct
import random


def _length(n: int) -> bytes:
    if n < 128:
        return bytes([n])
    packed = n.to_bytes((n.bit_length() + 7) // 8, 'big')
    return bytes([0x80 | len(packed)]) + packed


def tlv(tag: int, data: bytes) -> bytes:
    return bytes([tag]) + _length(len(data)) + data


def int_tlv(number: int, tag: int = 0x02) -> bytes:
    # SNMP unsigned 32-bit values must include a leading zero when MSB is set.
    if tag in (0x41, 0x42):
        raw = (number % (2 ** 32)).to_bytes(4, 'big').lstrip(b'\0') or b'\0'
        if raw[0] >= 128:
            raw = b'\0' + raw
    else:
        width = max(1, (number.bit_length() + 8) // 8)
        raw = number.to_bytes(width, 'big', signed=True)
        while len(raw) > 1 and ((raw[0] == 0 and raw[1] < 128) or (raw[0] == 255 and raw[1] >= 128)):
            raw = raw[1:]
    return tlv(tag, raw)


def _base128(n: int) -> bytes:
    bits = [n & 127]
    n >>= 7
    while n:
        bits.insert(0, 0x80 | (n & 127))
        n >>= 7
    return bytes(bits)


def oid_tlv(oid: str) -> bytes:
    arcs = [int(part) for part in oid.strip('.').split('.')]
    if len(arcs) < 2 or arcs[0] not in (0, 1, 2) or (arcs[0] < 2 and arcs[1] >= 40):
        raise ValueError('Invalid OID')
    payload = _base128(40 * arcs[0] + arcs[1]) + b''.join(_base128(i) for i in arcs[2:])
    return tlv(0x06, payload)


def parse_tlv(data: bytes, pos: int = 0) -> tuple[int, bytes, int]:
    if pos + 2 > len(data):
        raise ValueError('Truncated TLV')
    tag = data[pos]
    length = data[pos + 1]
    pos += 2
    if length & 0x80:
        count = length & 127
        if count == 0 or count > 4 or pos + count > len(data):
            raise ValueError('Invalid BER length')
        length = int.from_bytes(data[pos:pos + count], 'big')
        pos += count
    if pos + length > len(data):
        raise ValueError('Truncated BER value')
    return tag, data[pos:pos + length], pos + length


def parse_oid(data: bytes) -> str:
    values = []
    value = 0
    for b in data:
        value = (value << 7) | (b & 127)
        if not (b & 128):
            values.append(value)
            value = 0
    if not values or (data and data[-1] & 128):
        raise ValueError('Invalid OID payload')
    first = values.pop(0)
    if first < 40:
        arcs = [0, first]
    elif first < 80:
        arcs = [1, first - 40]
    else:
        arcs = [2, first - 80]
    return '.'.join(map(str, arcs + values))


def parse_int(data: bytes, unsigned: bool = False) -> int:
    return int.from_bytes(data, 'big', signed=not unsigned)


def encode_message(pdu_tag: int, community: str, request_id: int, oid: str,
                   value_tag: int = 0x05, value: int | str | None = None,
                   error_status: int = 0) -> bytes:
    if value_tag == 0x04:
        value_bytes = tlv(0x04, str(value).encode('utf-8'))
    elif value_tag == 0x05:
        value_bytes = tlv(0x05, b'')
    else:
        value_bytes = int_tlv(int(value or 0), value_tag)
    varbind = tlv(0x30, oid_tlv(oid) + value_bytes)
    pdu = tlv(pdu_tag, int_tlv(request_id) + int_tlv(error_status) + int_tlv(0) + tlv(0x30, varbind))
    return tlv(0x30, int_tlv(0) + tlv(0x04, community.encode('ascii')) + pdu)


def decode_message(payload: bytes) -> dict:
    tag, outer, end = parse_tlv(payload)
    if tag != 0x30 or end != len(payload):
        raise ValueError('Invalid SNMP envelope')
    pos = 0
    tag, ver, pos = parse_tlv(outer, pos)
    if tag != 0x02 or parse_int(ver) != 0:
        raise ValueError('Not SNMP v1')
    tag, community, pos = parse_tlv(outer, pos)
    if tag != 0x04:
        raise ValueError('Missing community')
    pdu_tag, pdu, pos = parse_tlv(outer, pos)
    if pos != len(outer):
        raise ValueError('Extra SNMP message data')
    index = 0
    tag, req, index = parse_tlv(pdu, index)
    if tag != 0x02:
        raise ValueError('Invalid request ID')
    tag, status, index = parse_tlv(pdu, index)
    tag, error_index, index = parse_tlv(pdu, index)
    tag, bind_list, index = parse_tlv(pdu, index)
    if tag != 0x30 or index != len(pdu):
        raise ValueError('Invalid varbind list')
    tag, bind, index = parse_tlv(bind_list)
    if tag != 0x30 or index != len(bind_list):
        raise ValueError('Invalid varbind')
    tag, oid, bind_pos = parse_tlv(bind)
    if tag != 0x06:
        raise ValueError('Invalid varbind OID')
    value_tag, value_raw, bind_pos = parse_tlv(bind, bind_pos)
    if bind_pos != len(bind):
        raise ValueError('Invalid varbind value')
    if value_tag == 0x04:
        value = value_raw.decode('utf-8', errors='replace')
    elif value_tag in (0x02, 0x41, 0x42, 0x43):
        value = parse_int(value_raw, unsigned=value_tag != 0x02)
    else:
        value = None
    return {'pdu_tag': pdu_tag, 'community': community.decode('ascii'),
            'request_id': parse_int(req), 'error_status': parse_int(status),
            'oid': parse_oid(oid), 'value_tag': value_tag, 'value': value}


def get_next(host: str, port: int, community: str, oid: str, timeout: float = 1.5) -> tuple[str, object] | None:
    req_id = random.randint(1, 2 ** 31 - 1)
    data = encode_message(0xA1, community, req_id, oid)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(data, (host, port))
        response, _ = sock.recvfrom(65507)
    message = decode_message(response)
    if message['pdu_tag'] != 0xA2 or message['request_id'] != req_id or message['community'] != community:
        raise ValueError('Unexpected SNMP response')
    if message['error_status'] == 2:  # noSuchName: reached end of MIB
        return None
    if message['error_status'] != 0:
        raise ValueError(f"SNMP error status {message['error_status']}")
    return message['oid'], message['value']
