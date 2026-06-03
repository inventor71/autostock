# NFR Requirements — Unit B: tui-components (TypeScript)

## 결론: 0 new runtime deps

`packages/tui-trading/`은 기존 opencode 포크가 이미 사용하는 의존성만 활용:

| 의존성 | 버전 | 용도 | 신규 여부 |
|--------|------|------|----------|
| `@opentui/solid` | catalog: | UI 프리미티브 (`<box>`, `<text>`, signals) | 기존 |
| `@opentui/core` | catalog: | 터미널 차원, renderer | 기존 |
| `@opentui/keymap` | catalog: | 키맵 바인딩 | 기존 |
| `solid-js` | catalog: | 반응형 프리미티브 (createSignal 등) | 기존 |
| `fs` (Node 내장) | — | 파일 읽기 (monitor.json, snapshot, thesis) | 내장 |

- `catalog:` = bun workspace catalog (root `package.json`에서 버전 관리)
- 새 npm 패키지 추가 불필요 → **SECURITY-10 (supply chain)** 리스크 없음

## 빌드 설정

- turbo 빌드 그래프에 `tui-trading` 추가
- `tsconfig.json`: opencode 패키지의 tsconfig를 extends
- opencode `package.json`에 `"@tui-trading": "workspace:*"` 의존성 추가

## 성능 고려 (NFR-2)

- 타임라인 바 렌더링: turns ≤ 8개 → O(1) 수준
- 오버레이: 클릭 시에만 렌더 → 상시 비용 0
- 폴링: 1.5s setInterval (기존 사이드바와 동일) → 추가 부하 무시 가능
- thesis 파일: 오버레이 열 때만 1회 읽기
