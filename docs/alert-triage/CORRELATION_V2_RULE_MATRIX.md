# Correlation-v2 Proposed Rule Matrix

| Signal family | Classification | Proposed role |
| --- | --- | --- |
| Same host + same user + same process/destination | VERY STRONG | Merge candidate when temporally continuous and no conflict. |
| Ordered behavior continuity on same host/account | VERY STRONG | Merge candidate; explains rotating-IP continuity. |
| Same host alone | CORROBORATING | Never sufficient with time alone. |
| Same user alone | CORROBORATING | Never sufficient; common accounts are expected. |
| Same process/domain/destination | STRONG | Requires host/account/sequence or another independent family. |
| Same public source/destination IP | CORROBORATING | Never attacker identity by itself; NAT/proxy risk. |
| Same category/severity/source MITRE | WEAK/UNTRUSTED | Context only; never a merge basis. |
| Alert title/description/source metadata | UNTRUSTED | Never score or discriminate. |

Candidate ledger: behavior continuity +5; shared account +3; shared host +2; shared process/destination/domain +3 each; close observed time +1. Penalties: different user -4, different process family -4, different destination/domain -3, independent rule family -3, incompatible stage -5. Hard veto applies for evidenced incompatible user/process/destination/stage combinations. Candidate merge requires net >=8, two positive independent families, and no hard veto.

### Cluster safety

Choose a stable representative (earliest observed alert then ID). A candidate must pass pairwise compatibility with representative and at least half of current members, including at least one behavior/identity-compatible member. A bridge alert that only connects two otherwise incompatible clusters must not merge them; retain the compatible side or create an ambiguity record. These are proposals, not implemented weights.
