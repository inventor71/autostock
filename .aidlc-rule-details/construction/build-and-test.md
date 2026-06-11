# Build and Test

**Purpose**: Build all units and execute comprehensive testing strategy

## Prerequisites
- Code Generation must be complete for all units
- All code artifacts must be generated
- Project is ready for build and testing

---

## Step 1: Analyze Testing Requirements

Analyze the project to determine appropriate testing strategy:
- **Unit tests**: Already generated per unit during code generation
- **Integration tests**: Test interactions between units/services
- **Performance tests**: Load, stress, and scalability testing
- **End-to-end tests**: Complete user workflows
- **Contract tests**: API contract validation between services
- **Security tests**: Vulnerability scanning, penetration testing

---

## Step 2: Generate Build Instructions

Create `aidlc-docs/construction/build-and-test/build-instructions.md`:

```markdown
# Build Instructions

## Prerequisites
- **Build Tool**: [Tool name and version]
- **Dependencies**: [List all required dependencies]
- **Environment Variables**: [List required env vars]
- **System Requirements**: [OS, memory, disk space]

## Build Steps

### 1. Install Dependencies
\`\`\`bash
[Command to install dependencies]
# Example: npm install, mvn dependency:resolve, pip install -r requirements.txt
\`\`\`

### 2. Configure Environment
\`\`\`bash
[Commands to set up environment]
# Example: export variables, configure credentials
\`\`\`

### 3. Build All Units
\`\`\`bash
[Command to build all units]
# Example: mvn clean install, npm run build, brazil-build
\`\`\`

### 4. Verify Build Success
- **Expected Output**: [Describe successful build output]
- **Build Artifacts**: [List generated artifacts and locations]
- **Common Warnings**: [Note any acceptable warnings]

## Troubleshooting

### Build Fails with Dependency Errors
- **Cause**: [Common causes]
- **Solution**: [Step-by-step fix]

### Build Fails with Compilation Errors
- **Cause**: [Common causes]
- **Solution**: [Step-by-step fix]
```

---

## Step 3: Generate Unit Test Execution Instructions

Create `aidlc-docs/construction/build-and-test/unit-test-instructions.md`:

```markdown
# Unit Test Execution

## Run Unit Tests

### 1. Execute All Unit Tests
\`\`\`bash
[Command to run all unit tests]
# Example: mvn test, npm test, pytest tests/unit
\`\`\`

### 2. Review Test Results
- **Expected**: [X] tests pass, 0 failures
- **Test Coverage**: [Expected coverage percentage]
- **Test Report Location**: [Path to test reports]

### 3. Fix Failing Tests
If tests fail:
1. Review test output in [location]
2. Identify failing test cases
3. Fix code issues
4. Rerun tests until all pass
```

---

## Step 4: Generate Integration Test Instructions

Create `aidlc-docs/construction/build-and-test/integration-test-instructions.md`:

```markdown
# Integration Test Instructions

## Purpose
Test interactions between units/services to ensure they work together correctly.

## Test Scenarios

### Scenario 1: [Unit A] → [Unit B] Integration
- **Description**: [What is being tested]
- **Setup**: [Required test environment setup]
- **Test Steps**: [Step-by-step test execution]
- **Expected Results**: [What should happen]
- **Cleanup**: [How to clean up after test]

### Scenario 2: [Unit B] → [Unit C] Integration
[Similar structure]

## Setup Integration Test Environment

### 1. Start Required Services
\`\`\`bash
[Commands to start services]
# Example: docker-compose up, start test database
\`\`\`

### 2. Configure Service Endpoints
\`\`\`bash
[Commands to configure endpoints]
# Example: export API_URL=http://localhost:8080
\`\`\`

## Run Integration Tests

### 1. Execute Integration Test Suite
\`\`\`bash
[Command to run integration tests]
# Example: mvn integration-test, npm run test:integration
\`\`\`

### 2. Verify Service Interactions
- **Test Scenarios**: [List key integration test scenarios]
- **Expected Results**: [Describe expected outcomes]
- **Logs Location**: [Where to check logs]

### 3. Cleanup
\`\`\`bash
[Commands to clean up test environment]
# Example: docker-compose down, stop test services
\`\`\`
```

---

## Step 5: Generate Performance Test Instructions (If Applicable)

Create `aidlc-docs/construction/build-and-test/performance-test-instructions.md`:

