# SNMP Interface Bandwidth Monitor — No Docker edition

This project implements **Unit 2 / Topic 2: Automating Interface Bandwidth Bottleneck Detection**.

Unlike the original Docker edition, this project requires only Python. A small educational SNMPv1 agent starts on `127.0.0.1:1161`, exposes real OS network interface counters using psutil, and the Python dashboard polls those values using SNMPv1 `GETNEXT` requests over UDP.

## Quickstart on Windows

1. Install **Python 3.11 or 3.12** from https://www.python.org/downloads/ (or use an existing supported installation).
2. Extract this ZIP, open the extracted **snmp_bandwidth_no_docker** folder in File Explorer.
3. Click the folder path bar, type `powershell`, and press Enter.
4. Execute:

```powershell
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

If `py` is not recognized, use `python` instead of `py` (after verifying `python --version`).
5. Open http://localhost:8501 in your browser.
6. Select **Live SNMP v1** to view real network-interface counters from the laptop. Allow 10 seconds for samples. If an interface does not report its link speed, utilization displays as unknown rather than inventing a speed.
7. Select **Simulated classroom demo**, threshold `70%`, and watch for synthetic utilization to rise to `84%`, showing an alert. Clearly state that these are simulated values.

## Deploy the no-Docker version online, free

1. Create a GitHub repository at https://github.com/new.
2. Upload the files (`app.py`, `monitor.py`, `snmp_proto.py`, `local_agent.py`, `requirements.txt`, `README.md`) into the **root of the repository**.
3. Visit https://share.streamlit.io, log in with GitHub, and select **Create app**.
4. Pick the repo/branch and set app entrypoint to `app.py`. Click **Deploy**.
5. Streamlit Community Cloud provides a public HTTPS URL ending in `streamlit.app`.

**Important:** When viewed online, **Live SNMP v1** monitors the cloud host's network interface stats, NOT the visitor's computer or Wi-Fi. **Simulated classroom demo** is the predictable alarm demonstration. Free Community Cloud resource limits and idle behavior may interrupt monitoring. The internal test agent uses loopback UDP only and does not expose SNMP to the Internet.

## How SNMP works here

`psutil` (real host counters) → minimal built-in SNMPv1 agent → UDP GETNEXT → Python SNMPv1 client → rate calculations → Streamlit dashboard and alert log.

MIB-II `interfacesGroup`: `ifDescr (.2)`, `ifSpeed (.5)`, `ifOperStatus (.8)`, `ifInOctets (.10)`, `ifOutOctets (.16)`. These OIDs are below `.1.3.6.1.2.1.2.2.1` and use index suffixes. The code supports just enough ASN.1 BER encoding to transfer these values. It is an educational subset, not a production SNMP stack.

Bandwidth: `(counter_new - counter_old) % 2^32 × 8 / (seconds × 1,000,000)`. Warn when the higher of received or sent Mbps reaches the threshold percentage of reported physical link speed. This calculation treats duplex directions separately, rather than adding them.

## How to present (one minute)

- "This project automates network interface bandwidth monitoring using the SNMP v1 protocol."
- "A lightweight Python test agent reports actual interface statistics using standard MIB-II OIDs."
- "Our client sends SNMP GETNEXT requests and calculates Mbps from changing byte counters."
- "The website plots bandwidth and warns when link utilization is too high."
- "I will switch to a clearly simulated congestion example to demonstrate a warning."
- "The dashboard is deployed online using Streamlit Community Cloud, with no Docker required."

## Limitations

- SNMP v1 is unencrypted. The training agent listens **only on localhost** and should not be shared over public UDP.
- This is a small custom teaching agent, not an enterprise-grade SNMP service. It implements a subset of `interfacesGroup`, not `addressTranslationGroup` or all SNMP behaviors.
- Link speed can be unknown (`0`); when unknown, the app shows Mbps but no utilization percentage.
- Under high-speed load, 32-bit counters can wrap multiple times between samples; this app handles only single wraps.
- Reports are kept in current browser session only.

## Tests

```powershell
py -m pip install pytest
py -m pytest -q
```
