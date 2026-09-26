---
description: Select the next Backstage migration wave from live repository debt
agent: build
---

Plan exactly one bounded Backstage materialization wave from repository evidence.

1. Run:
   `python scripts/audit-service-catalog-v2-parity.py --check --debt-json`
2. Parse only the returned debt inventory; do not infer missing services from
   directory names.
3. Prefer declared criticality in this order:
   `critical -> high -> medium -> low -> unclassified`.
4. If the highest remaining candidates are `unclassified`, do **not** invent
   business criticality, RTO, RPO, MTPD/DMTP or impact values. Switch to a
   classification-first task:
   - group candidates by `sourcePath`;
   - inspect one coherent app/runtime group;
   - identify actual runtime dependencies and statefulness;
   - record the BIA/criticality questions that need evidence;
   - materialize only entities whose classification can be justified from
     existing repository evidence.
5. Load `nabla-service-catalog` and, when Compose changes are required,
   `docker-compose-orchestration`.
6. Keep `x-nabla` compatibility until the coordinated v2 cutover.
7. Run the catalog parity audit and the narrowest related tests before
   `mise run agent-fix`.
8. Never update hard-coded debt counts without reconciling them against
   `--debt-json`.
