# DDFC — TLA+ machine-checkable specification

This directory holds the TLA+ formalization of the Direct Data Flow
Controller (DDFC) token-exchange protocol described in the A-VIP paper
(Section "DDFC — Direct Data Flow Controller", paragraph
"Protocol specification").

## Files

- `DDFC.tla` — the protocol specification: four-message exchange
  M1–M4, attacker actions (relay, replay), and the four invariants
  I1–I4 plus the structural-resistance theorem.
- `DDFC.cfg` — TLC model-checker configuration with the bounded
  parameter values from the paper's Section "DDFC — Marketplace and
  multi-merchant scope".

## Running TLC

```bash
# Java 11+ and TLA+ Toolbox / community modules installed.
tlc -config DDFC.cfg DDFC.tla
```

With the released configuration the state space is finite and TLC
verifies all five invariants in under a minute on a laptop. The
configuration intentionally includes an attacker merchant
(`M_attacker`) and three users to exercise both relay (I2) and
replay (I4) attempts.

## What the spec proves

- **I1 (No identifier disclosure)** — `uid` never appears in the
  agent's reachable context or in any token field. The Vault
  Whisper's argument-space attack surface is structurally removed.
- **I2 (Audience binding)** — every accepted redemption is by the
  audience the token names. Cross-merchant relay fails at the
  Credentials Provider.
- **I3 (Cart-mandate binding)** — every accepted redemption
  presents the same cart hash the token was issued for.
  Confused-deputy cart swaps fail at the Credentials Provider.
- **I4 (Single-use + TTL)** — replayed tokens fail atomically;
  expired tokens fail unconditionally.
- **VaultWhisperResistance** — composition of I1–I4: no
  reachable trace exposes any uid to the agent or to any
  merchant, regardless of attacker-controlled merchant text.

## Scope and limitations

This is a *protocol-level* specification. It abstracts away from
cryptographic signature verification (modelled as token integrity
held by construction) and from the AP2 mandate-signing pipeline
(treated as an external sequencing constraint). A machine-checked
cryptographic proof of the JWT/COSE signature primitive is out of
scope and would be performed in Tamarin or ProVerif on the
underlying primitive, not on the DDFC protocol layer.

The TLA+ specification is bundled with the paper artifact and is
the machine-readable form of the invariants stated informally in
the paper (Theorem "Vault-Whisper structural resistance").
