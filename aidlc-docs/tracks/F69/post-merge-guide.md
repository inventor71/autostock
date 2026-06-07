# F69 Post-Merge Guide — Health Check TUI 통합

머지 후 운영 브랜치(main)에서 무엇이 달라지고, 어떻게 켜고 확인하는지.

## 무엇이 바뀌나
- 에이전트 데몬(`--mode agent`, steering 활성)이 **5분마다** 경량 시스템 health를
  `steering/health.json`에 발행한다. (외부 API 호출 없음 — process/logs/config_env/resources
  + 스냅샷 파생 account.)
- TUI 상단 상태바(타임라인 NavRow) 끝에 **health 글리프** `· ✓ hp`(색상)가 뜬다. 클릭하면
  9차원(현재 cheap 5차원) 상세 **오버레이**가 열린다.
- 전체 9차원 deep check(broker/llm live 포함)는 기존대로 `scripts/health.py`로 수동 실행.

## 전제 조건
- **데몬 재시작 필요**: 새 seconds-job(`steering_health`)은 데몬 기동 시 등록된다. 런처가
  버전 스큐를 감지해 자동 재시작(F43)하거나, 수동으로 데몬을 재시작.
- 새 config 키: `monitoring.health_publish_seconds`(기본 300). `settings.yaml`에서 조정,
  **`0`이면 발행 비활성**(글리프는 'no data' ○로 표시).

## 실사용 검증 체크리스트
1. **발행 확인**: 데몬 가동 후 5분 내 `steering/health.json` 생성 확인
   - `cat steering/health.json | python -m json.tool` → `overall`, `dimensions`,
     `publish_interval_seconds: 300` 존재.
   - `dimensions` 키 = `process, logs, config_env, resources, account` (broker/llm 없음 = 정상).
2. **비용 없음 확인 (중요)**: 데몬 로그(`logs/autostock.log`)에 발행 시각마다 `AlpacaBroker
   initialized` 스팸이 **쌓이지 않아야** 함. LLM 과금 ping도 없어야 함. (critic HIGH 회귀 가드)
3. **TUI 글리프**: 콘솔(`autostock` 런처)을 띄우면 상단 상태바 끝에 `· ✓ hp`(또는 ⚠/✗/⊘/○).
   - 정상 운영 중이면 `✓`(green). 데몬이 막 떠 스냅샷 전이면 account가 SKIPPED일 수 있음.
4. **오버레이**: 글리프를 **클릭** → 9차원 리스트 오버레이가 뜨고, OK 아닌 차원은 사유가 펼쳐짐.
   다시 클릭 또는 Esc로 닫힘.
5. **stale 표시**: 데몬을 멈춰 health.json이 15분(=interval×3) 넘게 안 갱신되면 글리프가 dim ○.

### "정상"의 모습
- 글리프 `✓ hp` green, 오버레이 summary = "All checks passed." (혹은 운영상 의미 있는 WARNING).
- health.json `ts`가 5분 주기로 갱신.

## 튜닝 노브
- `monitoring.health_publish_seconds`: 발행 주기(초). 더 잦게/뜸하게. `0`=끄기.
- 전체 deep check가 필요하면: `python scripts/health.py`(전체 9차원, broker/LLM 포함, on-demand).

## 롤백
- config `health_publish_seconds: 0` → 발행 즉시 중단(코드 롤백 없이). 글리프는 ○(no data).
- 코드 롤백: 본 트랙 커밋 revert (신규 파일 + 9개 파일 수정, 모두 additive).

## 알려진 한계 / 범위 밖
- 주기 발행은 cheap subset — broker/LLM 연결성 같은 라이브 점검은 포함 안 됨(의도적, 비용/로그
  스팸 회피). 깊은 점검은 `scripts/health.py`.
- health 점검 로직 자체(차원 추가/수정)는 F63/F66 소관, 본 트랙 범위 밖.
- 과거 health 이력/타임라인 없음 — 최신 1건만.
