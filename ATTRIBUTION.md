# Attribution

X-Ray is original Hack Hydra work. The following open-source projects informed
**presentation patterns** (verdict labels, demo beat sheets, honesty badges).
Unless noted, we reimplemented ideas rather than copying source files.

| Project | License | What we reused |
|---|---|---|
| [danielAsaboro/sourcetruce](https://github.com/danielAsaboro/sourcetruce) | MIT | Verdict enum `SUPPORTED` / `DISPUTED` / `NOT_FOUND` / `UNKNOWN` and decide-order inspiration (`packages/xray_analytics/.../verdicts.py`) |
| [rohan911438/Hydra-Ontology](https://github.com/rohan911438/Hydra-Ontology) | MIT | Timed demo / voiceover document structure (`docs/DEMO_SCRIPT.md`, `docs/VOICEOVER_SCRIPT.md`) |
| [yashksaini-coder/Reachable](https://github.com/yashksaini-coder/Reachable) | MIT | Collapsible Cypher proof panel pattern on risk detail |
| [FalkorDB/RepoGraph](https://github.com/FalkorDB/RepoGraph) | MIT | Bus-factor / silo *product language* only (no code port) |
| [KenGraph/checkOwners](https://github.com/KenGraph/checkOwners) | MIT | Ownership-confidence framing (already present in X-Ray OWNS) |
| [iamdflame/cordon](https://github.com/iamdflame/cordon) | Apache-2.0 | Judge “90-second path” / honest results framing |

**Not copied:** HydraDB AGPL engine source; HydraSentry (unclear license) —
only the REAL vs Snapshot *honesty* product pattern.

Datasets, HydraDB, MinIO, and other dependencies: see [NOTICE.md](NOTICE.md).
