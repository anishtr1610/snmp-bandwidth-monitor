"""No-Docker educational SNMPv1 bandwidth dashboard with an internal localhost agent."""
from datetime import datetime
import time
import pandas as pd
import streamlit as st
from local_agent import ensure_agent
from monitor import SNMPError, calculate_rates, poll_interfaces

st.set_page_config(page_title='SNMP Bandwidth Monitor', page_icon='📡', layout='wide')
st.title('📡 SNMP Interface Bandwidth Monitor')
st.caption('Network Management · Unit 2, Topic 2 · SNMP v1 · MIB-II interfacesGroup')

try:
    ensure_agent()
except OSError as exc:
    st.error(f'Could not start the built-in local SNMP agent: {exc}')
    st.stop()

st.info('**Live mode:** a minimal educational SNMP v1 agent exposes real network-interface counters from the machine **running this app**. On Streamlit Cloud, that means the cloud server, not your Windows laptop. **Demo mode** uses clearly labeled synthetic traffic.')
mode = st.sidebar.radio('Monitoring source', ['Live SNMP v1', 'Simulated classroom demo'])
threshold = st.sidebar.slider('Bandwidth warning threshold (%)', 1, 100, 70)
st.sidebar.markdown('**SNMP:** v1 (GETNEXT, localhost only)\n\n**Polling:** every 5 seconds\n\n**Port:** UDP 1161\n\n**MIB:** ifDescr, ifSpeed, ifOperStatus, ifInOctets, ifOutOctets')
if st.sidebar.button('Clear sample history'):
    st.session_state.clear()
    st.rerun()

for key, default in [('samples', []), ('alerts', []), ('previous', {}), ('last_poll', None), ('sample_number', 0), ('previous_mode', mode)]:
    if key not in st.session_state:
        st.session_state[key] = default
if st.session_state.previous_mode != mode:
    st.session_state.samples = []
    st.session_state.alerts = []
    st.session_state.previous = {}
    st.session_state.last_poll = None
    st.session_state.sample_number = 0
    st.session_state.previous_mode = mode

@st.fragment(run_every='5s')
def dashboard():
    now = time.time()
    stamp = datetime.now().strftime('%H:%M:%S')
    if mode == 'Live SNMP v1':
        try:
            polled = poll_interfaces()
        except SNMPError as exc:
            st.error(f'SNMP polling failed: {exc}')
            return
        elapsed = (now - st.session_state.last_poll) if st.session_state.last_poll is not None else 0
        rows = [calculate_rates(st.session_state.previous.get(idx), data, elapsed) for idx, data in polled.items()]
        st.session_state.previous = polled
        st.session_state.last_poll = now
    else:
        n = st.session_state.sample_number
        inbound = 12.0 if n % 8 < 4 else 84.0
        outbound = 4.0 if n % 8 < 4 else 30.0
        rows = [{'name': 'SIMULATED Demo Ethernet', 'status': 1, 'speed': 100_000_000,
                 'in_mbps': inbound, 'out_mbps': outbound, 'utilization': max(inbound, outbound)}]
        st.session_state.sample_number += 1

    measured = [row for row in rows if row['utilization'] is not None]
    peak = max(measured, key=lambda x: x['utilization'], default=None)
    violations = sum((r['utilization'] is not None and r['utilization'] >= threshold) or r['status'] == 2 for r in rows)
    c1, c2, c3 = st.columns(3)
    c1.metric('Interfaces', len(rows))
    c2.metric('Highest link usage', f"{peak['utilization']:.2f}%" if peak else 'Waiting for second sample / speed')
    c3.metric('Current warnings', violations)

    table = []
    for row in rows:
        usage = row['utilization']
        alert = (usage is not None and usage >= threshold) or row['status'] == 2
        if alert:
            msg = f"{stamp}: {row['name']} — " + ('interface DOWN' if row['status'] == 2 else f'{usage:.1f}% link usage >={threshold}% threshold')
            st.session_state.alerts.append(msg)
        table.append({'Interface': row['name'], 'Status': 'UP' if row['status'] == 1 else 'DOWN',
                      'Incoming Mbps': round(row['in_mbps'], 3) if row['in_mbps'] is not None else None,
                      'Outgoing Mbps': round(row['out_mbps'], 3) if row['out_mbps'] is not None else None,
                      'Link usage %': round(usage, 2) if usage is not None else None,
                      'Alert': 'WARNING' if alert else 'Normal'})
        if usage is not None:
            st.session_state.samples.append({'Time': stamp, 'Interface': row['name'],
                'Inbound Mbps': round(row['in_mbps'], 3), 'Outbound Mbps': round(row['out_mbps'], 3),
                'Usage %': round(usage, 2)})
    st.session_state.samples = st.session_state.samples[-360:]
    st.session_state.alerts = st.session_state.alerts[-100:]
    st.subheader('Monitored interfaces')
    st.dataframe(pd.DataFrame(table), hide_index=True, use_container_width=True)
    if violations:
        st.error('🚨 High bandwidth usage or interface DOWN!')
    else:
        st.success('No threshold violations at this reading.')
    hist = pd.DataFrame(st.session_state.samples)
    if not hist.empty:
        st.subheader('Traffic and utilization history')
        selected = st.selectbox('Interface graph', sorted(hist['Interface'].unique()))
        history = hist[hist['Interface'] == selected]
        st.line_chart(history, x='Time', y=['Inbound Mbps', 'Outbound Mbps'])
        st.line_chart(history, x='Time', y=['Usage %'])
        st.download_button('Export CSV', hist.to_csv(index=False), file_name='snmp_measurements.csv', mime='text/csv')
    st.subheader('Alert history')
    if st.session_state.alerts:
        st.code('\n'.join(st.session_state.alerts[-8:]))
    else:
        st.caption('No alerts yet.')
    st.caption('Real mode reads SNMP v1 Counter32 values. Utilization requires a known network-interface link speed. Demo mode does not use measured data.')

dashboard()
with st.expander('How the SNMP implementation works'):
    st.markdown('''
**Architecture:** The app starts a small Python SNMP v1 agent bound to **127.0.0.1:1161**.
It reads the machine's actual network-interface counters via `psutil` and exposes selected standard **MIB-II interfacesGroup OIDs**.
The monitoring client sends real UDP SNMP v1 **GETNEXT** requests to the agent, decodes responses and compares successive Counter32 readings.

**Formula:** inbound Mbps = `8 × change in ifInOctets / elapsed seconds / 1,000,000`.
Link usage (%) = `100 × max(inbound Mbps, outbound Mbps) / interface speed Mbps`.

**Scope:** This is a **minimal educational SNMPv1 implementation**, not a production-compliant, full-featured SNMP agent.
No hardware routers or Docker required. The deprecated `addressTranslationGroup` is not implemented by this minimal agent.
**Security:** SNMP v1 community strings are unencrypted, so the agent listens only on loopback. Use SNMPv3 for real network management.
''')
