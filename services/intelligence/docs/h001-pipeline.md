# H001 preparation pipeline map

Gate 2 `DATA READY` is **withdrawn**. This map is Scope A preparation only.

```text
snapshots 2/nifty50/1D/manifest.json  (49 names, TATAMOTORS excluded)
        |
        v
datasets/h001-nse-raw-20261010T140237Z/
  corporate-announcements/*.raw   (392 slices)
  corporate-announcements/*.json  (49 concatenations)
  financial-results/*.raw         (auxiliary; not merged)
  retrieval.json, audit_stats.json
        |
        |  integrity-audit-v2 (sizes + class + SHA-256)
        v
Scope A records: symbol, seq_id, desc, exchdisstime_raw,
available_at = parse(exchdisstime) tagged Asia/Kolkata (convention)
        |
        +-- section15 classifier (hasXbrl OR desc regex)
        +-- v1 three-desc class (immutable)
        v
docs: hashes, coverage, missingness, DATA_PREP_READY gate
```

Not in this pipeline: holdout, labels, train, live RSS, BSE DissemDT, ProwessDx.

Command (repo root):

```text
set PYTHONPATH=packages/contracts/src;services/intelligence/src
python -m intelligence_agents.h001v2.scan
python -m pytest services/intelligence/tests/test_h001v2_normalize.py services/intelligence/tests/test_h001_prep.py -q
```
