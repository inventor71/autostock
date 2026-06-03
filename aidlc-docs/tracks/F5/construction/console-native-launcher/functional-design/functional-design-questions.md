# F5 Functional Design — 명확화 질문 (유닛 `console-native-launcher`)

요구사항은 확정됐고, 설계에서 굳혀야 할 **운영/UI 결정 4개**만 확인합니다.
`[Answer]:` 뒤에 letter로 답해주세요. 맞는 게 없으면 `X) 기타` + 설명.

---

## Question 1 — autostock 로고 워드마크 레이아웃 (FR-2)
opencode 로고는 "open"+"code" 2-세그먼트 블록폰트입니다. "autostock"(9자)을 어떻게 배치할까요?
(아래는 배치 미리보기 — 실제 글리프는 기존 블록폰트 스타일/시머 유지)

A) **한 줄 워드마크** "autostock" (가로로 김 — 좁은 터미널에서 잘릴 수 있음)
```
  ┌────────────────────────────────────┐
  │   a u t o s t o c k                 │
  └────────────────────────────────────┘
```

B) **2줄 스택** "auto" / "stock" (세로로 쌓음 — 좁아도 안전, 가장 추천)
```
  ┌──────────────────┐
  │   a u t o        │
  │   s t o c k      │
  └──────────────────┘
```

C) **2-세그먼트 가로** "auto"│"stock" (opencode와 동일한 좌/우 구조)
```
  ┌──────────────────────────┐
  │   a u t o   s t o c k     │
  └──────────────────────────┘
```

X) 기타 (아래 [Answer]: 뒤에 설명)

[Answer]: B

---

## Question 3 — systemd 서비스 정책 (FR-4) — 트레이딩 데몬 수명
트레이딩 데몬(`main.py --mode agent --steering`) systemd user 서비스의 재시작/부팅 정책은?
(데몬이 죽으면 장중 트레이딩이 멈추므로 중요)

A) **크래시 시 자동 재시작(`Restart=on-failure`) + 부팅/로그인 시 자동 시작(`enable` + linger)** — 데몬이
   사람 개입 없이 항상 떠 있음 (운용 신뢰성 최고, 추천)
B) **크래시 시 자동 재시작만**, 부팅 자동 시작은 안 함 (시작은 `autostock` 실행 시 수동 기동)
C) **자동 재시작 없음** — 런처가 띄우고, 죽으면 다음 `autostock` 실행 때 다시 기동
X) 기타 (아래 [Answer]: 뒤에 설명)

[Answer]: A

---

## Question 3 — 콘솔(TUI) 종료 시 데몬 수명 (FR-3/FR-4)
`autostock` 콘솔 TUI를 닫으면 트레이딩 데몬은?

A) **계속 실행** (detached) — 콘솔은 운용 창일 뿐, 데몬은 장중 계속 트레이딩 (추천; F4 detached 설계와 일관)
B) 콘솔과 **함께 종료** (데몬도 내림)
X) 기타 (아래 [Answer]: 뒤에 설명)

[Answer]: A

---

## Question 4 — `autostock` 설치 위치 / PATH (FR-3)
`autostock` 명령을 어디에 설치할까요?

A) **`~/.local/bin/autostock`** (user 레벨, sudo 불필요; PATH에 없으면 안내) — 추천
B) **`/usr/local/bin/autostock`** (시스템 전역, sudo 필요)
C) **`~/.bun/bin`** 등 기존 bun 경로 (이미 PATH에 있음)
X) 기타 (아래 [Answer]: 뒤에 설명)

[Answer]: A
