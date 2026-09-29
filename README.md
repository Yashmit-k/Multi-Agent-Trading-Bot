# Multi-agent trading

Shared contracts live in [`packages/contracts`](packages/contracts). That package is the only source of truth for schemas, event names, Redis channels, horizons, trading modes, and agent interfaces.

Install it from the repo root:

```bash
python3 -m pip install -e "packages/contracts[dev]"
```

Contract changes ship as a pull request to `packages/contracts` with a semantic version bump. Other services import this package and do not redefine its models or vocabulary.
