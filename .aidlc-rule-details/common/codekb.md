# CodeKB — Shared Codebase Knowledge Base

## Why this rule exists

Every track that starts on a brownfield project needs to understand the codebase. Without a shared knowledge layer, each track re-discovers the same things — architecture, domain entities, integration points, business rules — from scratch. CodeKB is the **single, always-current cache** of that knowledge.

CodeKB answers "what does this codebase look like right now?" for any track starting work. A track reads CodeKB, gets 80% instant orientation, and only needs per-track RE for the areas it's actually changing.

## Core rule: CI owns CodeKB

> **CodeKB has exactly one writer — CI.** No track writes to it. The merge orchestrator doesn't touch it.

- **CI** re-runs full RE on every push to `main` and overwrites `aidlc-docs/codekb/` entirely. No incremental patching, no staleness ambiguity.
- **Bootstrap exception**: The first track on a fresh repo (CodeKB absent) populates CodeKB during inception RE. This is a one-time seed — after the first merge, CI takes over.
- **All tracks**: Read-only consumers. Load CodeKB during inception as baseline context.

## File layout

```
aidlc-docs/codekb/
├── summary.md              # One-page codebase summary
├── architecture.md         # System architecture and patterns
├── integration-map.md      # External integrations
├── domain-entities.md      # Key domain models
├── business-rules.md       # Business logic and rules
├── nfr-design.md           # NFR design decisions
├── infrastructure-design.md # Deployment architecture
└── codekb-state.md         # Metadata: last SHA, timestamp, schema version
```

## Schema

### summary.md

High-level codebase summary — one page. Business domain, primary language/framework, architecture style, key components at a glance. Targeted at giving a new track instant orientation.

```markdown
# Codebase Summary

## Business Domain
[What business problem this codebase solves. One paragraph.]

## Technical Overview
- **Primary Language**: [language + version]
- **Framework**: [framework + version]
- **Architecture Style**: [monolith / microservices / serverless / etc.]
- **Build System**: [Maven / Gradle / npm / etc.]

## Key Components
| Component | Type | Purpose |
|---|---|---|
| [name] | [app / infra / shared / test] | [one-line purpose] |

## Current State
- **Total Packages**: [N]
- **Total Source Files**: [N]
- **Last Significant Change**: [description]
```

### architecture.md

System architecture and patterns. Component-level descriptions with relationships, data flow for key workflows.

```markdown
# System Architecture

## Architecture Diagram
[Mermaid diagram showing all packages/services/data stores and their relationships]

## Component Descriptions
### [Component Name]
- **Purpose**: [What it does]
- **Responsibilities**: [Key responsibilities]
- **Dependencies**: [What it depends on]
- **Type**: [Application / Infrastructure / Model / Client / Test]

## Data Flow
[Mermaid sequence diagram of key workflows]

## Design Patterns
### [Pattern Name]
- **Location**: [Where used]
- **Purpose**: [Why used]
```

### integration-map.md

External API integrations, databases, third-party services, message queues, file systems.

```markdown
# Integration Map

## External APIs
| API | Purpose | Connection | Auth | Criticality |
|---|---|---|---|---|
| [name] | [purpose] | [REST/GraphQL/gRPC] | [method] | [high/medium/low] |

## Databases & Data Stores
| Store | Type | Purpose | Access Pattern |
|---|---|---|---|
| [name] | [DynamoDB/RDS/S3/etc.] | [purpose] | [read/write/read-write] |

## Message Queues & Events
| Queue/Topic | Type | Producer | Consumer | Purpose |
|---|---|---|---|---|
| [name] | [SQS/SNS/Kafka/etc.] | [component] | [component] | [purpose] |
```

### domain-entities.md

Key domain models and business entities.

```markdown
# Domain Entities

## Entity Catalog
### [Entity Name]
- **Purpose**: [What it represents in the business domain]
- **Key Fields**: [field: type — purpose]
- **Relationships**: [related entity → relationship type]
- **Defined In**: [file paths]
- **Lifecycle**: [how it's created, modified, deleted]
```

### business-rules.md

Business logic rules discovered in the codebase.

```markdown
# Business Rules

## Rules by Domain

### [Domain Area]
#### [Rule Name]
- **Rule**: [What it enforces]
- **Rationale**: [Why this rule exists]
- **Implemented In**: [file paths / functions]
- **Invariants**: [What must always be true]
```

### nfr-design.md

Non-functional requirements and their design decisions visible in the codebase.

