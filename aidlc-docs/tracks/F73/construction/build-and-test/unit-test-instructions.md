# Unit Test Instructions — F73 viz-shell

## 실행
```bash
cd viz-shell
npm test            # vitest run (10 files, 108 tests)
npm run test:watch  # 워치 모드
```

## 커버리지 (10 파일 / 108 테스트, 전부 green)

### 서버 계층
| 파일 | 검증 |
|---|---|
| `tests/server/boundary.test.ts` | **경계 거부 전수** (blocking 게이트) — write→generated/만, read→viz-shell/만, `../`·절대경로·심링크(파일/디렉토리) 탈출 deny, 비편집 도구 deny-by-default, **Glob `..` 패턴 deny**(code-review 추가), 절대 Glob 정적 프리픽스, deny 이벤트 페이로드 |
| `tests/server/safe-read.test.ts` | readJsonFile(ENOENT/invalid/스키마 drift), tailJsonl(torn-line/skip/maxLines) + **PBT** 임의 바이트 절단 무crash, readFileStable(멀티바이트/ENOENT) |
| `tests/server/schemas.test.ts` | 실데이터 형상(E1 account 중첩/positions dict, E2) + passthrough(BR-9) + **PBT** 직렬화 라운드트립 |
| `tests/server/portfolio-router.test.ts` | **mutation 0 구조 검증**(BR-6), sinceDays 경계, symbol 이중 화이트리스트 거부, fail-honest 부재 처리 |
| `tests/server/sanitize-env.test.ts` | 실 .env 키 전수 strip + **거래 크리덴셜 패밀리 프리픽스**(code-review 추가) + OAuth 보존 + undefined drop |
| `tests/server/session-store.test.ts` | 영속/리셋/부재/손상 파일 fail-honest |
| `tests/server/chat-reset.test.ts` | **reset in-flight 409 가드**(code-review 추가) + 단일 in-flight 락 |

### UI 계층 (jsdom)
| 파일 | 검증 |
|---|---|
| `tests/ui/view-utils.test.ts` | 파일명→타이틀, `_` 접두 제외, 숨김/복원, localStorage 라운드트립/손상 내성 |
| `tests/ui/format.test.ts` | fail-honest `—`, 부호/색상 토큰 |
| `tests/ui/error-boundary.test.tsx` | 깨진 뷰 탭 단위 격리 + 복구 안내 렌더 |

## 성공 기준
- `Test Files 10 passed`, `Tests 108 passed`
- 경계 거부 테스트(보안 성공 기준 ③) 전건 green — **blocking**
