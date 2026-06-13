# Performance Test Instructions — F73 viz-shell

로컬 단일 사용자 dev 도구라 부하/스케일 테스트는 **N/A**. 단, NFR-6(데몬 무영향)와
폴링 비용만 가볍게 확인한다.

## PT-1 — 폴링이 데몬에 무영향
- 대시보드는 tRPC 쿼리를 5초 간격 폴링(로컬 파일 읽기). 데몬 프로세스/IPC를 건드리지
  않음 — `viz-shell` 가동 중 데몬 CPU/지연 변화 없음을 관찰로 확인.
- snapshot은 AccountCards·PositionsTable이 공유(`useSnapshot` 단일 쿼리키 → react-query
  dedupe). 5초당 snapshot 파일 1회 read.

## PT-2 — tail 비용
- equity.jsonl은 일 ~1라인(~400B). tailJsonl 상한 8MB는 수십 년치 — 실파일에서
  무시 가능. 비정상적으로 큰 파일에서도 상한 버퍼로 OOM 없음.

## 기대
- viz-shell 가동이 트레이딩 데몬 동작/지연에 측정 가능한 영향 없음 (NFR-6 충족).
- 부하/스트레스/스케일 테스트: **N/A** (단일 로컬 사용자, 외부 트래픽 없음).
