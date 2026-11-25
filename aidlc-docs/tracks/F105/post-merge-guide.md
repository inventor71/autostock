# F105 운영

정상 모드와 두 Toss dry 모드의 장중 턴에 같은 정보 갱신과 신선도 구분을 적용한다.
Toss 실제 자동매매의 bracket 제한, read-only 경계, 모델 설정, 위험 한도, 주문/비용 규칙은 유지한다.

## 기록 확인

- 각 journal root의 research-context.json: 가장 최근 주입된 브리프와 종목별 뉴스/가격 상태.
- research-context.jsonl: 턴별 로컬 이력. 정상 workspace와 dry의 research-comparisons 경로는
  기존 gitignore 대상이며 이 파일들은 0600으로 작성한다.
- Toss dry report/account의 research_data: 마지막 장중 정보 상태. as_of를 함께 읽는다.
  아직 새 장중 턴이 없으면 not_recorded가 정상이다. 프로세스 health=ok와 별개다.
- 기존 dry runtime_revisions의 F105 시작 시각으로 적용 전후를 나눠 비교한다.

```bash
venv/bin/python -m src.evals.toss_shadow --dir research-comparisons/toss-shadow/trial-01 report
venv/bin/python -m src.evals.toss_shadow --dir research-comparisons/toss-shadow/trial-fable-20261124 report
```

뉴스 source status=ok도 전체 시장의 모든 뉴스가 확인되었다는 의미는 아니다.
content_status / published_at / source_as_of를 함께 본다. no_recent_dated_items와 stale,
not_checked를 '변화 없음'으로 해석하지 않는다. fallback도 실패하면 추가 확인 필요를 표시한다.

## 설정과 적용

signals.sources의 기존 primary/fallback 설정을 공통 사용한다. 새 credential은 필요 없다.
intraday.market_symbols.us는 SPY/QQQ, kr은 빈 목록이다. 이 값은 관찰용이며 매매 풀은 유지된다.
news.ttl_minutes 기본 15분, 모델 호출 간격과 일별 budget은 기존 설정을 유지한다.

실행 중인 Python 프로세스는 재시작해야 한다. 두 dry는 기존 장부로 재실행하고 init을
다시 호출하지 않는다. 일반 데몬은 다음 console attach에서 F43 버전 차이 감지로 1회 자동
재시작할 수 있다. 실행 중인 모델 턴이 있다면 턴 사이에 attach한다.

이번 적용에서는 11/25 09:52~09:59 KST 두 dry와 정상 paper 데몬 4개를 모두 재시작하고
상태 보존을 확인했다. 현재 실행 코드는 merge 0d458d4다. 뒤따르는 종료 문서 커밋 때문에
console attach가 버전 차이를 감지할 수 있으나, 실행 코드의 추가 변경은 없다.

롤백이 필요하면 턴 종료 후 프로세스를 멈추고 F105 merge commit에 git revert -m 1을
적용한 뒤 기존 장부로 재시작한다. 결정을 삭제하거나 커서를 되감지 않는다.
