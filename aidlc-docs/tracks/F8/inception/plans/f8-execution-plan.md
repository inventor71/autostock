# F8 실행 계획 (Workflow Planning) — Console Sidebar status.py-rich Data & Color

- **트랙**: F8. **기반**: F4/F6 콘솔(merged main). **리스크**: Medium.
- **요구사항**: `aidlc-docs/inception/requirements/console-sidebar-status-rich.md` (APPROVED 2026-05-31).
- **빌드 베이스**: 새 worktree + 브랜치 off `main`(파이썬) / 서브모듈 `operator-console/cli`(TS, 현재 `7d26d49` heads/main).

## 1. 단계 결정 (Stage Determination)
| 단계 | 결정 | 근거 |
|---|---|---|
| User Stories | **SKIP** | 단일 운영자 도구, 워크플로는 FR-1~6로 포착(F2~F7 일관). |
| Application Design | **SKIP → Functional Design로 흡수** | 신규 컴포넌트 없음; 기존 `publish_snapshot`/`autostock.tsx` 확장. |
| Units Generation | **SKIP** | 단일 응집 유닛(`console-sidebar-status-rich`). |
| **Functional Design** | **EXECUTE (light)** | snapshot 스키마 확장(positions/open_orders/account/recent_fills) + 역할 매핑 + 사이드바 렌더(1줄압축/wrap/width-floor)을 코딩 전 못 박음. Python↔TS 계약이 걸려 있어 가치 큼. |
| NFR Requirements | **EXECUTE (minimal)** | 신규 런타임 의존성 0 확인. |
| NFR Design | **EXECUTE** | 가격 fetch 캐시/슬로우잡 배치, 케이던스 상수, width-floor 값, fail-closed 접합. (케이던스 기본값은 이미 확정.) |
| Infrastructure Design | **SKIP** | 로컬 데몬/TUI, 인프라 없음. |
| Code Generation | **EXECUTE** | Part1 계획 → Part2 빌드. |
| Build & Test | **EXECUTE** | Python 회귀 + bun 테스트 + 라이브 검증(R-항목). |

## 2. 단일 유닛: `console-sidebar-status-rich`
내부 빌드 순서(예비):
1. **(Python) 공유 유틸 추출**: status.py `_order_role`/`_pnl`/`_latest_prices` 로직을 데몬·콘솔 양쪽이 신뢰할 형태로 정리(중복 방지). 역할 매핑·가격 보충 헬퍼.
2. **(Python) `publish_snapshot` 확장**: `positions`에 `current_price/market_value/unrealized_pnl`; `open_orders`에 `side/order_type(역할 파생)/current_price`; `_account_block`에 `invested`. 전부 가산적(NFR-4).
3. **(Python) 신규 슬로우잡**: 미보유 주문심볼 현재가 캐시 fetch(~10–15s), `recent_fills` 발행(~45s, `get_fills` 재사용). 워커 직렬화·best-effort(NFR-2).
4. **(TS) 스키마 미러**: `operator-console/src/schema.ts`에 신규 필드 + 크로스랭귀지 contract 갱신(F4 Phase4 패턴).
5. **(TS) 사이드바 렌더**: `autostock.tsx` 보유/주문/최근체결/요약 확장 + green/red·▲▼ + 1줄압축·word-wrap·width-floor; 필드 부재 시 숨김(하위호환).
6. **테스트 + 라이브 검증**: Python PBT(평가손익%/Δ%/역할/recent_fills 정렬), bun 단위, 데몬 재시작 후 사이드바 라이브 확인.

## 3. 리스크 / 완화
- **Medium**: 라이브 주문/리스크 경로는 **불변**(콘솔 읽기전용 NFR-1, 데몬 발행만 확장). 가격 fetch 실패는 Δ 생략으로 그레이스풀.
- **F7 충돌 주의**: F7(copy/tips)도 콘솔을 건드림 — F8은 `autostock.tsx`(사이드바) 중심, F7은 `home.tsx`/`tips-view.tsx`(copy). 파일 겹침 적음. 머지 시 조율.
- **하위호환**: 머지 전 데몬은 구 스냅샷 → 콘솔은 신규 표시 안 함; **데몬 재시작 필요**(F6 GOTCHA 동일).
- 롤백: worktree/브랜치 격리 + 서브모듈 핀.

## 4. 익스텐션
- Security Baseline Enabled(SECURITY-03/15 적용, 대부분 N/A). PBT Partial(순수 계산 함수).

## 5. 진행 모델
- 설계 승인 후 Construction(코드+테스트)은 자율 진행(사용자 standing preference), 진짜 사람 판단 필요시(라이브 검증·머지·푸시 등 외부 영향)만 정지.
