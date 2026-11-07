# Watching my desk-node connections

I built a connection monitor because a missing room reading can mean either a
sensor problem or a lost connection. I can rehearse a bad connection on my
computer and see which alarms I would get before using a real node.

```sh
.venv/bin/pip install -r networking/requirements.txt
.venv/bin/python -m networking.links --demo --count 10
.venv/bin/python -m pytest networking/tests -q
```

The demo opens a real local TCP connection, then deliberately delays or closes
some replies. Loss here means failed application probes, not a measured IP-layer
packet-loss rate. For an ESP32, `--host <node-address> --port 8092` polls its
health responder while it is awake. The node sleeps between readings, so I must
schedule polling inside that wake window or expect an offline status.

My intended layout is ESP32 nodes on a WPA2/WPA3 protected Wi-Fi sensor network,
a gateway on that network, and LifeOS behind the gateway. I have not verified
that physical layout. The firmware responds to a nonce-based TCP health probe;
no calendar details or credentials are exposed. The monitor keeps ten probes.
After at least three samples, loss of at least 20% or mean successful latency
above 100 ms raises an alarm. Three consecutive healthy windows clear it.
Status is whether the last probe succeeded. A snapshot older than five seconds
is offline with an alarm even if the poller has stopped.

## SNMP status

SNMP is a standard way for a monitoring program to ask for device status. I use
Net-SNMP's real agent and its `pass_persist` protocol to expose the Python
snapshot, rather than writing a pretend SNMP server. In a private local demo
configuration, replace paths with the checkout and Python executable:

```conf
agentaddress udp:127.0.0.1:1161
rocommunity desk-demo 127.0.0.1
pass_persist .1.3.6.1.4.1.8072.9999.1 /absolute/path/.venv/bin/python -m networking.snmp /tmp/desk-link.json
```

Run `snmpd -f -Lo -C -c /path/to/demo.conf` from the repository root, then
`snmpwalk -v2c -c desk-demo -On 127.0.0.1:1161 .1.3.6.1.4.1.8072.9999.1`.
The four integer scalars `.1.0` through `.4.0` are up/down, mean latency in
milliseconds, loss percentage and alarm. This is Net-SNMP's local experimental
subtree, not my own assigned enterprise number. SNMPv2c is deliberately
loopback-only; for a remote deployment I would configure SNMPv3 authentication
and encryption. Stop the foreground agent with Ctrl-C. The Linux integration
test starts its own agent, queries it over UDP, walks all four values and stops it.

## Saving readings over MQTT

MQTT lets a sensor publish a reading to a broker which forwards it to a
subscriber. The simulated source and gateway use TLS, which encrypts traffic
and checks the broker certificate and name. The gateway saves accepted readings
in the existing adapter's SQLite `readings` table, using the same bounded batch
schema and deduplication rules. No live LifeOS account is needed.

On Linux with Docker Compose installed:

```sh
networking/deploy/certificates.sh
mkdir -p networking/build/data
chmod 777 networking/build/data # isolated demo only; use a matching UID in deployment
 docker compose -f networking/compose.yml up --build -d broker gateway
 docker compose -f networking/compose.yml --profile send run --rm sensor
curl 'http://localhost:8093/v1/readings/000000000001?limit=1'
 docker compose -f networking/compose.yml down -v
```

The two-day certificate authority and keys are generated locally and ignored by
git. `sensor` publishes labelled synthetic readings. `--source batch.json` uses
a captured ESP32 adapter batch instead. The current ESP32 upload remains HTTPS;
MQTT publishing is the simulated replay source, not a flashed MQTT ESP32 claim.
`desk/<12-hex-device>/readings` contains `device`, `session` (16 hex digits),
`dropped` and 1..64 `readings` with integer `sequence`, Unix `timestamp`,
`temperature_mc` (-45000..125000) and `humidity_mpermil` (0..100000).
A reused identity with changed data is rejected. QoS 1 may redeliver a batch;
the database's compound primary key prevents duplicate rows. Status topics
`desk/<device>/status` and `desk/gateway/status` retain online/offline values,
with an offline last will on ungraceful loss. The subscriber re-subscribes after
broker reconnect with bounded exponential backoff and a 64-message send queue.
The read API returns latest or historical rows with `limit=1..1000`.

This isolated broker permits anonymous clients. Before remote use I need
per-device credentials/ACLs and a real CA. The read API binds only to the host's
loopback through Compose. It does not expose private LifeOS routes.

`networking/deploy/firewall.nft` belongs inside a dedicated Linux gateway network
namespace. It accepts only TCP 8883 from the sensor address, allows established
replies and drops other inbound/forwarded traffic. The CI test first proves that
port 8884 is listening, then proves that the rule blocks it while a verified TLS
MQTT CONNECT on 8883 succeeds. It never changes the Mac's firewall.

A packet capture of a normal connection shows TCP setup, a TLS handshake and
encrypted application records; it does not reveal JSON readings. A rejected
connection shows unanswered SYN retries because the rule drops packets. DNS
resolves the broker name and NTP sets time before certificate validation on a
real node; the isolated test uses fixed addresses and the runner's clock. None
of these tests measures real radio loss or validates a home Wi-Fi installation.
