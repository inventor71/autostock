# F5 Tech Stack Decisions (유닛 `console-native-launcher`)

**결론: 신규 런타임 의존 0개.** 기존 도구만 사용.

## 1. `autostock` 런처 런타임 = Bun/TS (신규 의존 없음)
- **결정**: 런처를 **Bun TS 스크립트**로 작성하고, PATH에는 얇은 셸 심(`~/.local/bin/autostock` →
  `exec bun <repo>/operator-console/launcher/cli.ts "$@"`)을 둔다.
- **근거**: 콘솔이 이미 Bun. 프리플라이트가 기존 `operator-console/src/filedrop.ts`(snapshot 읽기·atomic·torn-safe)
  와 `schema.ts`를 그대로 재사용 → 로직 중복/드리프트 없음. 셸로만 짜면 JSON/토큰 처리·snapshot 파싱이 취약.
- **대안 기각**: (a) 순수 bash 런처 — JSON/torn-safe/토큰 비교 취약; (b) `bun build --compile` 단일 바이너리 —
  Q5=A로 기각(포크 전체 컴파일 부담). 심+bun이 `claude`류 UX를 동일 제공.

## 2. systemd 연동 = `systemctl --user` (stdlib spawn)
- **결정**: 런처가 `Bun.spawn(["systemctl","--user", ...])`로 상태/기동/설치 제어. 유닛 파일은 **생성된 텍스트**
  (`~/.config/systemd/user/autostock-daemon.service`), 정책 `Restart=on-failure` + `enable` + `loginctl enable-linger`.
- **근거**: 외부 라이브러리 불필요(시스템 `systemctl`/`loginctl` 호출). user scope = sudo 불필요(Q4=A 정합).
- **유닛 ExecStart**: repo의 venv 파이썬으로 `main.py --mode agent --steering`. (Code Gen에서 정확한 경로/파이썬 인터프리터 확정.)
- **⚠ 유닛 필수 필드 (critic #4, ✅코드확인)**: `WorkingDirectory={AUTOSTOCK_ROOT}` **필수**. `main.py:366`의
  `load_dotenv()`는 경로 인자가 없어 **CWD 기준 상향 탐색**하는데, `systemd --user`의 CWD는 `/`(또는 `$HOME`)이라
  WorkingDirectory가 없으면 root `.env`를 못 찾는다 → `runtime.py:47`이 **랜덤 토큰 생성** → 콘솔 토큰과 불일치 →
  채널이 모든 명령을 거부(메모리 기록 회귀 재현). 방어적으로 `EnvironmentFile={AUTOSTOCK_ROOT}/.env`도 함께 설정.
  `--steering` 데몬은 TTY/stdin 비의존(`agent.py:195` `while True: time.sleep(1)` 블로킹 루프)이라 `Type=simple`
  적합 → **"0 Python 변경" 주장은 성립**, 단 유닛이 CWD/env를 반드시 세팅해야 함.

## 3. 프리플라이트 = TS (기존 모듈 재사용)
- snapshot 읽기 = `filedrop.ts`. mcp 경로 = `AUTOSTOCK_ROOT` + `operator-console/src/mcp-server.ts` 존재 확인.
- **토큰 canonical 소스 (critic #6)**: 런처는 **root `.env`를 canonical 토큰**으로 삼아 (a) 콘솔 env에 **주입**하고
  (b) `cli/.env`/MCP 설정(`.opencode/opencode.jsonc`의 `{env:STEERING_OPERATOR_TOKEN}`)이 **일치하는지 검사**(불일치
  시 warn). 즉 *비교 대상 == 실제 콘솔에 먹는 값*이 되도록 단일 소스로 통일 — "두 .env 비교"가 주입과 어긋나
  false pass/fail 나는 함정(critic #6)을 차단. boolean만 표시(BR-6). 단일-유저 로컬이라 상수시간 비교는
  보안상 큰 의미 없음(무비용 nicety로 유지 가능, 필수 아님).

## 4. 리브랜딩/사이드바/배너 = 포크 내 TS/SolidJS 편집
- 신규 의존 없음. 기존 OpenTUI/SolidJS 컴포넌트 수정(`logo.ts`, `feature-plugins/*`, `sidebar/autostock.tsx`).

## 5. 설치 = 스크립트 (셸 + bun)
- `operator-console/launcher/install.sh`(또는 `bun run setup`): 심 배치(`~/.local/bin`), 유닛 생성/`daemon-reload`/
  `enable`/linger, PATH 안내. 멱등(재실행 안전).

## 6. 테스트 = 기존 러너
- 프리플라이트 판정/토큰 비교/유닛 텍스트 생성 = bun test(기존). 파이썬 무회귀 = 기존 pytest. 신규 dev 의존 없음.

## 보안 매핑
- SECURITY-03: 토큰은 TS 메모리에서만, 출력 금지. SECURITY-11: 권한분리 불변. SECURITY-15: fail-closed 기동.
