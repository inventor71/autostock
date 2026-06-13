# F77 — Workflow Plan

**Track**: F77 · **Date**: 2026-06-13 · **Base**: requirements.md (승인 2026-06-13)

## 1. 영향 분석

| 영역 | 파일 (예상) | 변경 |
|---|---|---|
| 소스 | `src/signals/sources/stocktwits.py` (신규) | 무인증 스트림 fetch + 라벨 집계 (pydantic 검증) |
| 히스토리/베이스라인 | `src/signals/sentiment_store.py` (신규, 가칭) | JSONL append/읽기 + 베이스라인·z-score 순수 함수 |
| 설정 | `src/signals/settings.py`, `config/settings.yaml` | `signals.sentiment:` 블록 (시간 창, N일, K, 임계값, rate 예산) |
| 수집/브리프 | `src/signals/collector.py`, `brief.py` | 이상치 섹션 조립 (degraded_sources 연동) |
| 데몬 잡 | `src/trading/modes/agent.py` | 시간당 스윕 잡 등록 |
| 턴 공급 | `src/agent/orchestrator.py` | research/intraday 브리프 경로 (기존 F61 경로 재사용 — 변경 최소) |
| 테스트 | `tests/` | 단위 + PBT + 가짜 HTTP 주입 |

**위험도**: 낮음~중간 — 읽기 전용 외부 호출 + 부수 파일 + 브리프 텍스트. 주문/리스크 경로 무접촉.
데몬에 신규 주기 잡 1개 (예외 격리 필수 — NFR-1).
**동시 트랙**: F74(prompt eval)와 브리프/프롬프트 표면 인접 가능 — Merge Risk Notes에 기록됨.

## 2. 단계 결정

| 단계 | 실행 | 근거 |
|---|---|---|
| User Stories | SKIP | 단일 운영자, 수용기준 requirements §6 |
| Application Design | SKIP | F61 플러그인 경계 내 (신규 모듈 2개는 Functional Design에서 충분) |
| Units Generation | SKIP | 단일 유닛 "stocktwits-sentiment" |
| **Functional Design** | **EXECUTE** | 신규 데이터 스키마(레코드/파일 레이아웃), 베이스라인·이상치 수식, 브리프 형식, rate 예산 로직 |
| NFR Req/Design · Infra Design | SKIP | NFR은 requirements §4 확정, 인프라 변경 없음 |
| Code Generation | EXECUTE | worktree `feat/F77` |
| Build & Test | EXECUTE | 단위/PBT + 라이브 스모크(실제 1스윕) + post-merge guide |

## 3. 실행 순서

Requirements 승인 → **Functional Design (승인 게이트)** → Code Gen 계획 → worktree 생성 →
구현+테스트 → Build & Test(+post-merge guide) → merge-awaiting.
Functional Design 승인 후 Construction은 자율 진행.
