# F73 — Application Design Plan

## 설계 질문 및 답변 (UAQ, 2026-06-12 — 질문 파일 대신 인터랙티브 진행)
| # | 질문 | 답변 |
|---|---|---|
| 1 | 채팅↔SDK 세션 모델 | **명시적 단일 세션** — 글로벌 1세션 + session id 명시 관리 + "New chat" 리셋 |
| 2 | 경계 콜백 거부 처리 | **거부+채팅 표시** — deny 사유를 SDK에 반환(재시도 가능) + 채팅 UI에 ⚠️ 이벤트 표시 |
| 3 | 도구 활동 가시성 | 무선호 → **추천안 채택: 텍스트+도구 요약** (tool 이벤트 요약 라인 스트림) |

## Plan Checklist
- [x] components.md — 컴포넌트 정의·책임
- [x] component-methods.md — 메서드 시그니처 (상세 비즈니스 룰은 Functional Design)
- [x] services.md — 오케스트레이션 (chat 생성 플로우 / 데이터 조회 플로우)
- [x] component-dependency.md — 의존 매트릭스·통신 패턴·데이터 플로우
- [x] application-design.md — 통합 문서
- [x] 설계 완전성·일관성 검증 (Security Baseline 적용 룰 점검 포함)
