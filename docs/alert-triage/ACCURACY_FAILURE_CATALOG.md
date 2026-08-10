# Accuracy Failure Catalog

## Phase 7.7.3 measured correlation results

| Scenario | V1 result | V2 result | Status |
| --- | --- | --- | --- |
| Same host, different user | 1 false merge | Separate | V2 corrected |
| Same host, different process | 1 false merge | Separate | V2 corrected |
| Same host, unrelated rule | 1 false merge | Separate | V2 corrected |
| Parallel incidents on same host | 1 false merge | Separate | V2 corrected |
| Bridge ABC | 2 false merges | A/B correlate; C separate | V2 corrected |
| Rotating IP with same identity/behavior | Correlated | Correlated | Preserved |
| Shared NAT gateway | Separate | Separate | Preserved |
| Common service account | Separate | Separate | Preserved |
| Noisy interleaving | Correct grouping | Correct grouping | Preserved |
| Delayed continuation | Separate | Separate | Preserved |
| Multi-source telemetry | Correlated | Correlated | Preserved |
| Cross-org lookalikes | Separate | Separate | Preserved |

The executable shared matrix measured v1 at precision 0.4000, recall 1.0000, F1 0.5714, 6 false merges, and 0 missed correlations. V2 measured precision 1.0000, recall 1.0000, F1 1.0000, 0 false merges, and 0 missed correlations.

Version isolation is verified by processing the same canonical alerts under both correlation versions and reading memberships with the matching version only. No ground-truth incident label is present in a production `CanonicalAlert` field or metadata.
