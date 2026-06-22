# F88 / U5 — Authoring surface (CLI 서브커맨드) + daemon 배선 construction record

> **결정 변경(critic#1 후, 사용자 재승인)**: 원래 "daemon-호스팅 HTTP MCP 서버" → **CLI 서브커맨드**.
> 이유: agent 세션엔 MCP 배선 0(전부 신규), repo 관용구는 stdio+file-IPC, TriggerStore가 이미 파일
> 기반이라 CLI가 직접 쓰면 daemon Evaluator가 디스크에서 집어감(live 연결 불필요). 최소 머지 리스크.

## 구현
- **`python -m src.agent.tools trigger {register,list,inspect,cancel}`** (`src/agent/tools/__main__.py`):
  watch 서브커맨드 패턴 미러, AGENT_JOURNAL_ROOT 기준 TriggerStore에 직접. register는 `--predicate-file`
  + spec args(`--id/--thesis/--cadence/--ttl-days/--sources-json/--primary-symbol/--no-entry-inducing`).
  TriggerError→{ok:false,error,violations}, 기타 예외→구조화 error(트레이스백 X). agent는 이미
  `Bash(python -m src.agent.tools:*)` 허용 → 추가 권한/MCP/토큰 불필요.
- **TriggersConfig** (`settings.py`, `triggers:` 블록): enabled(기본 False), tick_seconds, sandbox
  (image digest 핀/timeout/mem/cpu), webfetch_allowlist, max_consecutive_errors, min_fire_gap_s,
  wake_timeout. `config.config.Settings.triggers: dict={}` 추가.
- **daemon 배선** (`agent.py._setup_triggers`, steering-gated): enabled 시 SandboxRunner+**preflight
  loud fail**(critic#5) → TriggerStore + BrokeredFetcher(signal_resolver=market fns, httpx, allowlist)
  + TriggerEvaluator → `add_seconds_job(tick, tick_seconds, "trigger_eval")`. **disabled면 완전 inert**
  (NFR: 기능 off→기존 동작 동일). 모든 실패는 daemon 안 죽임.
- **ctx-schema.md 시딩**(critic#7, `schema_doc.py`): agent가 src 못 봄(F39) → predicate/ctx 계약을
  `workspace/triggers/ctx-schema.md`로 시드(daemon 부팅 시). 계약 SSOT.
- signal_resolver: macro/movers/earnings/holdings는 기존 market 툴 함수로; **sentiment는 후속**
  (fail-honest `_error`).

## 검증
- `tests/triggers/test_tools_cli.py`(6) + `test_settings_and_schema.py`(4) → **10 passed**.
  register 성공/screen-violations/bad-sources/list/inspect/cancel/no-entry-inducing/config defaults·
  from_block/schema 계약·seeding.
- agent 모듈 import 클린, `get_settings().triggers`={} (off). **triggers 전체 101 passed.**

## Security 컴플라이언스 (U5)
SECURITY-05(register 인자/spec/AST 검증=U1 재사용), 08(authoring은 agent 자기 workspace 한정,
normal 모드 src 불가시 F39 불변), 10(이미지 digest 핀 in config), 15(CLI 예외→구조화 error,
daemon 배선 실패→inert). 가시성(FR-10): register/cancel/list/inspect 모두 기존 tools CLI 권한 안.

## 파일
- 신규: `src/agent/triggers/{settings,schema_doc}.py`,
  `tests/triggers/{test_tools_cli,test_settings_and_schema}.py`
- 수정: `src/agent/tools/__main__.py`(trigger 서브커맨드), `config/config.py`(triggers 필드),
  `src/trading/modes/agent.py`(_setup_triggers + resolver + schema seed)
- 미해결: settings.yaml에 주석 예시 블록(post-merge-guide에 문서), prod systemd docker 소켓(Infra/guide).
