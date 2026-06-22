# F88 / U2 — SandboxRunner (Docker 격리) construction record

## 설계 결정
- **커스텀 이미지 빌드 안 함**: stock `python:3.12-slim`을 **digest 핀**(SECURITY-10,
  `python@sha256:d764…`)으로 쓰고, trusted `entry.py`(stdlib만)를 per-run mount. 공급망 표면↓,
  유지보수↓. 이미지 업그레이드는 `SandboxConfig.image`로.
- **entry.py(신뢰, 미스크린)**가 predicate를 importlib로 로드→`should_fire(ctx)` 호출→strict JSON
  verdict 또는 structured error를 stdout으로. predicate만 untrusted.
- **fail-closed 분류**(SandboxResult.error): docker-unavailable / timeout / nonzero-exit /
  no-output / bad-output / oversize-output / ctx-load / predicate-import / no-entrypoint /
  predicate-raised / bad-return. **어떤 실패도 fire 안 됨**(verdict.fire=False 고정).
- **preflight()**(critic#5): 데몬 부팅 시 docker 도달성 확인 → 불가 시 큰 소리(조용한 fail-closed 금지).

## docker run 하드닝 (보안 경계)
`--network=none --read-only --user 65534:65534 --security-opt no-new-privileges
--cap-drop=ALL --pids-limit --memory(+swap=mem) --cpus --tmpfs /scratch -v {predicate,ctx,entry}:ro
--workdir /run -e HOME/TMPDIR/PYTHONDONTWRITEBYTECODE python -I -B /run/entry.py`.
src 미마운트(존재 자체 X) · env에 시크릿 미전달(-e 최소) · timeout 시 `docker kill` 정리 · tmpfs만 쓰기.

## 검증 (tests/triggers/test_sandbox.py, 실제 컨테이너; docker 없으면 skip)
**10 passed (9.5s)** — 수용 기준 전부 실증:
- preflight ok / 정상 fire·no-fire round-trip / ctx 주입이 결정 구동
- **시크릿 비가시**(데몬 env의 FAKE_BROKER_SECRET → 컨테이너에서 ABSENT)
- **네트워크 차단**(socket connect → predicate-raised, fire=False)
- **호스트 소스 미마운트**(open('/app/src/...') → predicate-raised)
- **무한루프 timeout**(while True → error=timeout) / predicate 예외 fail-closed / bad-return·non-dict 거부

## Security 컴플라이언스 (U2)
SECURITY-06(최소권한: cap-drop/non-root/ro mount만), 07(net=none), 09(시크릿 제거 env·no-new-priv·
에러 detail은 짧은 tail만), 10(이미지 digest 핀), 15(fail-closed 전수) — 전부 실증 테스트로 충족.

## 파일
- 신규: `src/agent/triggers/sandbox.py`, `tests/triggers/test_sandbox.py`
- 수정: `src/agent/triggers/__init__.py` (sandbox export)
- 미해결(Infra Design): prod systemd --user docker 소켓 접근(SupplementaryGroups=docker/rootless) — U5/Infra.
