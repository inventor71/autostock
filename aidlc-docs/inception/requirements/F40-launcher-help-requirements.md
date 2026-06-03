# F40 — autostock 런처 `-h`/`--help` 핸들러 요구사항 (minimal depth)

> Track F40 / brownfield / 단일 유닛. 대상 파일: `operator-console/launcher/cli.ts`
> (보조: 도움말 텍스트 헬퍼는 `launcher/` 내 신규 작은 모듈 또는 cli.ts 인라인).

## 배경 / 문제
현재 런처(`cli.ts`)는 인자 파싱·도움말이 없다. `--supervisor`만 가로채고(strip) 나머지를
opencode로 무가공 전달한다. opencode(yargs)는 `-h`/`--help`/`-v`/`--version`을 자체 처리하며
(`index.ts:74-77`), `-h` 전용 분기(`index.ts:195-204`)로 help 텍스트를 **stderr에 출력하고 정상
종료**한다(무거운 미들웨어 미실행). 따라서 `autostock -h`는 이미 opencode의 풍부한 help를 띄우지만
**런처 고유 옵션 `--supervisor`가 어디에도 노출되지 않는다.**

## 결정 (사용자 합의)
- **Help 합성 = Loose fuse.** opencode help를 버리지 않고 그 위에 런처 섹션을 덧붙인다.
- **미인식 옵션 경고/제안은 하지 않는다.** opencode가 `.strict()`(`index.ts:193`)라 unknown 인자는
  이미 `"Unknown argument"`로 거부되고 `.fail()`이 help를 띄운다 → 런처 측 typo 제안은 중복. (당초
  검토했던 FR-3 폐기.)
- **`--version`은 범위 외**(opencode가 처리).

## 기능 요구사항

### FR-1 — Help loose-fuse (`-h` / `--help`)
argv에 `-h` 또는 `--help`가 있으면 런처는:
1. **preflight·데몬 기동을 건너뛴다** (도움말은 데몬/정상 상태와 무관하게 떠야 함).
2. 런처 help 섹션을 **stderr**에 출력한다(FR-2).
3. `-h`/`--help`를 **strip하지 않고** consoleArgs에 남겨 `bun run dev -- …`로 전달 →
   opencode가 자체 help를 그 아래 출력하고 exit.
4. 런처는 opencode exit code로 종료.
- config 해석(`resolveConfig`)은 consoleCwd/env 확보용으로 수행하되, **실패해도 help는 hard-fail
  하지 않는다**: 런처 섹션 + "opencode help 불가(config 오류)" 한 줄을 찍고 exit 0.

### FR-2 — 런처 help 섹션 내용
- 제목 1줄(autostock 런처).
- `--supervisor`: supervisor(read-only, 전체 코드 읽기) 프로파일 진입, **셸 접근 개발자 전용, 평상시
  생략**.
- "그 외 모든 인자는 opencode 콘솔로 그대로 전달됩니다 (예: `autostock -s ses_x` → 세션 재개)."
- 구분선 후 opencode 자체 help가 이어짐을 암시(별도 안내 문구 불필요 — 바로 아래 출력되므로).
- **비밀값 미출력**(BR: 토큰 등 절대 노출 금지).

## 비목표 (Non-goals)
- **미인식 옵션 경고/제안 (前 FR-3 폐기)**: opencode `.strict()`가 unknown 인자를 이미 거부하므로
  런처 측 typo 감지/제안은 중복. 런처는 자기 플래그(`--supervisor`)만 처리하고 나머지는 무판단 전달.
- `--version`/`-v` 런처 처리(opencode가 이미 처리).
- Tight-fuse(opencode help 텍스트 캡처/스플라이스) — yargs 포맷 결합도 회피.
- opencode 플래그 집합을 런처가 알거나 검증하는 것.

## 영향 / 호환성
- 기존 동작 보존: `--supervisor` strip + env 세팅, 일반 인자 패스스루는 그대로.
- `-h`가 이전엔 그냥 opencode로 갔다 → 이제 런처 섹션이 **먼저** 붙고 preflight/데몬을 건너뜀
  (이전엔 데몬 기동 후 opencode help가 떴음 → 개선).

## 테스트 (단위, 순수 로직 위주)
- help 텍스트 빌더: `--supervisor`/패스스루 문구 포함, 비밀 키 미포함.
- 인자 분류: `-h`/`--help` 감지, `--supervisor` strip 유지, 일반 인자/opencode 플래그는 무판단 전달.
- (가능하면) help 모드에서 preflight/daemon 미호출 경로 확인.

## Extension 준수
- Security Baseline: N/A(opt-in 룰 부재) — 단 BR로 비밀 미출력 유지(준수).
- Property-Based Testing: N/A.
