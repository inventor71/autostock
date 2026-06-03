# Track F47 — 급등주 히스토리 기록 및 원인 분석 (Surge Stock History & Root-Cause Analysis)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F47
- **Title**: 급등주 히스토리 기록 및 원인 분석 (Surge Stock History & Root-Cause Analysis)
- **Type**: feature
- **Status**: merged → main 3eee516 (2026-06-03)
- **Branch**: feat/F47
- **Worktree**: .claude/worktrees/F47
- **Submodule branch**: — (monorepo)
- **Base commit**: 469fa51
- **Start Date**: 2026-06-03

## Project Information
- **Project Type**: Brownfield
- **Start Date**: 2026-06-03T00:00:00Z
- **Current Stage**: INCEPTION - Workflow Planning (완료) → Construction: Functional Design

## Workspace State
- **Existing Code**: Yes (Python 3.11+, src/ 기반 모듈러 모노리스)
- **Programming Languages**: Python, TypeScript (operator-console/)
- **Build System**: Hatchling / pyproject.toml
- **Project Structure**: Modular monolith (src/ layered packages: agent/, risk/, execution/, data/, core/, modes/)
- **Reverse Engineering Needed**: No (기존 프로젝트, 46개+ 트랙 완료, 코드베이스 충분히 이해됨)
- **Workspace Root**: /home/jihoonpark/Project/autostock
- **Previous Artifacts**: M1 트랙에서 reverse-engineering 수행됨; 공유 inception/ 디렉토리는 multi-track partition으로 migration 됨

## Code Location Rules
- **Application Code**: Workspace root (NEVER in aidlc-docs/)
- **Documentation**: aidlc-docs/ only
- **Structure patterns**: See code-generation.md Critical Rules

## Extension Configuration
| Extension | Enabled | Decided At |
|---|---|---|
| Security Baseline | No | Requirements Analysis (Q7-1=B, PoC/실험적 기능) |
| Property-Based Testing | Partial | Requirements Analysis (Q7-2=B, 순수 함수 + serialization round-trip만) |

## Scope
매일 유니버스 내 급등주를 자동 감지하여 히스토리를 기록하고, 급등 원인을 분석·분류한다.
현재 autostock의 데이터로 설명 불가능한 급등은 정보 갭(information gap)으로 기록하여,
추후 해당 정보를 수집할 수 있도록 개발 피드백을 제공한다.
장기적으로는 축적된 패턴 데이터를 기반으로 agent가 급등주를 예측하는 것을 목표로 한다.

## Stage Progress

### 🔵 INCEPTION PHASE
- [x] Workspace Detection — 완료 2026-06-03 (Brownfield, Reverse Engineering skip)
- [x] Reverse Engineering — SKIP
- [x] Requirements Analysis — Standard depth (질문 7+3개, 답변 완료, requirements.md 작성)
- [x] User Stories — SKIP (단일 operator 페르소나, FR로 충분)
- [x] Workflow Planning — 완료 2026-06-03 (execution-plan.md)
- [x] Application Design — SKIP (Functional Design에서 통합)
- [x] Units Generation — SKIP (단일 유닛)

### 🟢 CONSTRUCTION PHASE
- [x] Functional Design — 완료 2026-06-03 (domain-entities, business-logic-model, business-rules)
- [x] NFR Requirements — 완료 2026-06-03 (Minimal depth, 0 new deps)
- [x] NFR Design — 완료 2026-06-03 (Minimal depth, 6 patterns, 9 logical components)
- [x] Infrastructure Design — SKIP (local daemon, no infra)
- [x] Code Generation — 완료 2026-06-03 (Part 1+2, 680 tests green, 31 new surge tests)
- [x] Build & Test — 완료 2026-06-03 (680 passed, 0 regressions, merge-awaiting)

### 🟡 OPERATIONS PHASE
- [ ] Operations — PLACEHOLDER

## Construction Scope
- **Unit**: `surge-detection` (단일 유닛)
- **Deliverables**: `src/surge/` (records.py + detector.py + store.py), agent prompt 확장, settings.yaml `surge:` 블록
- **0 new runtime deps** 예상
