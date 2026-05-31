# F14 요구사항 질문 (한국어)

> 각 질문의 `[Answer]:` 줄에 선택지(A~E) 또는 Other 내용을 적어주세요.
> 답변 후 `/ai-dlc-resume` 하면 이 답을 반영해 요구사항을 확정하고 Workflow Planning/설계로 진행합니다.
> 잠정 권장값은 각 항목에 표시해 두었습니다(미응답 시 권장값으로 진행 가능).

---

## Q-SCOPE. 이번 트랙 포함 범위
이번 F14에 A/B/C 중 무엇을 포함할까요?
- A. A+B+C 전부 (타임아웃 + WakeDetector 완화 + 런처 self-heal) — *권장*
- B. A+C만 (타임아웃 + self-heal), B는 후속 트랙
- C. A만 (타임아웃 근본 방어 최소 수정), B·C는 후속
- D. C만 (런처 self-heal 먼저), A·B는 후속
- E. Other

[Answer]: A

---

## Q-A1. HTTP 타임아웃 값 (connect / read)
half-open 연결을 끊을 read 타임아웃을 얼마로 할까요? (paper Alpaca 호출 정상 지연 고려)
- A. connect 3s / read 5s — *권장(공격적, 빠른 자가복구)*
- B. connect 5s / read 10s (보수적)
- C. connect 5s / read 15s (대형 리서치 배치 여유)
- D. 호출 종류별 차등(주문 계열 길게, 가격/바 짧게)
- E. Other

[Answer]: A

---

## Q-A2. 타임아웃 적용 방식
- A. alpaca-py SDK가 노출하는 타임아웃 파라미터 사용(있으면) — *권장*
- B. 하부 HTTP 세션/httpx(또는 requests) 레벨에서 타임아웃 강제 주입
- C. 우리 쪽 호출 래퍼에 concurrent timeout(future.result(timeout)) 적용
- D. SDK 파라미터 + 래퍼 타임아웃 이중
- E. Other (조사 후 결정 위임 등)

[Answer]: A

---

## Q-B1. WakeDetector 경직성 완화 접근법
- A. `price_ttl`을 루프 주기보다 충분히 크게(예: 5s 루프 → price_ttl ≥ 10~15s) 올리는 최소 변경
- B. detect_wakes의 동기 fetch를 **별도 prefetch 워커**로 분리(주기적으로 캐시 채움, detect는 캐시만 read) — docstring 불변식 충족, *권장*
- C. A + B 둘 다 (TTL도 올리고 prefetch도 분리)
- D. Other

[Answer]: B

---

## Q-B2. (B1에서 B 또는 C 선택 시) prefetch 워커 주기
- A. 가격 5s / 바 60s (현 bars_ttl 유지) — *권장*
- B. 가격 10s / 바 60s
- C. 기존 스케줄러에 별도 seconds job으로 추가 (steering_* 잡과 동일 패턴)
- D. Other

[Answer]: A

---

## Q-C1. 런처 wedge 판정 patience 윈도
active인데 published_at advance가 0회인 채로 이 시간이 지나면 wedge로 판정:
- A. 3분 (빠른 복구, 오탐 위험 약간↑)
- B. 5분 — *권장(정상 리서치/인트라데이 턴 흡수 + 빠른 복구 균형)*
- C. 90초 (가장 공격적)
- D. Other

[Answer]: A

---

## Q-C2. restart 후 health-wait 시간
restart 후 published_at advance를 이 시간까지 기다렸다가 성공/실패 판정:
- A. 60초 (기존 HEALTHWAIT_TIMEOUT_MS 재사용) — *권장*
- B. 90초
- C. 5분 (콜드스타트 리서치 배치까지 여유)
- D. Other

[Answer]: A

---

## Q-C3. 자동 restart 횟수
인터랙티브 `autostock` 1회 실행에서:
- A. 자동 restart 1회만, 실패하면 진단 메시지 보고(저널 명령 안내) — *권장*
- B. 2회까지 시도 후 보고
- C. Other

[Answer]: A

---

## Q-C4. self-heal 위치/형태
- A. 기존 런처 `DaemonService.ensureRunning` 안에 wedge 분기 추가(autostock 실행 시 자동) — *권장*
- B. 별도 명령(`autostock --heal` 등) 수동 트리거
- C. A + 향후 백그라운드 watchdog로 확장 가능한 공통 함수로 추출
- D. Other

[Answer]: A

---

## Q-SEC. 보안 베이스라인 extension
이 작업에 **보안 베이스라인 점검**을 적용할까요? (입력 검증, 비밀/토큰 취급, 최소 권한,
의존성 취약점, 로깅 시 민감정보 마스킹 등) 적용 시 각 단계에서 하드 제약으로 강제.
- A. 적용 (이 트랙은 토큰/systemd 단위/외부 API 키를 다루므로 권장 검토)
- B. 미적용 (내부 신뢰성 수정 위주, 시크릿 신규 취급 없음) — *간이 판단 시 무난*
- C. Other

[Answer]: A

---

## Q-VERIFY. 재발/검증 방법
다음 wedge 발생 시 근본 지점 확정을 위해:
- A. py-spy를 환경에 설치해 두고 재발 시 `py-spy dump --pid` 자동/수동 캡처 — *권장*
- B. 데몬에 주기적 self-watchdog 로그(각 스케줄러 잡 last-run 타임스탬프) 추가
- C. A + B
- D. 검증은 단위/통합 테스트(타임아웃·self-heal 모킹)로 충분, 별도 안 함
- E. Other

[Answer]: A