```markdown
# NFR Design

## Resilience
| Pattern | Implementation | Location |
|---|---|---|
| [retry / circuit-breaker / timeout / fallback] | [how it's done] | [file paths] |

## Scalability
| Pattern | Implementation | Location |
|---|---|---|
| [caching / sharding / async] | [how it's done] | [file paths] |

## Security
| Pattern | Implementation | Location |
|---|---|---|
| [auth / encryption / input-validation] | [how it's done] | [file paths] |

## Observability
| Pattern | Implementation | Location |
|---|---|---|
| [logging / metrics / tracing] | [how it's done] | [file paths] |
```

### infrastructure-design.md

Deployment architecture and infrastructure.

```markdown
# Infrastructure Design

## Deployment Model
- **Platform**: [AWS / GCP / Azure / on-prem]
- **Orchestration**: [CDK / Terraform / CloudFormation / manual]

## Stacks & Resources
### [Stack Name]
- **Purpose**: [What infrastructure it provisions]
- **Key Resources**: [list of key resources]
- **Defined In**: [file paths]

## Environment Topology
| Environment | Account/Region | Purpose |
|---|---|---|
| [dev/staging/prod] | [details] | [purpose] |

## CI/CD
- **Pipeline**: [GitHub Actions / Jenkins / etc.]
- **Config Location**: [file paths]
```

### codekb-state.md

Metadata about the CodeKB itself. Updated by CI on every refresh.

```markdown
# CodeKB State

- **Last Commit SHA**: `<sha>` (the `main` HEAD this CodeKB reflects)
- **Last Refresh**: `<ISO 8601 timestamp>`
- **Refreshed By**: `ci` | `track/<id>` (bootstrap only)
- **Schema Version**: `1`
```

## Staleness detection

Any track can check CodeKB freshness by comparing the SHA:

```
codekb_sha=$(grep 'Last Commit SHA' aidlc-docs/codekb/codekb-state.md | cut -d'`' -f2)
current_sha=$(git rev-parse HEAD)
if [ "$codekb_sha" = "$current_sha" ]; then
  echo "CodeKB is current"
else
  echo "CodeKB is stale — was generated from $codekb_sha, HEAD is $current_sha"
fi
```

- **SHA match** → CodeKB is current. Full trust.
- **SHA mismatch** → CodeKB is stale (another track merged since last CI refresh). Still usable as approximate context; per-track RE should verify the areas the track touches.
- **CI pipeline**: typically completes within seconds of a `main` push, so the staleness window is small.

## Bootstrap procedure (first track only)

When a track's inception RE phase finds no CodeKB (`aidlc-docs/codekb/codekb-state.md` absent):

1. Run full RE as usual, writing per-track artifacts to `aidlc-docs/tracks/<id>/inception/reverse-engineering/`.
2. After RE is approved (Step 13 in reverse-engineering.md), synthesize the per-track RE findings into CodeKB files under `aidlc-docs/codekb/`.
3. Write `codekb-state.md` with the current `HEAD` SHA, timestamp, `track/<id>` as the refresher.
4. Commit CodeKB files to the track's branch — they land on `main` when this track merges.
5. Record in track's `state.md`:
   ```markdown
   ## CodeKB Bootstrap
   - [x] CodeKB bootstrapped by this track
   - **Bootstrap SHA**: `<sha>`
   - **Bootstrap Date**: `<ISO 8601>`
   ```

After this track merges and CI fires for the first time, CI overwrites CodeKB with a fresh RE and becomes the sole writer from that point on.

## CI refresh procedure

Triggered on every push to `main` (see `.github/workflows/codekb-refresh.yml`):

1. Check out the repo at the new `main` HEAD.
2. Run the full 13-step Reverse Engineering process (same as `reverse-engineering.md`), but write outputs to `aidlc-docs/codekb/` instead of a per-track directory.
3. Update `codekb-state.md`:
   - `Last Commit SHA` → current `HEAD`
   - `Last Refresh` → now
   - `Refreshed By` → `ci`
4. Commit and push back to `main` with message: `docs: codekb refresh (<short-sha>)`

If CodeKB doesn't exist yet (somehow CI triggered before bootstrap), CI bootstraps it — same as the track bootstrap procedure, but marked `Refreshed By: ci`.

## Quick checklist

- [ ] Starting a track? Check CodeKB SHA against `HEAD`. Load if current.
- [ ] Running inception RE? Check if CodeKB exists. If not, bootstrap it.
- [ ] About to edit CodeKB from a track? → **Don't.** Only CI writes it.
- [ ] Just merged? → CI handles the refresh. Nothing to do.
