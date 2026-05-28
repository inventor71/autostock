# NFR Requirements — 추가 확인: 콘솔 UI 스택

_AI-DLC 트랙 F2 · CONSTRUCTION · NFR Requirements · 2026-05-29._
_사용자 제기: "UX/UI가 다각화됐는데 REPL 입력에 적합한 package를 안 써도 되나? seamless·이쁘게(claude cli 같은 느낌) 발전시킬 계획."_

> 아래 `[Answer]:` 를 채워주세요. "신규 런타임 의존성 0"은 hard 요구가 아니라 제가 둔 기본값일 뿐이므로,
> UX 우선이면 푸는 게 맞습니다. 핵심 트레이드오프를 정리했습니다.

---

## 왜 stdlib-only가 약한가 (단순 미관 아님)
- **async 승인 알림 ↔ 바닐라 `input()`**: 설계상 에이전트 결정이 사람-락 종목에 걸리면 콘솔에 비동기 `⚠ 승인 대기`
  줄을 띄움(CQ2=A). 순수 `input()`은 타이핑 중인 줄 위로 출력이 끼어들면 입력 줄이 깨짐 → stdlib로 깔끔히 못 고침.
  `prompt_toolkit`의 `patch_stdout`가 정확히 이 문제용.
- 자동완성(`/명령`·심볼)·히스토리·하단 상태 툴바·색/테이블 없음 → "seamless·이쁨"과 거리가 멈.

## CQ-NFR1 — 콘솔 UI 스택을 어디까지 갈까?
A) **현행 유지 (stdlib만)** — 의존성 0. 그러나 위 결함 감수(async 알림 깨짐, 자동완성/색/테이블 없음).
B) **`prompt_toolkit` + `rich` 채택 (권장)** — 라인 기반 REPL 유지(monitor.sh 패널 모델 그대로):
   - 슬래시 명령/심볼 **자동완성**, **히스토리**, **하단 툴바**(running/paused·승인대기 라이브),
   - `patch_stdout`로 async 알림이 입력을 안 깨뜨림, `rich`로 `/status`·`/positions`·`/orders` 예쁜 테이블.
   - 신규 런타임 의존성 2개(둘 다 성숙·순수파이썬, 잘 관리됨). claude cli **입력 경험에 근접**.
   - 추후 `textual` 전면 TUI로 진화 여지(rich 출력·명령 모델 재사용 가능 → B는 버려지는 작업 아님).
C) **`textual` 전면 TUI로 지금부터** — claude cli처럼 풀스크린 위젯 앱(로그/포지션/결정 패널 + 입력 박스)으로
   `monitor.sh` 대시보드를 **대체**. 가장 이쁨/seamless. 단, 구현량 大 + 아키텍처 변경(패널 `tail` 모델 → 단일
   TUI 앱) + tmux 모니터 패널들과의 관계 재설계 필요. (인-프로세스 데몬이 풀스크린 TUI를 소유.)
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: B

## CQ-NFR2 — (B 또는 C 선택 시) 진행 방식
A) **이번 v1은 선택한 스택으로 바로 구현.** (B면 prompt_toolkit+rich, C면 textual)
B) **단계적**: v1은 B(prompt_toolkit+rich)로 빠르게 seamless 확보 → 이후 별도 트랙에서 C(textual TUI)로 승격.
   (north star가 풀 TUI여도 B가 디딤돌이 됨.) (권장)
X) 기타 (아래 [Answer]: 태그 뒤에 설명)

[Answer]: A

## CQ-NFR3 — (C 선택 시에만) monitor.sh 처리
A) textual 앱이 모니터 패널(로그/결정/포지션)을 흡수 → `monitor.sh`는 콘솔 패널 없이 보조용으로 축소/유지.
B) textual 앱과 monitor.sh 공존(앱은 입력+요약, 상세 tail은 monitor.sh).
X) 기타 (아래 [Answer]: 태그 뒤에 설명) — C를 고르지 않으면 비워두세요.

[Answer]:
