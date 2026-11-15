"""SNMPv1 interface-table polling and bandwidth-rate calculation."""
from __future__ import annotations
import os
from snmp_proto import get_next

IF_BASE = '1.3.6.1.2.1.2.2.1'
FIELDS = {
    'name': f'{IF_BASE}.2',      # ifDescr
    'speed': f'{IF_BASE}.5',     # ifSpeed
    'status': f'{IF_BASE}.8',    # ifOperStatus
    'in_octets': f'{IF_BASE}.10',
    'out_octets': f'{IF_BASE}.16',
}


class SNMPError(RuntimeError):
    pass


def walk(oid_prefix: str) -> dict[str, object]:
    host = os.getenv('SNMP_TARGET_HOST', '127.0.0.1')
    port = int(os.getenv('SNMP_TARGET_PORT', '1161'))
    community = os.getenv('SNMP_COMMUNITY', 'labMonitor')
    current = oid_prefix
    values = {}
    try:
        for _ in range(256):
            nxt = get_next(host, port, community, current)
            if nxt is None:
                break
            oid, value = nxt
            if not oid.startswith(oid_prefix + '.'):
                break
            if oid == current:
                raise SNMPError('Agent returned repeated OID')
            values[oid[len(oid_prefix) + 1:]] = value
            current = oid
    except (OSError, ValueError) as exc:
        raise SNMPError(str(exc)) from exc
    return values


def poll_interfaces() -> dict[str, dict]:
    cols = {field: walk(oid) for field, oid in FIELDS.items()}
    result = {}
    for idx, name in cols['name'].items():
        result[idx] = {
            'index': idx, 'name': name,
            'speed': cols['speed'].get(idx),
            'status': cols['status'].get(idx),
            'in_octets': cols['in_octets'].get(idx),
            'out_octets': cols['out_octets'].get(idx),
        }
    if not result:
        raise SNMPError('Agent did not return any interface data')
    return result


def calculate_rates(previous: dict | None, current: dict, elapsed: float) -> dict:
    row = dict(current)
    row.update(in_mbps=None, out_mbps=None, utilization=None)
    if previous is None or elapsed <= 0 or any(previous.get(k) is None or current.get(k) is None for k in ('in_octets', 'out_octets')):
        return row
    incoming = (current['in_octets'] - previous['in_octets']) % (2 ** 32)
    outgoing = (current['out_octets'] - previous['out_octets']) % (2 ** 32)
    row['in_mbps'] = incoming * 8 / elapsed / 1_000_000
    row['out_mbps'] = outgoing * 8 / elapsed / 1_000_000
    speed = current.get('speed')
    if speed and speed > 0:
        row['utilization'] = 100 * max(incoming, outgoing) * 8 / elapsed / speed
        if row['utilization'] > 120:
            row.update(in_mbps=None, out_mbps=None, utilization=None)
    return row