```markdown
# Performance Test Instructions

## Purpose
Validate system performance under load to ensure it meets requirements.

## Performance Requirements
- **Response Time**: < [X]ms for [Y]% of requests
- **Throughput**: [X] requests/second
- **Concurrent Users**: Support [X] concurrent users
- **Error Rate**: < [X]%

## Setup Performance Test Environment

### 1. Prepare Test Environment
\`\`\`bash
[Commands to set up performance testing]
# Example: scale services, configure load balancers
\`\`\`

### 2. Configure Test Parameters
- **Test Duration**: [X] minutes
- **Ramp-up Time**: [X] seconds
- **Virtual Users**: [X] users

## Run Performance Tests

### 1. Execute Load Tests
\`\`\`bash
[Command to run load tests]
# Example: jmeter -n -t test.jmx, k6 run script.js
\`\`\`

### 2. Execute Stress Tests
\`\`\`bash
[Command to run stress tests]
# Example: gradually increase load until failure
\`\`\`

### 3. Analyze Performance Results
- **Response Time**: [Actual vs Expected]
- **Throughput**: [Actual vs Expected]
- **Error Rate**: [Actual vs Expected]
- **Bottlenecks**: [Identified bottlenecks]
- **Results Location**: [Path to performance reports]

## Performance Optimization

If performance doesn't meet requirements:
1. Identify bottlenecks from test results
2. Optimize code/queries/configurations
3. Rerun tests to validate improvements
```

---

## Step 6: Generate Additional Test Instructions (As Needed)

Based on project requirements, generate additional test instruction files:

### Contract Tests (For Microservices)
Create `aidlc-docs/construction/build-and-test/contract-test-instructions.md`:
- API contract validation between services
- Consumer-driven contract testing
- Schema validation

### Security Tests
Create `aidlc-docs/construction/build-and-test/security-test-instructions.md`:
- Vulnerability scanning
- Dependency security checks
- Authentication/authorization testing
- Input validation testing

### End-to-End Tests
Create `aidlc-docs/construction/build-and-test/e2e-test-instructions.md`:
- Complete user workflow testing
- Cross-service scenarios
- UI testing (if applicable)

---

## Step 7: Generate Test Summary

Create `aidlc-docs/construction/build-and-test/build-and-test-summary.md`:

```markdown
# Build and Test Summary

## Build Status
- **Build Tool**: [Tool name]
- **Build Status**: [Success/Failed]
- **Build Artifacts**: [List artifacts]
- **Build Time**: [Duration]

## Test Execution Summary

### Unit Tests
- **Total Tests**: [X]
- **Passed**: [X]
- **Failed**: [X]
- **Coverage**: [X]%
- **Status**: [Pass/Fail]

### Integration Tests
- **Test Scenarios**: [X]
- **Passed**: [X]
- **Failed**: [X]
- **Status**: [Pass/Fail]

### Performance Tests
- **Response Time**: [Actual] (Target: [Expected])
- **Throughput**: [Actual] (Target: [Expected])
- **Error Rate**: [Actual] (Target: [Expected])
- **Status**: [Pass/Fail]

### Additional Tests
- **Contract Tests**: [Pass/Fail/N/A]
- **Security Tests**: [Pass/Fail/N/A]
- **E2E Tests**: [Pass/Fail/N/A]

## Overall Status
- **Build**: [Success/Failed]
- **All Tests**: [Pass/Fail]
- **Ready for Operations**: [Yes/No]

## Next Steps
[If all pass]: Ready to proceed to Operations phase for deployment planning
[If failures]: Address failing tests and rebuild
```

---

## Step 7.5: Post-Merge Guide (CONDITIONAL — user-facing / real-usage changes)

The build-and-test summary covers how to verify the code **in the worktree before merge**. It does
NOT tell the user what to expect **once it lands on the prod branch**, or how to sanity-check it in
**real usage** (live data, the running daemon, actual user workflows). For any change a person will
observe in production, write that guide.

**Execute IF** the change is user-facing or has real-usage behavior worth verifying after merge:
- new/changed runtime behavior the operator or end-user will see (new tools, prompts, UI, signals,
  scheduled jobs, external-API integrations),
