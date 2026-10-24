# Network deployment notes

The original deployment used a Windows machine behind a private campus network. The table below summarizes the topology; identifying network addresses are intentionally excluded from the public repository.

| Observation | Result |
|---|---|
| Active adapter | Ethernet |
| Negotiated Ethernet speed | 1 Gbps |
| Local IPv4 address | Private campus subnet; address omitted |
| Default gateway | Campus-managed gateway; address omitted |
| Public egress address observed via HTTPS | Different from the private host address; address omitted |
| Globally routable IPv6 address | None observed |
| Windows network profile | Public; IPv4 reports Internet |
| WinHTTP proxy | Direct access |

The private address and different egress address indicate NAT upstream. This inspection cannot determine whether that NAT is managed by the college, ISP or multiple layers; it does not establish carrier-grade NAT. The public egress address does not establish port-forwarding rights or inbound reachability. Local IPs can change with DHCP.

**1 Gbps is the local Ethernet link speed. Internet upload, Internet download, tunnel capacity and concurrent-session capacity have not been measured.** No campus network scan, router administration, firewall modification, inbound port opening or bandwidth stress test was performed. Firewall policy details were not successfully retrieved and are not assumed.

## Chosen route

```text
Windows host ──outbound WSS──┐
                            ├─ public HTTPS tunnel edge
Outside browser ──WSS───────┘              │
                                  outbound tunnel
                                          │
                              office relay 127.0.0.1:8787
```

The office machine runs the relay. All session frames and controls pass through it and its network connection. The public edge is still necessary to reach a private network without inbound forwarding. Its bandwidth, uptime, policies and latency also limit performance. Neither a private address nor an outbound tunnel guarantees 1 Gbps remote desktop throughput.

The relay binds to loopback, so the Windows Public profile does not need an inbound firewall exception. Other campus computers use the public HTTPS tunnel URL as well. The outbound tunnel must be permitted by the college network administrator; this implementation does not change or bypass campus policy.

## External acceptance test

1. Start a permitted outbound tunnel using the supplied launcher or named-tunnel config.
2. Connect the host to the resulting HTTPS URL.
3. Open that URL using a different network (for example mobile data).
4. Enter the host ID/key, approve locally, verify the image and controls, then disconnect.
5. Observe real session Mbps and latency before choosing a permanent service and sizing capacity.

The original operator subsequently reported a successful outside-network session through the temporary tunnel. That report does not establish a particular Internet throughput or 30/60 fps performance. `scripts/inspect-network.ps1` repeats the read-only inspection and writes `docs/network-inspection.json` locally; that file and the private original inspection notes are excluded from Git and release bundles.
