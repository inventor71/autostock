# F81 — Post-Merge Guide (13F 보유종목 시그널 소스)

## main에서 무엇이 바뀌나
공개 보유내역(1차 = Situational Awareness LP의 SEC 13F)을 주기적으로 따와 봇의 **tradeable
유니버스**와 **리서치 브리프**에 공급하는 신규 시그널 소스. **기본 OFF** — 켜기 전엔 동작/거동 변화 없음.

## 활성화 전제조건
1. **config**: `config/settings.yaml`의 `signals.disclosed_holdings.enabled: true`로 변경.
2. **User-Agent**: 같은 블록 `user_agent`에 **실제 연락처 이메일** 기입 (SEC fair-access 정책 필수).
3. **데몬 재시작**: 설정 반영 + 리프레시 잡 등록을 위해 데몬 재시작.
   - 부팅 시 1회 즉시 리프레시(데몬 스레드, 논블로킹) + 이후 `refresh_hours`(기본 24h)마다.

## 동작 방식 (한 줄)
데몬 리프레셔가 **유일하게** SEC를 HTTP로 따와 `workspace/holdings/sec_13f_<cik>.json`에 정규화 캐시
기록 → 리서치 턴/유니버스는 그 캐시를 **읽기만**(HTTP 0). 외부 장애는 해당 소스만 degrade, 턴/데몬
무중단.

## 실사용 검증 체크리스트
1. **캐시 생성 확인** (데몬 재시작 ~1분 후):
   ```
   ls -l workspace/holdings/            # sec_13f_0002045724.json 존재?
   cat workspace/holdings/sec_13f_0002045724.json | head -40
   ```
   → `as_of`(분기말), `rows`(ticker/side/weight), `unmapped_n`이 보이면 정상.
   - 로그: `holdings refresh scheduled every 24h (1 provider(s))` / `holdings: sec_13f:... refreshed — N rows ...`.
2. **유니버스 편입 확인**:
   ```
   venv/bin/python -c "from config.config import get_settings; from src.universe.factory import resolve_universe; u=resolve_universe(get_settings()); print('CLSK' in u, 'RIOT' in u, len(u))"
   ```
   → 기본(shorting OFF): SA LP의 **롱 보유종목**(CLSK/RIOT/IREN/CORZ/…)이 유니버스에 추가됨.
     풋(NVDA/AVGO/…)은 **추가 안 됨**(brief-only) — 방향 오인 방지.
3. **브리프 노출 확인**: research turn 트리거 후 마커 오버레이/`agent-trace`에서
   `[기관공시] Situational Awareness LP (13F YYYY-MM-DD): LONG … · SHORT … · unmapped N` 라인 확인.
4. **"정상"의 모습**: as_of가 최근 분기말(45일 시차 내), 롱/숏 방향이 thesis와 일치
   (롱=마이너/AI-인프라, 숏=AI-하드웨어 풋), unmapped 소수(현재 SA LP 기준 ~5건).

## 숏-사이드를 켜려면 (선택)
`risk.shorting_enabled: true`일 때만 풋 underlying이 유니버스에 **숏 후보**로 편입됨. 실제 숏 진입은
기존 RiskManager 게이트(F54/F60: ETB/할트/필수 스톱)를 그대로 통과 — 본 트랙은 게이트 무변경/무우회.

## 튜닝 노브 (`signals.disclosed_holdings`)
- `refresh_hours`(24): 폴링 주기. 13F는 분기 공시라 더 짧출 이유 거의 없음.
- `max_age_days`(135): 이보다 오래된 filing은 오버레이/유효성에서 제외(매니저 신고 중단 대비).
- `brief_top_n`(6): 브리프에 표시할 사이드별 종목 수.
- `request_gap_s`(0.5): SEC 요청 간격.
- `providers`: 매니저 추가 = `{type: sec_13f, cik: "<10자리>", manager_name, overlay}` 한 줄 더.
  `overlay: false`로 두면 유니버스 미편입·브리프 전용.

## CUSIP 매핑 (커버리지)
`config/holdings/cusip_ticker.json` 로컬 정적 맵. 매핑 안 되는 CUSIP은 **드롭 + `unmapped_n` 집계**
(브리프에 "unmapped N"). 새 종목 커버 = 이 JSON에 `"CUSIP": "TICKER"` 추가. (틀린 매핑은 unmapped보다
나쁘니, 확실한 것만 추가.)

## 확장 (다른 공시 소스 추가)
`src/signals/holdings/providers/<x>.py`에 `fetch_snapshot()→HoldingsSnapshot` 구현 +
`provider.py`의 `_BUILDERS`에 `type` 한 줄 등록. overlay/brief/store/refresher는 **무변경**(소스-무관).

## 롤백
- 즉시 무력화: `enabled: false` + 데몬 재시작 (코드 롤백 불필요).
- 완전 롤백: 트랙 커밋 revert. 유니버스는 base∪themes로 복귀(오버레이 union-only라 부작용 없음).
- 캐시 청소(선택): `rm -rf workspace/holdings/`.

## 알려진 한계 / Out-of-scope
- **자동 미러링/자동 주문 아님** — 13F 종목을 유니버스 후보로만 추가(에이전트가 독립 판단).
- 옵션 자체 거래 불가(봇은 주식/숏). 풋은 방향 신호로만 반영.
- 13F는 **분기 + 최대 45일 시차** — 이미 청산/변경됐을 수 있음(브리프에 "context only" 명시).
- CUSIP→ticker는 로컬 맵 한도 내 커버(현재 SA LP ~5건 unmapped). 외부 CUSIP API는 미포함(후속).
- 13F 외 공시(13D/G, Form 4)는 미포함(FR-1 추상화로 후속 plugin 가능).
- 사전 존재(F81 무관) 실패: `tests/signals/test_sentiment_sweep.py` 3건(날짜 의존, main에서도 실패).
