# F5 critic 후속 — 정책 분기 1개

critic 검토에서 나온 지적은 대부분 엔지니어링 보강으로 **이미 문서에 반영**했습니다.
사용자 결정이 필요한 **정책 분기 1개**만 확인합니다.

## Question 1 — opencode 포크 서브모듈(`operator-console/cli`) 재핀 소유권
F5의 포크 편집(`logo.ts` 글리프, `app.tsx` 타이틀, `tips.tsx`/`footer.tsx`, home/sidebar 배선 등)은
**서브모듈 repo**(`github.com/inventor71/autostock-cli`)에 커밋하고 부모 repo를 **재핀**해야 반영됩니다.
(참고: F4 때 서브모듈 변경분을 아직 커밋+재핀 안 한 백로그가 있음.) 이 시퀀스의 소유 범위는?

A) **F5가 전부 소유** — 서브모듈 커밋 + 원격(autostock-cli) push + 부모 재핀까지 자동 진행 (재현성 최고;
   원격 push 인증이 이 환경에서 가능해야 함)
B) **서브모듈 로컬 커밋 + 부모 재핀까지 F5가**, 원격 push는 사용자가 직접 (인증/타이밍 사용자 통제; F4 백로그도
   같은 방식으로 정리) — 추천
C) **로컬 fork 편집만** F5가 스테이징, 서브모듈 커밋/재핀/ push 전부 사용자가
X) 기타 (아래 [Answer]: 뒤에 설명)

[Answer]: A
