# F43 요구사항 — 데몬 코드 버전 스큐 자가치유

## 배경 / 근본원인
- 증상: `autostock-daemon.service`가 2초마다
  `steering: skipping unparseable command line: 1 validation error for SteeringCommand / verb`
  경고를 무한 반복.
- 진단: 데몬 PID 1767528은 **11:19:28** 기동. `research` verb를 추가한 **F38(d55f831)** 머지는
  **20:32:50**. 데몬은 기동 시점의 인메모리 코드를 계속 들고 돌아 신버전 콘솔이 보낸
  `research` 명령을 구버전 `SteeringVerb` Literal로 거부. (로그 허용목록이 `answer`→`place_order`로
  `research`를 건너뜀이 직접 증거.) `steering/commands.jsonl` 단일 라인은 JSON 유효+verb=research →
  파일 손상 아님, **순수 버전 스큐**.
- 기존 자가치유(F14)는 snapshot이 **frozen** 일 때만 재시작. 지금처럼 데몬이 정상 발행 중이면
  트리거 안 됨. 또한 데몬은 자기 **코드 버전을 어디에도 스탬프하지 않아** 런처가 스큐를 알 수 없음.
- 사용자 액션: 수동 `systemctl --user restart` 로 해결 확인.

## 기능 요구사항 (FR)
- **FR-1 (데몬 버전 스탬프)**: 데몬은 기동 시 자신이 실행 중인 코드의 git HEAD SHA를 1회 resolve해,
  publish하는 모든 snapshot 페이로드에 `code_version` 필드로 포함한다. SHA를 못 구하면
  `code_version`을 비우거나 생략한다(크래시 금지).
- **FR-2 (런처 스큐 감지)**: `autostock` 런처는 데몬에 attach하기 직전, snapshot의 `code_version`을
  작업트리 현재 HEAD SHA(`git -C <autostockRoot> rev-parse HEAD`)와 비교한다.
- **FR-3 (자동 재시작)**: 두 SHA가 **다르면 무조건 즉시** `systemctl --user restart` 후 health-wait,
  그다음 attach. (사용자 결정: in-flight LLM turn 보호·마켓 게이팅 **없음**.)
- **FR-4 (미스탬프 데몬)**: snapshot에 `code_version`이 아예 없으면(= 분명한 pre-F43 구데몬) 스큐로
  간주해 1회 재시작한다. 재시작 후 신데몬이 스탬프하므로 수렴(무한 루프 없음).
- **FR-5 (재시작 결과 가시화)**: 자동 재시작이 발생하면 `HealthResult.reason`에
  "stale code — auto-restarted" 류의 문구를 실어 사용자가 무슨 일이 일어났는지 알 수 있게 한다.

## 안전/제약 (NFR & 가드)
- **G-1 (재시작 루프 방지 / fail-open)**: 런처가 **자기쪽 HEAD SHA를 못 구하면**(git 실패·repo 아님)
  스큐 검사를 **건너뛰고** 기존처럼 attach. 불확실하면 재시작하지 않는다.
- **G-2 (재시작은 1회 흐름)**: 스큐 분기는 기존 wedge 분기와 동일하게 `systemctl restart` 1회 +
  health-wait. health-wait 실패는 기존과 동일하게 `DaemonStartError`로 표면화.
- **G-3 (보안)**: snapshot에 SHA(공개 가능한 커밋 해시)만 기록. 토큰/시크릿 미기록(SECURITY-03).
  서브프로세스는 인자 배열 고정(`git rev-parse HEAD`), 셸 인터폴레이션 없음.
- **G-4 (테스트 가능성)**: 런처 비교 로직은 주입된 `run`/`readSnapshot` 의존성으로 단위테스트.
  데몬 SHA resolve는 git 미존재 환경에서도 안전(예외→빈 값).

## 범위 밖 (Non-goals)
- 채널 파싱-실패 라인의 무한 로그/사일런트-노옵 수정 → **별도 트랙**으로 남김(사용자 결정).
- systemd 밖에서 수동 실행된 데몬 대응(이 경우 `systemctl restart`는 systemd 인스턴스를 별도 기동).
  현재 운영은 systemd 유닛이므로 본 트랙 범위 밖, state.md에 한계로 명기.
- 머지 외 임의 작업트리 코드편집(uncommitted) 감지 — HEAD SHA 기준만 사용.

## 수용 기준 (AC)
- AC-1: 데몬 기동 후 `steering/snapshot.json`에 `code_version`(40-hex 또는 빈문자열)이 존재.
- AC-2: snapshot SHA ≠ 런처 HEAD → `ensureRunning()`이 `systemctl restart`를 1회 호출하고,
  health-wait 통과 시 "auto-restarted (stale code)" reason 반환.
- AC-3: snapshot SHA == 런처 HEAD → 재시작 호출 0회, 기존 attach 경로 그대로.
- AC-4: snapshot에 `code_version` 없음 → 재시작 1회(미스탬프 구데몬 취급).
- AC-5: 런처 HEAD SHA를 못 구함(git 실패) → 재시작 0회, 기존 attach (G-1 fail-open).
