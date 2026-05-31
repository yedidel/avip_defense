# Acceptable Use Clause — Attack Harness

The contents of this `attacks/` subdirectory implement attack payloads
used to evaluate the A-VIP defense.

## Acceptable use

This code is provided for:
- Security research
- Evaluation of A-VIP and other defenses against AP2 whisper attacks
- Academic study and reproducibility of the IEEE S&P 2027 paper

## Prohibited use

This code MUST NOT be used to:
- Attack production AP2 deployments without the operator's explicit
  written authorization
- Exfiltrate real users' payment-method aliases
- Submit cryptographically valid Cart Mandates that misroute payment
- Target individuals or specific deployments outside an authorized
  evaluation scope

## Coordinated disclosure

The attack class encoded here has been disclosed to Google's
Vulnerability Reward Program (VRP) and to the FIDO Alliance Agentic
Working Group leadership prior to publication. The 90-day standard
disclosure window has been observed.

## Defense colocation

The attack harness assumes the A-VIP defense (`avip/`, `sv/`) is also
present in the same checkout. Running the harness in isolation against
an unprotected AP2 deployment is not a supported configuration.
