# F7 — 실행 계획 (Workflow Planning)

> **트랙**: F7 (콘솔 트레이딩-네이티브 카피 & 팁) / **단계**: INCEPTION → Workflow Planning
> **상태**: 작성 완료 — 승인 대기 / **작성일**: 2026-05-30
> **요구사항**: `aidlc-docs/inception/requirements/console-trading-native-copy.md` (APPROVED)

## 1. 위험/규모 평가
- **규모**: 매우 작음 — 카피(문자열) 전용, 파일 2개(`home.tsx`, `tips-view.tsx`).
- **위험**: 낮음 — 기능 동작/경로/MCP 배선 무변경, 롤백 용이(worktree), 타입/테스트로 무회귀 검증.
- **F6/F5 충돌**: 없음 — F7은 `home.tsx` placeholder + `tips-view.tsx` 카피만; F6는 사이드바/`index.tsx` resize, F5는
  로고/런처. 편집 파일 비중첩.

## 2. 단계 결정
| 단계 | 결정 | 사유 |
|------|------|------|
| User Stories | **SKIP** | 단일 운영자 카피 변경; 워크플로는 FR로 포착(F2/F3/F5/F6 일관) |
| Application Design | **SKIP** | 새 컴포넌트/메서드 없음 |
| Units Generation | **SKIP** | 단일 소단위 |
| Functional Design | **SKIP** | 새 데이터모델/비즈니스 로직 없음 — 순수 카피 |
| NFR Requirements | **SKIP** | 0 new deps, 기존 스택; 요구사항 §4에서 NFR 확정 |
| NFR Design | **SKIP** | 동시성/성능 영향 없음 |
| Infrastructure Design | **SKIP** | 로컬 콘솔, 인프라 없음 |
| **Code Generation** | **EXECUTE** | 실제 카피 작성(Part 1 계획 = 구체 문구 제안 → 승인 → Part 2 적용) |
| **Build and Test** | **EXECUTE** | `tsgo --noEmit` + 기존 launcher/console 테스트 무회귀 |

## 3. 단일 단위
`console-trading-native-copy` — F5 콘솔 포크(submodule `operator-console/cli`) 기반, **worktree off F5 base**에서 작업.

## 4. 시퀀스
1. Code Generation **Part 1**: 구체 카피 제안(placeholder 배열 + tips 교체 목록 + 신규 트레이딩 팁 문구) → 승인 게이트.
2. Code Generation **Part 2**: worktree 생성 → 카피 적용 → `tsgo`/테스트 → 커밋.
3. Build and Test: 무회귀 확인.
4. (outward) push/re-pin/merge = 사용자 승인 후.

**참고**: [[feedback-autonomy-construction]] — Part 1(카피) 승인 후 Part 2~Build&Test는 자율 진행, worktree push/merge 직전 정지.
