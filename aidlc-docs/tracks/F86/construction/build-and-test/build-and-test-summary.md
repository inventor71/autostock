# F86 — Build & Test Summary

> 단일 유닛(dashboard-endpoint). TS console 트랙(worktree `feat/F86`). 모든 게이트 그린.

## Build / Typecheck
```bash
cd .claude/worktrees/F86/operator-console/cli
(cd packages/opencode && PATH=~/.bun/bin:$PATH bun run typecheck)   # → clean
(cd packages/app      && PATH=~/.bun/bin:$PATH bun run typecheck)   # → clean
```
- 신규 devDependency: `fast-check@4.6.0` (opencode 패키지; app은 F79가 이미 보유). `bun install` 반영, `bun.lock` 갱신.

## Unit + Property tests
```bash
# 서버 코어 (C1/C2/C3): example + PBT(P1 never-throw / P2 보존 / P3 부호 / P5 resolver)
(cd packages/opencode && PATH=~/.bun/bin:$PATH bun test test/autostock-dashboard.test.ts)   # 13 pass

# 클라 매퍼 (C4 helpers): example + PBT(P2 보존 / P4 staleness fail-safe / P6 round-trip)
(cd packages/app && PATH=~/.bun/bin:$PATH bun test --preload ./happydom.ts src/addons/autostock)   # 52 pass (F79 41 + F86 11)

# 회귀 (F79/F75 보안 코어 무영향)
(cd packages/opencode && PATH=~/.bun/bin:$PATH bun test test/autostock-webauthn.test.ts)   # pass
```
- **PBT(PBT-08)**: fast-check 기본 shrinking/seed. P1이 실제 버그(미정규화 pending/position_count) 발견 → 수정 후 그린. 발견 반례는 example 회귀로 고정(PBT-10).

## Integration / 통합 (서버 라우트 ↔ 실 데이터)
- **real-data 스모크(핵심)**: 데몬이 발행 중인 실 `steering/{snapshot,health,monitor}.json`을
  `assembleDashboardPayload`에 투입 → account(equity=$99,624 / cash / open_pnl / position_count=1),
  positions(RTX return_pct=+4.37% long), agent.recent(20건, action/symbol/ts), market({open:false}),
  published_at(파싱가능) 정상 산출. **이 스모크가 실 `health.json`의 `overall` 스키마 불일치 버그를 잡음**
  (fakes로는 불가). → post-merge-guide의 실기기 라이브 스모크로 라우트 end-to-end 확인.
- **라이브 HTTP 라운드트립**: serve 미기동 상태라 미실행 → post-merge-guide 체크리스트(사용자 1회).

## Security 적합성 (Security Baseline — enforced)
| Rule | 결과 |
|---|---|
| SECURITY-08 (접근제어) | ✅ fork 라우트는 HttpApi auth 우회 → `checkBasicAuth` 자체 적용(webauthn과 동일). 비인증 → 401 |
| SECURITY-05 (입력검증/path) | ✅ 고정 파일명만 read, 요청 입력 경로결합 없음(traversal 불가). GET only(else 405) |
| SECURITY-15 (fail-safe) | ✅ 전 파일 I/O try/catch + 전역 try/catch → 부분/빈 200(거짓 신선 없음, published_at=null→stale). 5xx로 셸 안 깨짐 |
| SECURITY-09 (에러노출) | ✅ 응답에 스택/내부경로 없음. health 블롭 축약(detail 미노출) |
| SECURITY-13 (역직렬화) | ✅ 신뢰 호스트 파일이나 파싱실패 안전 흡수, allowlist 필드만 추출 |
| SECURITY-03 (로깅) | ✅ 민감값 로그 미기록(기존 serve 로깅 활용) |
| 그 외(01/02/06/07/10/11/12/14) | N/A — 신규 인프라/IAM/네트워크/인증서버/공급망 없음(인증=F71/F75 재사용), 신규 비밀키 없음 |

## PBT 적합성 (full — enforced)
- PBT-01(속성식별 문서화) ✅ / PBT-02·03(round-trip·invariant) ✅ P1/P2/P6 / PBT-03(부호 invariant) ✅ P3 /
  PBT-07(도메인 생성기) ✅ / PBT-08(shrink·seed·CI) ✅ / PBT-09(fast-check) ✅ / PBT-10(example 병행) ✅.
  PBT-04(idempotency)·05(oracle)·06(stateful) = N/A(해당 로직 없음).

## 결과
**All green** — typecheck/unit/PBT/회귀/real-data 스모크 통과. 머지 후 실기기 라이브 스모크만 사용자 1회(post-merge-guide).
