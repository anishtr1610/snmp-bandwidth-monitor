"""Educational SNMPv1 agent; binds to 127.0.0.1 only (never expose publicly)."""
from __future__ import annotations
import os
import socket
import threading
import psutil
from snmp_proto import decode_message, encode_message

COMMUNITY = os.getenv('SNMP_COMMUNITY', 'labMonitor')
PORT = int(os.getenv('SNMP_PORT', '1161'))
BASE = '1.3.6.1.2.1.2.2.1'
STARTED = threading.Event()
LOCK = threading.Lock()
THREAD = None


def mib_rows() -> dict[str, tuple[int, str | int]]:
    """MIB-II ifTable values mapped to actual host interface counters."""
    counters = psutil.net_io_counters(pernic=True)
    stats = psutil.net_if_stats()
    table: dict[str, tuple[int, str | int]] = {}
    for index, name in enumerate(sorted(counters), start=1):
        count = counters[name]
        stat = stats.get(name)
        speed_bps = max(0, int(stat.speed)) * 1_000_000 if stat else 0
        status = 1 if stat and stat.isup else 2
        table[f'{BASE}.2.{index}'] = (0x04, name)                 # ifDescr
        table[f'{BASE}.5.{index}'] = (0x42, speed_bps)            # ifSpeed
        table[f'{BASE}.8.{index}'] = (0x02, status)               # ifOperStatus
        table[f'{BASE}.10.{index}'] = (0x41, count.bytes_recv)    # ifInOctets
        table[f'{BASE}.16.{index}'] = (0x41, count.bytes_sent)    # ifOutOctets
    return table


def _serve(sock: socket.socket) -> None:
    STARTED.set()
    while True:
        try:
            payload, addr = sock.recvfrom(8192)
            request = decode_message(payload)
            if request['pdu_tag'] != 0xA1 or request['community'] != COMMUNITY:
                continue
            rows = mib_rows()
            current = tuple(int(part) for part in request['oid'].split('.'))
            successors = sorted(rows, key=lambda oid: tuple(int(x) for x in oid.split('.')))
            successor = next((oid for oid in successors if tuple(int(x) for x in oid.split('.')) > current), None)
            if successor is None:
                response = encode_message(0xA2, COMMUNITY, request['request_id'], request['oid'], error_status=2)
            else:
                value_tag, value = rows[successor]
                response = encode_message(0xA2, COMMUNITY, request['request_id'], successor, value_tag, value)
            sock.sendto(response, addr)
        except (OSError, ValueError, KeyError):
            continue


def ensure_agent() -> None:
    global THREAD
    with LOCK:
        if THREAD is not None and THREAD.is_alive():
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('127.0.0.1', PORT))
        THREAD = threading.Thread(target=_serve, args=(sock,), daemon=True, name='local-snmp-v1-agent')
        THREAD.start()
        STARTED.wait(timeout=2)
