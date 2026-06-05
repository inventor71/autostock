# Reverse Engineering

**Purpose**: Analyze existing codebase and generate comprehensive design artifacts

**Execute when**: Brownfield project detected (existing code found in workspace)

**Skip when**: Greenfield project (no existing code)

**Rerun behavior**: Rerun is controlled by workspace-detection.md. If existing reverse engineering artifacts are found and are still current, they are loaded and reverse engineering is skipped. If artifacts are stale (older than the codebase's last significant modification) or the user explicitly requests a rerun, reverse engineering executes again to ensure artifacts reflect current code state

## Step 0: Check CodeKB Bootstrap Status

Before starting RE analysis, check whether the shared CodeKB exists (see `common/codekb.md`):

1. Check if `aidlc-docs/codekb/codekb-state.md` exists:
   - **CodeKB exists**: Read `codekb-state.md` to get the last-known SHA. Load CodeKB artifacts (`summary.md`, `architecture.md`, `integration-map.md`, `domain-entities.md`) as baseline context for the current codebase. Use this to focus per-track RE on areas that changed or are relevant to this track — don't re-analyze what CodeKB already covers. Record CodeKB status in track's `state.md`.
   - **CodeKB absent**: This track is the first. It will do full RE and bootstrap CodeKB upon completion (Step 12a). Record "CodeKB will be bootstrapped" in track's `state.md`.

2. Record in track's `state.md`:
   ```markdown
   ## CodeKB Status
   - **CodeKB exists**: [Yes/No]
   - **CodeKB SHA**: [sha or "N/A"]
   - **Current HEAD**: [sha]
   - **Bootstrap needed**: [Yes/No]
   ```

## Step 1: Multi-Package Discovery

### 1.1 Scan Workspace
- All packages (not just mentioned ones)
- Package relationships via config files
- Package types: Application, CDK/Infrastructure, Models, Clients, Tests

### 1.2 Understand the Business Context
- The core business that the system is implementing overall
- The business overview of every package
- List of Business Transactions that are implemented in the system

### 1.3 Infrastructure Discovery
- CDK packages (package.json with CDK dependencies)
- Terraform (.tf files)
- CloudFormation (.yaml/.json templates)
- Deployment scripts

### 1.4 Build System Discovery
- Build systems: Brazil, Maven, Gradle, npm
- Config files for build-system declarations
- Build dependencies between packages

### 1.5 Service Architecture Discovery
- Lambda functions (handlers, triggers)
- Container services (Docker/ECS configs)
- API definitions (Smithy models, OpenAPI specs)
- Data stores (DynamoDB, S3, etc.)

### 1.6 Code Quality Analysis
- Programming languages and frameworks
- Test coverage indicators
- Linting configurations
- CI/CD pipelines

## Step 2: Generate Business Overview Documentation

Create `aidlc-docs/tracks/<id>/inception/reverse-engineering/business-overview.md`:

```markdown
# Business Overview

## Business Context Diagram
[Mermaid diagram showing the Business Context]

## Business Description
- **Business Description**: [Overall Business description of what the system does]
- **Business Transactions**: [List of Business Transactions that the system implements and their descriptions]
- **Business Dictionary**: [Business dictionary terms that the system follows and their meaning]

## Component Level Business Descriptions
### [Package/Component Name]
- **Purpose**: [What it does from the business perspective]
- **Responsibilities**: [Key responsibilities]
```

## Step 3: Generate Architecture Documentation

Create `aidlc-docs/tracks/<id>/inception/reverse-engineering/architecture.md`:

```markdown
# System Architecture

## System Overview
[High-level description of the system]

## Architecture Diagram
[Mermaid diagram showing all packages, services, data stores, relationships]

## Component Descriptions
### [Package/Component Name]
- **Purpose**: [What it does]
- **Responsibilities**: [Key responsibilities]
- **Dependencies**: [What it depends on]
- **Type**: [Application/Infrastructure/Model/Client/Test]

## Data Flow
[Mermaid sequence diagram of key workflows]

## Integration Points
- **External APIs**: [List with purposes]
- **Databases**: [List with purposes]
- **Third-party Services**: [List with purposes]

## Infrastructure Components
- **CDK Stacks**: [List with purposes]
- **Deployment Model**: [Description]
- **Networking**: [VPC, subnets, security groups]
```

## Step 4: Generate Code Structure Documentation

Create `aidlc-docs/tracks/<id>/inception/reverse-engineering/code-structure.md`:

```markdown
# Code Structure

## Build System
- **Type**: [Maven/Gradle/npm/Brazil]
- **Configuration**: [Key build files and settings]

## Key Classes/Modules
[Mermaid class diagram or module hierarchy]

### Existing Files Inventory
[List all source files with their purposes - these are candidates for modification in brownfield projects]

**Example format**:
- `[path/to/file]` - [Purpose/responsibility]

## Design Patterns
### [Pattern Name]
- **Location**: [Where used]
- **Purpose**: [Why used]
- **Implementation**: [How implemented]

## Critical Dependencies
### [Dependency Name]
- **Version**: [Version number]
- **Usage**: [How and where used]
- **Purpose**: [Why needed]
```

## Step 5: Generate API Documentation

Create `aidlc-docs/tracks/<id>/inception/reverse-engineering/api-documentation.md`:

```markdown
# API Documentation

## REST APIs
### [Endpoint Name]
- **Method**: [GET/POST/PUT/DELETE]
- **Path**: [/api/path]
- **Purpose**: [What it does]
- **Request**: [Request format]
- **Response**: [Response format]

## Internal APIs
### [Interface/Class Name]
- **Methods**: [List with signatures]
- **Parameters**: [Parameter descriptions]
- **Return Types**: [Return type descriptions]

## Data Models
### [Model Name]
- **Fields**: [Field descriptions]
- **Relationships**: [Related models]
- **Validation**: [Validation rules]
```

## Step 6: Generate Component Inventory

Create `aidlc-docs/tracks/<id>/inception/reverse-engineering/component-inventory.md`:

```markdown
# Component Inventory

## Application Packages
- [Package name] - [Purpose]

## Infrastructure Packages
- [Package name] - [CDK/Terraform] - [Purpose]

## Shared Packages
- [Package name] - [Models/Utilities/Clients] - [Purpose]

## Test Packages
- [Package name] - [Integration/Load/Unit] - [Purpose]

## Total Count
- **Total Packages**: [Number]
- **Application**: [Number]
- **Infrastructure**: [Number]
- **Shared**: [Number]
- **Test**: [Number]
```

## Step 7: Generate Technology Stack Documentation

Create `aidlc-docs/tracks/<id>/inception/reverse-engineering/technology-stack.md`:

```markdown
# Technology Stack

## Programming Languages
- [Language] - [Version] - [Usage]

## Frameworks
- [Framework] - [Version] - [Purpose]

## Infrastructure
- [Service] - [Purpose]

## Build Tools
- [Tool] - [Version] - [Purpose]

## Testing Tools
- [Tool] - [Version] - [Purpose]
```

## Step 8: Generate Dependencies Documentation

Create `aidlc-docs/tracks/<id>/inception/reverse-engineering/dependencies.md`:

```markdown
# Dependencies

## Internal Dependencies
[Mermaid diagram showing package dependencies]

### [Package A] depends on [Package B]
- **Type**: [Compile/Runtime/Test]
- **Reason**: [Why dependency exists]

## External Dependencies
### [Dependency Name]
- **Version**: [Version]
- **Purpose**: [Why used]
- **License**: [License type]
```

## Step 9: Generate Code Quality Assessment

Create `aidlc-docs/tracks/<id>/inception/reverse-engineering/code-quality-assessment.md`:

```markdown
# Code Quality Assessment

## Test Coverage
- **Overall**: [Percentage or Good/Fair/Poor/None]
- **Unit Tests**: [Status]
- **Integration Tests**: [Status]

## Code Quality Indicators
- **Linting**: [Configured/Not configured]
- **Code Style**: [Consistent/Inconsistent]
- **Documentation**: [Good/Fair/Poor]

## Technical Debt
- [Issue description and location]

## Patterns and Anti-patterns
- **Good Patterns**: [List]
- **Anti-patterns**: [List with locations]
```

## Step 10: Create Timestamp File

Create `aidlc-docs/tracks/<id>/inception/reverse-engineering/reverse-engineering-timestamp.md`:

```markdown
# Reverse Engineering Metadata

**Analysis Date**: [ISO timestamp]
**Analyzer**: AI-DLC
**Workspace**: [Workspace path]
**Total Files Analyzed**: [Number]

## Artifacts Generated
- [x] architecture.md
- [x] code-structure.md
- [x] api-documentation.md
- [x] component-inventory.md
- [x] technology-stack.md
- [x] dependencies.md
- [x] code-quality-assessment.md
```

## Step 11: Update State Tracking

Update the track's `state.md` (`aidlc-docs/tracks/<id>/state.md`):

```markdown
## Reverse Engineering Status
- [x] Reverse Engineering - Completed on [timestamp]
- **Artifacts Location**: aidlc-docs/tracks/<id>/inception/reverse-engineering/
```

## Step 12: Present Completion Message to User

```markdown
# 🔍 Reverse Engineering Complete

[AI-generated summary of key findings from analysis in the form of bullet points]

> **📋 <u>**REVIEW REQUIRED:**</u>**  
> Please examine the reverse engineering artifacts at: `aidlc-docs/tracks/<id>/inception/reverse-engineering/`

> **🚀 <u>**WHAT'S NEXT?**</u>**
>
> **You may:**
>
> 🔧 **Request Changes** - Ask for modifications to the reverse engineering analysis if required
> ✅ **Approve & Continue** - Approve analysis and proceed to **Requirements Analysis**
```

## Step 12a: Bootstrap CodeKB (only if CodeKB was absent at Step 0)

**Execute ONLY if `aidlc-docs/codekb/codekb-state.md` did not exist when Step 0 ran.**

This is the one-time seed — after this track merges and CI fires, CI becomes the sole CodeKB writer (see `common/codekb.md`).

Using the per-track RE artifacts just produced, synthesize the shared CodeKB:

1. Read the per-track RE artifacts at `aidlc-docs/tracks/<id>/inception/reverse-engineering/`.

2. Create the `aidlc-docs/codekb/` directory structure.

3. Synthesize each CodeKB file from the RE artifacts, following the schema in `common/codekb.md`:
   - `summary.md`: Distill from `business-overview.md` + `architecture.md` — high-level one-page summary.
   - `architecture.md`: Adapt from per-track `architecture.md` — system-level view, not track-specific.
   - `integration-map.md`: Extract external integrations from `api-documentation.md` + `dependencies.md`.
   - `domain-entities.md`: Extract key data models/entities from `code-structure.md` + `api-documentation.md`.
   - `business-rules.md`: Extract business logic patterns from `business-overview.md`.
   - `nfr-design.md`: Note NFR patterns observable in the codebase from `code-quality-assessment.md` + `technology-stack.md`.
   - `infrastructure-design.md`: Adapt infrastructure/deployment info from `component-inventory.md`.
   - `codekb-state.md`: Create with:
     - Last Commit SHA: current `HEAD`
     - Last Refresh: now (ISO 8601)
     - Refreshed By: `track/<id>`
     - Schema Version: `1`

4. Commit CodeKB files to this track's branch. They travel with the track and land on `main` when this track merges.

5. Record in track's `state.md`:
   ```markdown
   ## CodeKB Bootstrap
   - [x] CodeKB bootstrapped by this track
   - **Bootstrap SHA**: `<sha>`
   - **Bootstrap Date**: `<ISO 8601>`
   ```

After this track merges and the first CI run fires, CI will overwrite CodeKB with a fresh RE and become the sole writer.

## Step 13: Wait for User Approval

- **MANDATORY**: Do not proceed until user explicitly approves
- **MANDATORY**: Log user's response in the track's `audit.md` with complete raw input