- new config knobs or env keys the user must set or may tune,
- anything whose correctness depends on live data / external services (so worktree tests with fakes
  can't fully prove it).

**Skip IF** purely internal with no observable prod effect (refactor, test-only, docs, infra-neutral
cleanup) — note the skip in `state.md`.

**Create `aidlc-docs/tracks/<id>/post-merge-guide.md`** covering:
1. **무엇이 바뀌나 (prod 기대 동작)** — 머지 후 프로드에서 달라지는 동작을 한 줄 요약 + 구체.
2. **전제/활성 조건** — 데몬 재기동 필요 여부, 새 env 키(`.env`)·config 블록, 기본 on/off 상태.
   - **F43 자동 재시작 표준 공지 (모든 코드-변경 트랙 공통, R10 critic 발견)**: "데몬 재시작
     불필요"라고 쓰지 말 것 — **어떤 머지든 HEAD SHA가 바뀌므로 F43 버전-스큐 자가치유가 다음
     콘솔 attach 시 데몬을 1회 자동 재시작한다**(`operator-console/launcher/daemon.ts`
     `detectCodeSkew()` → 무조건 restart). 가이드에는 "코드 동작 불변이어도 다음 attach 시 1회
     자동 재시작은 정상(F43)"을 명시하고, in-flight 턴 중이면 attach를 턴 사이로 미루라고 안내.
3. **실사용 확인 체크리스트** — 운영자가 실제로 눌러볼 순서(스모크 명령, 어디를 보면 되는지:
   로그/콘솔/산출 파일), 무엇이 "정상"인지(기대 출력)와 fail-honest 시 신호.
   **로그 문구는 코드에서 실제 문자열을 인용**(추측 금지 — R10 critic: "wrote N rows"류 가공
   문구가 실제 `{symbol}: N sessions`와 불일치했던 사례).
4. **튜닝 노브** — `config/...`에서 조정 가능한 값과 의미(시드 기본값 포함).
5. **롤백/비활성** — 부분/완전 비활성 방법(예: `enabled: false`, 소스 토글, 머지 revert).
   **revert 명령은 `git revert -m 1 <merge-sha>`로 적을 것** — `/ai-dlc-merge`는 `--no-ff`
   merge commit이라 `-m 1` 없이는 git이 거부한다(R10 critic 발견).
6. **알려진 한계 / 범위 밖** — 이번 트랙이 커버하지 **않는** 것(후속 트랙 후보) — 기대치 오정렬 방지.

가능하면 worktree에서 **실데이터 라이브 스모크를 1회** 돌려(외부 연동은 fake 테스트가 못 잡는다)
그 결과를 가이드의 검증 상태에 적어둔다. 이 문서는 머지 후에도 `tracks/<id>/`에 남아 운영자의
실사용 검증 길잡이가 된다.

---

## Step 8: Update State Tracking + enqueue for merge

> **Partition model (see `common/concurrent-tracks.md`)**: progress lives in the track's own
> `aidlc-docs/tracks/<id>/state.md` (single writer), NOT the root `aidlc-state.md` (that is the
> Track Registry only). Update the per-track file here.

Update `aidlc-docs/tracks/<id>/state.md`:
- Mark the Build and Test stage checkbox as complete (`[x]`), with the actual test results
  (suite counts / pass-fail) recorded.
- **If Build & Test PASSED (all green): set the track's `**Status**:` to `merge-awaiting`** to
  enqueue this track for `/ai-dlc-merge`. This is the standard hand-off — a green Build & Test
  means the track is ready to merge, so the queue should see it without a separate manual step.
  - Leave the **root Track Registry row** as `active` — `/ai-dlc-merge` flips it to `merged` only
    at actual merge time (that command is the single writer of the registry/global audit).
  - If Build & Test did **not** pass, keep `**Status**: active` and do not enqueue; fix and rerun.
  - This only *enqueues*; `/ai-dlc-merge` still has its own approval gate before any merge, so
    setting `merge-awaiting` here cannot cause a premature merge.

> **`merge-awaiting` is provisional — revert it the moment work resumes.** If a track sitting at
> `merge-awaiting` gets ANY further work — more implementation, a `/code-review` or `/critic` round
> that produces fixes, a design change, a follow-up request — it is no longer "done and ready". The
> agent doing that work MUST flip the track's `state.md` `**Status**:` back to **`active`** BEFORE
> making changes, and only re-set `merge-awaiting` after Build & Test is green again. New commits
> alone do NOT un-enqueue a track — only the Status flag does, and `/ai-dlc-merge` reads that flag —
> so leaving it `merge-awaiting` while editing risks the orchestrator merging a half-finished track.
> (See `common/concurrent-tracks.md` → merge-awaiting lifecycle.)

---

## Step 9: Present Results to User

Present completion message in this structure:
     1. **Completion Announcement** (mandatory): Always start with this:

```markdown
# 🔨 Build and Test Complete
```

     2. **AI Summary** (optional): Provide structured bullet-point summary of build and test results
        - Format: "Build and test has completed with the following results:"
        - List build status and artifacts
        - List test results by category (unit, integration, performance, etc.)
        - List generated instruction files
        - DO NOT include workflow instructions ("please review", "let me know", "proceed to next phase", "before we proceed")
        - Keep factual and content-focused
     3. **Formatted Workflow Message** (mandatory): Always end with this exact format:

```markdown
> **📋 <u>**REVIEW REQUIRED:**</u>**  
> Please examine the build and test summary at: `aidlc-docs/construction/build-and-test/build-and-test-summary.md`



> **🚀 <u>**WHAT'S NEXT?**</u>**
>
> **You may:**
>
> 🔧 **Request Changes** - Ask for modifications to the build and test instructions based on your review
> ✅ **Approve & Continue** - Approve build and test results. On approval, if all tests passed the
>   track's `state.md` Status is set to **`merge-awaiting`** (enqueued for `/ai-dlc-merge`); the
>   Operations phase remains a placeholder.

---
```

---

## Step 10: Log Interaction

**MANDATORY**: Log the stage completion in the track's `audit.md` (`aidlc-docs/tracks/<id>/audit.md`):

```markdown
## Build and Test Stage
**Timestamp**: [ISO timestamp]
**Build Status**: [Success/Failed]
**Test Status**: [Pass/Fail]
**Files Generated**:
- build-instructions.md
- unit-test-instructions.md
- integration-test-instructions.md
- performance-test-instructions.md
- build-and-test-summary.md
- post-merge-guide.md (if user-facing / real-usage change — `tracks/<id>/post-merge-guide.md`)

---
```
