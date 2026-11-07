# Trying slow and interrupted desk uploads

I built a link rehearsal because I wanted to learn how a desk upload could keep
working when one network becomes slow or disappears. I replay small cellular-
and satellite-style delay traces, send actual local packets over two simulated
links, and choose the healthier one or send a duplicate during an outage.
These are made-up traces, not measurements of cellular or Starlink service.

From the repository root:

```sh
.venv/bin/pip install -r network_lab/requirements.txt
.venv/bin/python -m network_lab.links
.venv/bin/python -m pytest network_lab/tests -q
```

The demo prints measured round-trip time, selected link and delivered payload.
It also writes the active link's status to `/tmp/desk-link.json`, which the same
[SNMP agent](../docs/network-monitoring.md) can expose. The demo owns its local
UDP endpoints and stops them when it exits. It does not change the Mac's routes.

## Two links and a phone measurement

Each link delays or drops application packets over real UDP sockets. A bounded
five-sample window scores successful latency and failed probes. I switch only
when another link improves the score by more than 10 ms, and I use sequence
numbers and CRC-32 to check replies and deduplicate a duplicated upload. This
models steering at the application layer, not changing a modem or carrier route.

`android/` is a small Android app that requests Wi-Fi or cellular explicitly,
creates its socket through that selected network and records TCP connection
time. I enter the intended TLS server's hostname and tap the desired network.
It stores `measurements.jsonl` in its own app files. Android's connection time is
a useful network measurement, but is not an ICMP ping or pure propagation delay.
`android_measurements()` checks the exported JSONL schema before I use a capture.
CI compiles the APK; I have not run it on a phone or measured either carrier.

On Linux with Gradle 8.10.2, JDK 17 and Android SDK 35:

```sh
gradle -p network_lab/android :app:assembleDebug
```

## A radio waveform I can distort

OFDM sends many small frequency carriers together. I generate 64 QPSK carriers
and repeat 16 tail samples as a cyclic prefix. A real GNU Radio flowgraph runs
the generated samples through frequency-rotation, Gaussian-noise and delay blocks. I add a known
Doppler shift, a frequency change like the one caused by a moving satellite,
and compensate it before decoding. The tests compare symbol error with and
without compensation, and with an independent MATLAB-compatible calculation
executed in free GNU Octave.

On Ubuntu:

```sh
sudo apt-get install gnuradio octave python3-pytest python3-numpy
DESK_GNURADIO=1 /usr/bin/python3 -m pytest network_lab/tests/test_ofdm.py -q
/usr/bin/python3 -m network_lab.ofdm
```

This is a small 5G-style waveform experiment, not a 3GPP-compliant modem. There
is no RF transmitter, GNU Radio radio driver or satellite connection. The model
uses constant Doppler and integer sample delay; its values are controlled test
inputs rather than orbital predictions.

## Timed nodes and two encryption layers

`timed_tls.py` exchanges timed packets through an outer TLS socket and an inner
TLS session carried inside it. TLS encrypts traffic and verifies server identity.
The inner session uses MemoryBIO records; wrapping the same raw socket twice
would not create a real second encryption layer. Tests start two actual local
servers, verify both layers and measure round-trip times.

```sh
networking/deploy/certificates.sh
.venv/bin/python -m network_lab.timed_tls --cert networking/build/certs/server.crt --key networking/build/certs/server.key
```

The foreground node listens on loopback port 8443; Ctrl-C stops it. For a cloud
node I supply real certificate/key paths and choose the bind address explicitly.
`azure/main.bicep` defines two small Azure Linux nodes, a private network and an
inbound rule restricted to the caller's address on 443. CI compiles the template
without an Azure account. The included cloud-init installs the Python node code.
No Azure resource was deployed or billed. To deploy in an account, I provide an
SSH public key and caller CIDR, run `az deployment group create --resource-group
<group> --template-file network_lab/azure/main.bicep --parameters
sshPublicKey="$(cat ~/.ssh/id_ed25519.pub)" clientCidr='<public-ip>/32'`, then
install certificates using the Azure VM run-command facility and start the node
with `--host 0.0.0.0 --port 443`. I remove that resource group when finished.

I also experiment with quantising RTT samples into bits, discarding values near
a threshold. Hamming syndromes reconcile at most one mismatch per seven-bit
block, and an AES-GCM round trip checks that the resulting keys match. Tests
separate actual packet timing from synthetic paired timing samples used for
controlled bit-error injection. A stable local link may produce no useful bits.
RTT does not establish secret entropy, the helper data leaks information and
the experiment's final equality check is an oracle, not a deployable peer
agreement protocol. TLS supplies the actual transport security; I do not use
these timing bits as production encryption keys.
