#!/bin/sh
# Disposable local demo CA. Private keys never leave the generated build folder.
set -eu
out=${1:-networking/build/certs}
mkdir -p "$out"
umask 077
cat > "$out/ca.cnf" <<'CONFIG'
[req]
distinguished_name=dn
x509_extensions=ca_ext
[dn]
[ca_ext]
basicConstraints=critical,CA:TRUE
keyUsage=critical,keyCertSign,cRLSign
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always
CONFIG
openssl req -config "$out/ca.cnf" -x509 -newkey rsa:2048 -nodes -days 2 -subj /CN=desk-demo-ca -keyout "$out/ca.key" -out "$out/ca.crt" 2>/dev/null
openssl req -newkey rsa:2048 -nodes -subj /CN=localhost -keyout "$out/server.key" -out "$out/server.csr" 2>/dev/null
printf 'subjectAltName=DNS:localhost,DNS:broker,IP:127.0.0.1\nextendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n' > "$out/extensions"
openssl x509 -req -days 2 -in "$out/server.csr" -CA "$out/ca.crt" -CAkey "$out/ca.key" -CAcreateserial -extfile "$out/extensions" -out "$out/server.crt" 2>/dev/null
# Mosquitto's container user must read the demo server key. Directory stays local.
chmod 644 "$out/server.key" "$out/server.crt" "$out/ca.crt"
