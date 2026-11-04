# Changelog

This file records user-visible changes. Source releases identify the exact commit and dependency locks; the calculation engine and evidence format have separate compatibility versions.

## 3.2.0 — 2026-11-05

### Added

- English-default interface with live English/Chinese switching and a browser-local language preference.
- Optional Financial terminal theme alongside the original Classic light theme. Appearance changes include tables, charts, dialogs, inspectors and note previews.
- Offline synthetic baseline → evidence export → independent import/replay example with fixed reference hashes and overwrite protection.
- Deterministic, source-only release archives, dependency/commit manifest, SHA256 checksums and a gated tag-release workflow.
- Contribution and security policies, structured bug/feature forms, a pull-request template and private vulnerability reporting.
- English-default README with a Chinese entry point, a branded SVG header, feature cards and verified setup/reproduction instructions.

### Fixed

- Language/theme switches preserve selected projects, records, drafts and note previews. Original user/source content and data labels remain unchanged.
- Financial pages handle partial metric catalogs and absent template focus without failing to render.
- Standalone SVG downloads retain the theme colors needed to read the chart outside the workbench.
- Product version metadata agrees across Python, the backend, workspace/frontend npm manifests and lockfiles. Architecture/design/roadmap documents describe the current React implementation.

### Retained

- Project-centered research, persistent conclusions, fixed-snapshot bridges, strategy experiments, blind replay and optional note export.
- Suspension and explicit price-limit fields throughout normalization, snapshots, hashing and evidence replay; compatibility for older OHLCV-only hashes.
- Read-only market access, explicit fetching, missing-data semantics and local-only research storage. This release does not change financial formulas, trading signals or account assumptions.

Earlier development history is available in the [commit log](https://github.com/tail258/QuantSandbox/commits/main/).
