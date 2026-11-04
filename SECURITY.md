# Security policy

## Report a vulnerability privately

Use GitHub's [private vulnerability reporting](https://github.com/tail258/QuantSandbox/security/advisories/new) for this repository. The reporting feature is enabled; reports go to the repository's maintainers rather than the public issue list.

If GitHub private reporting becomes unavailable, open an issue asking the maintainer for a private reporting channel. Include only a general description such as “private security report”; keep exploit steps, vulnerable inputs, secrets, and personal data out of public issues and pull requests. This repository does not publish a separate security mailbox or a response-time guarantee.

A useful private report includes the affected version or commit, platform, minimal reproduction, expected trust boundary, observed impact, and a proposed fix if available. Prefer synthetic files and sanitized logs. Identify source URLs and relevant snapshot metadata without attaching personal research archives or an Obsidian vault.

## Deployment and data boundaries

QuantSandbox's provided launch scripts bind the application to the local machine. Treat it as a local research workbench; exposing its API to a network changes that boundary. Market access is read-only, and the application has no brokerage or live-order workflow.

Data imports, source URLs, downloaded documents, and evidence packages are untrusted inputs. Relevant reports include path traversal, unintended file access or overwrite, script execution, unsafe rendering, and exposure of local configuration or research data. Obsidian integration is optional and must preserve explicit, single-action writes and existing notes.

Keep credentials, local databases, exports, company profiles, research records, notes, original attachments, and `data/.local/obsidian.json` out of reports shared publicly. If a credential was exposed, revoke or rotate it before discussing the incident.

## Fixes and versions

Reproduce a suspected issue against the latest source when practical and include the affected release or commit. Security fixes are reviewed through the repository; no separate long-term-support or backport schedule is currently documented. A financial calculation discrepancy without a security impact belongs in a [bug report](https://github.com/tail258/QuantSandbox/issues/new?template=bug_report.yml), using a fixed synthetic snapshot where possible.
