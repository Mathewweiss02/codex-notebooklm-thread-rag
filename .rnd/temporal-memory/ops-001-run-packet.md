# OPS-001 Run Packet: Doctor and operator UX gate

## Objective

Verify that the everyday operator surface reports fresh runner state, correct
conversation policy, valid paths, source readiness, scheduler health, passive
auth truth, reconciliation, and console-free execution without exposing
credentials or answer content.

## Checks

- Run the repository suite and PowerShell doctor integration.
- Run `thread_rag_doctor.ps1` for both configured roles with `-Live`.
- Verify the scheduled action uses the hidden Python launcher rather than a
  visible PowerShell window.
- Inspect current Node process memory only as a diagnostic; do not kill an
  unverified process.
