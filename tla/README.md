# DDFC — TLA+ machine-checkable specification

This directory holds the TLA+ formalization of the Direct Data Flow
Controller (DDFC) token-exchange protocol described in the A-VIP paper
(Section "DDFC — Direct Data Flow Controller", paragraph
"Protocol specification").
It also holds `DecisionBinding.tla`, a bounded model of decision-basis
binding (see the section "DecisionBinding" below).

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

## DecisionBinding — bounded model of decision-basis binding

`DecisionBinding.tla` models one AP2 human-present purchase: the merchant's
search response, the agent's choice, the checkout response, an optional
re-choice, and signing. The agent is worst case: any subset of the statements
in its context may influence its choice. Every possible statement (any offer
speaking about any title) is in the merchant text. The mechanism it models is
the one in `../binding/` (capture wrapper W, attributor A, authority rule,
STRIP / ANNOTATE).

Property `BasisBound` (stated without reference to the mechanism): if an offer
is signed, every statement that influenced the choice was either received
together with its speaker (annotated) or spoken by a seller responsible for
every offer the statement is about. `ViolationIsMiss`: with an imperfect
attributor, every violation involves a statement the attributor missed.

Bounded universe: sellers A, B; offers o1 (A, t1), o2 (B, t2), o3 (A, t2; A's
copy of B's title); 6 statements. Results hold for this bound only.

### Files

- `DecisionBinding.tla` — the specification; the constants select the
  configuration (`WrapSearch`, `WrapCheckout`, `Policy`, `Expansion`, `PerfectA`).
- `C1_baseline.cfg` … `C6_full_annotate.cfg` — the seven configurations below.
- `logs/tlc_<config>.log` — the TLC output of the released runs (absolute local
  paths replaced by `<repo>` and `<tmp>`; the first line is the build stamp of
  the tools jar).

### Running TLC

TLA+ tools from the v1.8.0 release channel, TLC2 build 2026.10.28.014557 (rev 56d37a9) (`tla2tools.jar`, SHA-256
`fc6878c603f0fdc18b9fe3e5bf51860cb90ab5b1154e3c371660c036d6bdd63e`), Java 11+.
The jar is not redistributed here; download it from the TLA+ tools releases
(<https://github.com/tlaplus/tlaplus/releases>) and check its digest.

```bash
java -cp tla2tools.jar tlc2.TLC -config C3_full_strip.cfg -workers 4 DecisionBinding.tla
```

Each configuration finishes in seconds. With several workers, TLC stops at the
first violation it finds, so the state counts of the violated runs vary
between runs; the verdicts and the counts of the completed runs do not.

### Results

| config | W on search | W on checkout | policy | expansion | attributor | invariant | TLC result | distinct states |
|--|--|--|--|--|--|--|--|--|
| C1 baseline (AP2 v0.2.0) | no | no | none | - | - | BasisBound | violated | (stops at first) |
| C2 W on search only | yes | no | STRIP | yes | perfect | BasisBound | violated: the agent picks o2, the checkout response repeats o2's statement about t1, the agent re-selects o1 | (stops at first) |
| C3 full W + STRIP | yes | yes | STRIP | yes | perfect | BasisBound | holds | 50 |
| C4 no target expansion | yes | yes | STRIP | no | perfect | BasisBound | violated: o1 (A) speaks about t2; the resolver maps it to A's own copy o3, so it counts as authoritative and is kept, but it is also about B's o2 | (stops at first) |
| C5 imperfect attributor | yes | yes | STRIP | yes | misses any subset | ViolationIsMiss | holds: every violation involves a missed statement | 15,680 |
| C5b imperfect attributor | yes | yes | STRIP | yes | misses any subset | BasisBound | violated (as expected) | (stops at first) |
| C6 full W + ANNOTATE | yes | yes | ANNOTATE | yes | perfect | BasisBound | holds | 770 |

What the model does and does not say:

- The property holds by construction when W covers both channels, the policy
  is applied, targets are expanded over equal titles, and the attributor is
  perfect (C3, C6). That is not an empirical result; the measurements in
  `../binding/` test the assumptions: the channels W must cover (F1), the
  attributor (F2, F6) and offer identity (F3).
- Each assumption is necessary in this bound: dropping the checkout channel
  (C2), target expansion (C4) or attributor completeness (C5b) each gives a
  counterexample, and with an imperfect attributor the only violations are
  missed attributions (C5).
- The model says nothing about statements a seller makes about its own offer
  (authoritative by the rule); the residual measurement F5 (SELF arm) measures
  that.
