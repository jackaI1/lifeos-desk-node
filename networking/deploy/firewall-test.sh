#!/usr/bin/env bash
# CI-only: two owned network namespaces. Requires iproute2, nftables, mosquitto.
set -euo pipefail
root=$(pwd)
name="desk-fw-$$"
gw="${name}-gw"
sensor="${name}-sensor"
broker_pid=''
trap 'if [[ -n "$broker_pid" ]]; then kill "$broker_pid" 2>/dev/null || true; wait "$broker_pid" 2>/dev/null || true; fi; ip netns del "$sensor" 2>/dev/null || true; ip netns del "$gw" 2>/dev/null || true' EXIT
ip netns add "$gw"
ip netns add "$sensor"
ip link add dg type veth peer name ds
ip link set dg netns "$gw"
ip link set ds netns "$sensor"
ip -n "$gw" addr add 10.77.0.1/24 dev dg
ip -n "$sensor" addr add 10.77.0.2/24 dev ds
ip -n "$gw" link set dg up
ip -n "$sensor" link set ds up
ip -n "$gw" link set lo up
ip -n "$sensor" link set lo up
cat > networking/build/firewall-broker.conf <<CONF
user root
listener 8883
listener 8884
cafile $root/networking/build/certs/ca.crt
certfile $root/networking/build/certs/server.crt
keyfile $root/networking/build/certs/server.key
allow_anonymous true
CONF
ip netns exec "$gw" mosquitto -c "$root/networking/build/firewall-broker.conf" > networking/build/firewall-broker.log 2>&1 &
broker_pid=$!
# Prove the blocked service is actually listening before applying the rule.
ip netns exec "$sensor" python3 -c 'import socket,time
for attempt in range(50):
 try:
  socket.create_connection(("10.77.0.1",8884),.2).close(); break
 except OSError: time.sleep(.1)
else: raise SystemExit("broker never listened")'
ip netns exec "$gw" nft -f networking/deploy/firewall.nft
ip netns exec "$sensor" python3 -c 'import socket,ssl
context=ssl.create_default_context(cafile="networking/build/certs/ca.crt")
with socket.create_connection(("10.77.0.1",8883),1) as raw:
 with context.wrap_socket(raw,server_hostname="localhost") as tls:
  # MQTT 3.1.1 CONNECT followed by a successful CONNACK.
  tls.sendall(bytes.fromhex("101000044d5154540402000500046465736b"))
  assert tls.recv(4)==bytes.fromhex("20020000")
try: socket.create_connection(("10.77.0.1",8884),.3)
except OSError: print("PASS: TLS/MQTT 8883 allowed; listening port 8884 blocked")
else: raise AssertionError("firewall allowed forbidden port")'
ip netns exec "$gw" nft list ruleset > networking/build/firewall-rules.txt
