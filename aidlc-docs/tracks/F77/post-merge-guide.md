# F77 — Post-Merge Guide (StockTwits 리테일 sentiment 신호)

## 무엇이 바뀌나 (prod 브랜치)

1. **데몬에 시간당 스윕 잡** (`sentiment_sweep`): ET 04:00–20:00 창에서 매시 전
   유니버스(131심볼) StockTwits 무인증 스트림을 훑어 자가 라벨 집계를
   `workspace/sentiment/<ET날짜>.jsonl`에 append. LLM 비용 0, HTTP 131회/시간
   (예산 150 캡, 429/403 시 그 tick 중단·부분 저장).
2. **research 브리프에 "Retail sentiment" 섹션**: 자기 베이스라인 대비 bull-ratio
   |z|≥2.0 이상치 상위 5개만 (critic 반영: 메시지량 z는 스트림 30개 캡 포화로 폐기). **콜드스타트 컷(min_baseline_points=12 ≈ 12 스윕시간)** 때문에
   머지 당일 오후까지는 섹션이 안 뜨는 게 정상 — 스윕이 ~12시간 돌아야 베이스라인이 생김.
3. **intraday 브리프**: 보유/워치 종목에 이상치가 있을 때만 `sentiment SYM: ...` 라인.
4. 신규 설정 블록 `signals.sentiment:` (settings.yaml — 기본값으로 동작, env 키 없음).

## 사전 조건

- **데몬 재시작** (스윕 잡 등록 + 브리프 경로).
- 콘솔/외부 키 변경 없음. `workspace/sentiment/`는 자동 생성.

## 실사용 검증 체크리스트

1. 데몬 재시작 후 로그에서 `sentiment sweep scheduled every 60m` 확인.
2. (ET 창 내) 1시간 내 로그 `sentiment sweep: N collected, ...` + `ls workspace/sentiment/`
   → 오늘 ET 날짜 `.jsonl`, 심볼 수가 유니버스(~131)에 근접하는지.
3. **다음날부터** research 턴 브리프(agent-trace 또는 턴 프롬프트)에 이상치가 있으면
   "Retail sentiment" 섹션 — 조용한 날은 섹션 없음이 정상 (이상치 없음 = 무출력 설계).
4. 차단 시나리오: 로그에 `sentiment sweep aborted ... retrying next tick`가 떠도
   데몬/턴은 정상이어야 함.
5. "정상" 기준: 일당 파일 1개에 시간당 ~131행 누적, 인기주(NVDA/TSLA)는 tagged 10+,
   비인기주는 tagged 한 자리(이상치 후보에서 min_tagged=8로 자동 컷).

## 튜닝 노브 (settings.yaml `signals.sentiment:`)

- 민감도: `z_threshold`(기본 2.0), `top_k`(5), `min_tagged`(8), `min_baseline_points`(12)
- 부하: `sweep_minutes`(60), `request_gap_s`(0.5), `hourly_budget`(150), `window_et`
- 끄기: `enabled: false` (스윕·브리프 모두 무출력)

## 알려진 한계 / 리스크

- **무인증 비공식 엔드포인트**: 공식 보장 없음. 기본 python UA는 403이라 데스크톱
  UA를 보냄 — StockTwits가 필터를 강화하면 스윕이 조용히 degraded(백오프)되고
  시스템은 무영향. 그 경우 공식 파트너 API 신청 또는 소스 교체 검토.
- StockTwits 모집단은 낙관 편향(~75% bull) + 자기선택 트레이더 — z-정규화로
  보정하지만 절대값 해석 금지 (브리프 문구에 명시됨).
- wake 트리거/고빈도 폴링은 범위 외 (베이스라인 축적 후 후속 트랙).
- 롤백: 커밋 revert로 충분 (workspace/sentiment/ 파일은 무해, 원하면 삭제).
