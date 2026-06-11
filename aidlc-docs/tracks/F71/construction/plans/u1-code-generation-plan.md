# F71 / U1 server-runtime — Code Generation Plan

> Functional SKIP(신규 데이터모델 없음). NFR 경량(비번 fail-closed, QR 위생). worktree feat/F71.

## 신규
- [x] `operator-console/launcher/serve.ts` — resolveServePassword(env→.env→fail-closed) /
      detectTailscaleIp(주입식 exec) / buildPairingPayload(순수) / serveEnv / runServe / runQr
- [x] `operator-console/test/launcher-f71.test.ts` — 위 전부 단위테스트

## 수정
- [x] `launcher/cli.ts` — OWNED 서브커맨드 `serve`/`qr` 라우팅(help에도 표기)
- [x] `launcher/unit-template.ts` — `autostock-serve.service` 렌더(renderServeUnit)
- [x] `launcher/install.ts` — serve 유닛 설치/enable 추가
- [x] `operator-console/package.json` — `qrcode-terminal` 의존성

## 검증
- [x] `bun test` (operator-console) 그린
- [x] 비번 미설정 시 serve 기동 거부(fail-closed) 테스트
- [x] QR payload에 비번 포함하되 로그 경로엔 미출력 확인
