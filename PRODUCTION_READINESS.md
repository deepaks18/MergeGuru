# MergeGuru Production Readiness

## Current Decision

The v3.1 source is a controlled internal deployment candidate. It is not yet an
enterprise-certified release. Automated checks show strong functional and
data-safety coverage, while organization-specific deployment, security, and
real-volume acceptance still require sign-off.

## Verified In The Current Source

- Canonical Lite workflow regression suite: 21 tests passed.
- High-risk integrity and recovery suite: 29 tests passed.
- Shared-engine integration check passed, including Excel output round-trip.
- Canonical health check and Python syntax compilation passed.
- Excel export preserves text identifiers and literal formula-like values,
  supports a Validation Report sheet, and commits atomically.
- Cancellation and writer-failure tests preserve an existing destination.
- Source-change checks reject detected changes after validation.
- Generated-data load suite passed all 9 stages, including a one-million-row CSV
  combine and a 50,000-row streamed Excel output round-trip.
- An isolated frozen QA candidate passed all 8 packaged self-test checks.
- The CI workflow repeats source checks, builds Windows packaging, and runs the
  frozen self-test with a bounded timeout.

Passing a local source suite does not prove that CI or a newly built executable
passed until those runs have completed. Record the workflow URL, binary hash,
signature status, and self-test report for each promoted build.

## Required Before Wider Rollout

- Run the actual representative 2 GB Excel/CSV workload on target laptop classes
  and record elapsed time, peak memory, output checks, and cancellation behavior.
- Test a clean managed Windows device without Python, including antivirus,
  SmartScreen, endpoint policy, network shares, and OneDrive-controlled folders.
- Complete user acceptance with nontechnical users at supported display scaling.
- Sign the executable with the organization's approved code-signing certificate
  and verify both Authenticode and SHA-256 after signing.
- Complete the firm's security, privacy, retention, and access-control review.
- Exercise locked, corrupt, password-protected, full-disk, and interrupted-power
  scenarios on representative storage.
- Define supported Windows versions, rollback owner, support route, and release
  approval record.

## Claims That Must Not Be Made

- Do not claim that a data breach is impossible.
- Do not present synthetic timings as a guaranteed speed advantage over Power
  Query, VBA, or another tool.
- Do not describe metadata source signatures as cryptographic verification.
- Do not call an unsigned, unapproved build enterprise certified.

## Promotion Evidence

For every production candidate, retain:

1. Source revision or archive identity.
2. CI result and test counts.
3. Packaged self-test report.
4. File version, size, SHA-256, and Authenticode status.
5. Representative workload acceptance results.
6. Business, IT, and security approval references.
