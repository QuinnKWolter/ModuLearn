# Pitt catalog intermediate certificates

On 2026-10-05 `adapt2.sis.pitt.edu:443` sent only its leaf certificate.
Its issuer is `InCommon Intermediate CA - OVG2C`. Windows' cached
intermediates masked the missing chain; Mozilla's root-only store failed.

`pitt-intermediates.pem` contains **no self-signed root and no leaf certificate**:

| Certificate | SHA-256 fingerprint | Expires (UTC) |
| --- | --- | --- |
| InCommon Intermediate CA - OVG2C | `ba02f2f97ba481d19ed4906bab5602a9ce1cce5d1f362eb5ec4f9d828ef09ffc` | 2029-04-07 |
| emSign Root TLS CA - G1 (cross-signed by emSign Root CA - G1) | `9b913476eab476e21e0887dbcde44345d1359d28116b83b7cd3e87bd807ebf68` | 2039-07-09 |

Issuer repository sources:

- https://repository.emsign.com/certs/EEEMIncommonOVG2C.crt
- https://repository.emsign.com/certs/EMIncommonOVG2C.p7c

The first certificate was retrieved from a verified Windows TLS chain; the
cross-signed certificate was obtained from the issuer's HTTPS repository. The
complete chain was tested against the existing Mozilla roots with partial-chain
trust **disabled**, successfully anchoring at `emSign Root CA - G1`.

The catalog adapter adds these intermediates only for the fixed Pitt host and
requires an independently system-trusted root. Hostname, validity, and signature
verification remain enabled. No dynamic AIA fetching or insecure TLS fallback is
used. The upstream Apache operator should configure the full served chain; this
bundle can be removed after clean Linux clients verify the corrected server.
Renewal to another issuer may require refreshing these public intermediates.
