# F46 — Requirements & Root-Cause: 에이전트 `account` 툴 작동 불가

**깊이**: Minimal (명확하고 격리된 버그, 근본 원인 실측 확인됨)
**상태**: 승인 대기

## 1. 증상 (research turn 로그 / 사용자 제보)

research turn 로그에 반복적으로:

> ⚠️ `account` tool still down — alpaca-py missing from the permitted `python3`
> (the multi-day issue, lesson #11). Data tools work fine (yfinance).

즉 데이터 툴(`quote`/`indicators`/`news`/`scoreboard`, yfinance 기반)은 정상,
`account` 툴만 실패. 에이전트는 브로커 실측(equity/포지션/레스팅 주문) 없이
저널 기억에만 의존하게 되어 fill 누락·desync 위험 (그래서 lesson #11로 자가기록).

## 2. 근본 원인 (실측 확인)

에이전트(PM)는 모든 툴을 Bash 서브프로세스로 실행한다 (advisor-only, 읽기 전용):

```
python -m src.agent.tools account   →  market.account(_broker())
                                        _broker() → AlpacaBroker(...)   # alpaca-py 필요
```

- **데몬은 정상**: systemd `--user` 유닛의 `ExecStart`는 절대경로 venv 인터프리터
  (`/home/.../autostock/venv/bin/python main.py …`)로 데몬을 띄운다. 데몬 자체는 venv에서
  돌아 alpaca-py가 있다.
- **에이전트 서브프로세스는 PATH 구멍**: 데몬은 `claude` CLI를 띄울 때
  `scrub_agent_env(dict(os.environ))` 환경을 넘긴다(`session.py:215`). systemd `--user`는
  로그인 셸 PATH를 물려받지 않으므로, 유닛에 박힌 PATH가 곧 에이전트의 PATH다:

  ```
  Environment=PATH=/home/jihoonpark/.nvm/versions/node/v24.9.0/bin:/usr/local/bin:/usr/bin:/bin
  ```

  이 PATH에는 **venv bin 디렉터리가 없다**. (이 PATH는 `claude` 바이너리(nvm node bin)를
  찾게 하려고 launcher가 박은 것 — `daemon.ts:resolveDaemonPath`, 참고 [[daemon-claude-cli-path]].)

- 따라서 에이전트 Bash 안에서:
  - `python` → 존재하지 않음 (`/usr/bin/python` 없음) → 에이전트가 `python3`로 대체 (로그의 "the permitted `python3`")
  - `python3` → `/usr/bin/python3` (시스템 파이썬)

- **시스템 `/usr/bin/python3`의 실측 결과**:
  | 모듈 | 결과 |
  |------|------|
  | yfinance | ✅ import OK (시스템 전역 설치) |
  | pandas | ✅ import OK |
  | **alpaca** | ❌ `ModuleNotFoundError: No module named 'alpaca'` |

  → yfinance 기반 데이터 툴은 동작, alpaca-py가 필요한 `account`만 실패.
  `AlpacaBroker.__init__`이 의도대로 `BrokerError("alpaca-py not installed")`를 던진다
  (`alpaca_broker.py:76`). 가드는 정상; **원인은 잘못된 인터프리터**.

증상(데이터 툴 정상 + account만 실패)이 이 원인과 정확히 일치한다.

### 곁가지 사실 (혼동 방지)
- 프로젝트에 venv가 둘 있다: `venv/`(완전 — alpaca-py 0.43.2 + yfinance + pandas)와
  `.venv/`(거의 비어있음 — alpaca·yfinance·pandas 없음). 데몬 `ExecStart`는 `venv/`를 쓴다.
  이번 버그는 venv 선택 문제가 아니라 **에이전트 서브프로세스의 PATH**에 그 venv bin이
  없다는 문제다.

## 3. 요구사항

- **FR-1**: 에이전트가 실행하는 `python`/`python3 -m src.agent.tools <cmd>`가 데몬과 동일한
  Python 환경(= venv, alpaca-py 포함)에서 돌아야 한다. 특히 `account`가 브로커 실측을 반환해야 한다.
- **FR-2**: 어떤 기동 경로(systemd, docker-verify attach, foreground/tmux)에서도 성립해야 한다 —
  특정 systemd 유닛 PATH에 의존하지 않는다.
- **NFR-1**: 회귀 없음 — 기존 yfinance 데이터 툴과 257+ 테스트 그대로 통과.
- **NFR-2 (SECURITY-15)**: `AlpacaBroker`의 fail-closed 가드는 유지 (원인을 없앨 뿐 가드 제거 아님).
- **NFR-3 (SECURITY-03)**: PATH만 다루며 자격증명/토큰 로그 노출 없음. 스티어링 토큰 스크럽
  (`scrub_agent_env`)은 그대로.

## 4. 제안 수정 (single, root-cause)

`src/agent/session.py::_invoke`에서 에이전트 env를 만들 때, 기존 `PYTHONPATH` 주입 바로 옆에
**데몬 자신의 인터프리터 bin 디렉터리를 PATH 앞에 prepend**한다:

```python
import sys
# 기존: PYTHONPATH 주입 → -m src.agent.tools 가 패키지를 찾게
existing_pp = env.get("PYTHONPATH", "")
env["PYTHONPATH"] = str(_REPO_ROOT) + (os.pathsep + existing_pp if existing_pp else "")

# 신규(F46): 에이전트의 python/python3 를 데몬과 동일 인터프리터로 고정
#  → 그 인터프리터(venv)에는 alpaca-py 가 있으므로 account 툴이 산다.
bin_dir = os.path.dirname(sys.executable)
existing_path = env.get("PATH", "")
env["PATH"] = bin_dir + (os.pathsep + existing_path if existing_path else "")
```

근거: `_invoke`는 이미 같은 자리에서 `PYTHONPATH=_REPO_ROOT`를 주입한다. 즉
"스폰된 에이전트가 데몬의 Python 환경을 쓰도록" 하는 보정이 이미 한 축(`PYTHONPATH`) 있고,
이번에 두 번째 축(`PATH` → 같은 인터프리터)을 추가하는 것이다. 두 축이 짝을 이뤄야
`-m src.agent.tools`가 import도 되고 alpaca-py도 보인다.

`sys.executable`은 데몬을 띄운 인터프리터(= `venv/bin/python`, ExecStart의 그것). 그 dirname
(`venv/bin`)에는 `python`·`python3`·`python3.12`가 있고 alpaca-py가 설치돼 있다. prepend이므로
시스템 `/usr/bin/python3`보다 우선한다. `claude` 바이너리는 PATH 뒤쪽(nvm bin)에 그대로 남아
영향 없음.

### 대안 비교 (왜 이 방식인가)
- **(A) launcher 유닛 PATH에 venv bin 추가** (`daemon.ts`/`unit-template.ts`): systemd만 고침.
  docker-verify attach·foreground 경로는 미해결. TS 변경이라 별도 검증 필요. → 보류(부분적).
- **(B) ✅ session.py에서 PATH 주입**: 모든 기동 경로를 한 곳에서, 정확한 altitude(에이전트 env
  구성 지점)에서 고침. PYTHONPATH 주입과 대칭. 단위 테스트로 검증 쉬움. → 채택.
- (C) 프롬프트/CLAUDE.md 템플릿을 `sys.executable` 절대경로로 치환: 프롬프트가 런타임 경로에
  결합되고 워크스페이스 템플릿까지 건드려 산만. → 기각.

## 5. 검증
- **단위 테스트**: `_invoke`가 만든 env의 `PATH[0]`이 `dirname(sys.executable)`이고
  `PYTHONPATH`가 보존되는지 (fake runner로 env 캡처). 빈 PATH 케이스도.
- **라이브(워크트리)**: 메인 venv로 `python -m src.agent.tools account` 직접 실행해 alpaca 실측
  JSON이 나오는지 ([[worktree-live-verification]], read-only paper 계정).
- **회귀**: 전체 테스트 스위트 그린.

## 6. 리스크
**Low.** 에이전트 서브프로세스 env에 PATH 한 줄 prepend. 주문 경로(advisor-only,
decisions.jsonl→RiskManager→Broker) 불변. 롤백은 워크트리/브랜치로 즉시.
