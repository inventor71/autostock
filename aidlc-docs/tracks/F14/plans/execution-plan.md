# F14 실행 계획 (Workflow Planning)

> Requirements 확정(§5/§6/§7) 기반. 복잡도 **Medium**, 위험 **Medium**(라이브 데몬 신뢰성 경로를
> 건드리나 모두 방어적·자가복구 방향이고 worktree 격리로 롤백 쉬움). 사용자는 아래 단계 구성을
> 자유롭게 가감할 수 있다(override 가능).

## 1. 단계 결정 (어떤 stage를 돌릴지)

| Stage | 결정 | 근거 |
|-------|------|------|
| User Stories | **SKIP** | 내부 신뢰성 수정 + 운영자 1인 self-heal. 사용자 워크플로 변화 없음, FR-A/B/C로 충분 (F1~F3 선례와 일관). |
| Workflow Planning | **실행(현재)** | 항상. |
| Application Design | **SKIP → Functional Design에 흡수** | 신규 독립 컴포넌트는 prefetch 워커 1개뿐, 나머지는 기존 컴포넌트(DaemonService/BarCache/AlpacaBroker) 수정. 컴포넌트 경계가 작아 Functional Design에서 함께 다룸. |
| Units Generation | **SKIP** | 단일 트랙. 아래처럼 **2개 작업 단위(레이어 경계)**로 나눠 순차 진행하되 별도 Units 문서는 불필요. |
| Functional Design | **실행(Medium)** | B(prefetch 워커 스레딩 모델·심볼 소스)와 C(wedge 판정 상태/흐름)는 동작 정의 필요. A는 경계만. |
| NFR Requirements | **실행(minimal)** | 타임아웃 값(3s/5s)·patience(3분)·health-wait(60s)·동시성(NFR-2 워커 분리)이 NFR. ⚠️ alpaca-py 타임아웃 노출 실측 항목 포함. 신규 런타임 의존성 0 확인. |
| NFR Design | **실행** | 타임아웃 주입 경로(SDK vs httpx 폴백) 확정, prefetch 워커를 CommandBus와 분리하는 스레딩 설계, self-heal 분기의 fail-closed 처리(SECURITY-15). |
| Infrastructure Design | **SKIP** | 로컬 systemd 데몬, 클라우드 인프라 없음. |
| Code Generation | **실행** | worktree 게이트 후. 아래 단위 순서대로. |
| Build & Test | **실행** | pytest(Python) + bun test(launcher). 회귀 + 신규(타임아웃/self-heal 모킹). |

## 2. 작업 단위 (Construction, 레이어 경계로 2분할 · 순차)

> 단일 worktree(parent `feat/F14` + 서브모듈 `feat/F14`)에서 둘 다 진행. 서브모듈 gitlink는 머지 시점만 커밋.

- **U1 — Python 데몬 복원력 (A + B)** · 검증 pytest
  - A. `AlpacaBroker`(alpaca_broker.py) + Alpaca 데이터 provider(alpaca_provider.py)에 connect 3s/read 5s
    타임아웃. SDK 파라미터 노출 시 사용, 미노출 시 하부 HTTP 세션/httpx 레벨 강제(⚠️ NFR Design 실측).
  - B. `detect_wakes` 동기 fetch 제거 → 별도 **prefetch 워커**(가격 5s/바 60s)가 BarCache를 채우고,
    detect_wakes는 캐시만 read. CommandBus 단일 워커에 얹지 않음(read-only, NFR-2). docstring 불변식 충족.
- **U2 — 런처 self-heal (C)** · 검증 bun test · **서브모듈**
  - C. `DaemonService.ensureRunning`에 wedge 분기: active + published_at advance 0회가 **3분** 지속 →
    `systemctl --user restart` **1회** + health-wait **60s** → attach 또는 fail-closed 진단 보고.
    정상 긴 턴(중간 advance)은 절대 죽이지 않음. 콜드스타트 grace 예외 필요 여부는 Design에서 결정.

**순서**: U1(A→B) → U2(C). 근거: A는 근본 방어(독립·저위험)라 먼저, B는 같은 Python 레이어 연속,
C는 안전망이라 마지막. 단, 셋은 기능적으로 독립이라 순서는 권고일 뿐.

## 3. 의존성
- U1.A ↔ U1.B: 독립이나 같은 worktree·같은 테스트 러너 → 한 단위로 묶음.
- U2.C: U1과 독립(런처는 published_at만 관찰). 단 검증 시 U1 적용된 데몬이 있으면 wedge 빈도↓로
  실측이 어려움 → C는 모킹 기반 단위테스트로 검증(실서버 wedge 재현에 의존하지 않음).
- ⚠️ NFR Design의 alpaca-py 타임아웃 실측이 U1.A 코드 방식을 가른다(SDK param vs httpx).

## 4. 워크플로 시각화 (ASCII)

```text
[Requirements DONE]
      |
      v
[Workflow Planning] <- 현재(승인 대기)
      |
      v
[Functional Design]      (B 워커/심볼소스, C wedge 흐름)
      |
      v
[NFR Requirements(min)]  (타임아웃/patience/의존성0/SDK 실측항목)
      |
      v
[NFR Design]             (타임아웃 주입경로 확정, 워커 분리, fail-closed)
      |
      v
[Infrastructure Design: SKIP]
      |
      v
[worktree: parent feat/F14 + submodule feat/F14]
      |
      v
[Code Gen U1 (A->B, pytest)] --> [Code Gen U2 (C, bun test)]
      |
      v
[Build & Test: pytest 회귀+신규, bun test launcher]
```

## 5. 위험 / 롤백
- 위험: 라이브 에이전트 데몬의 스케줄러/스냅샷 경로 수정(U1.B) + 런처 자동 restart(U2.C).
- 완화: 모두 방어적(타임아웃/캐시/자가복구), worktree 격리, 단위/통합 테스트 + worktree 라이브
  검증(paper 계정, read-only) 후 머지. self-heal은 fail-closed(거짓 attach 금지, SECURITY-15).
- 롤백: 브랜치 폐기 / 서브모듈 gitlink 미커밋이면 영향 0.

## 6. 보안 (Security Baseline, enforce)
- SECURITY-03: 신규 로그에 토큰/API 키 미출력(self-heal 진단/타임아웃 경고).
- SECURITY-11: 다층 방어(타임아웃+try/except+self-heal), 라이브 데몬 이중기동 금지.
- SECURITY-15: 외부 호출(HTTP/systemctl) 명시적 에러 처리, self-heal 실패 시 fail-closed.
- 그 외 N/A(웹/DB/IaC/인증/배포/의존성 신규 없음).
