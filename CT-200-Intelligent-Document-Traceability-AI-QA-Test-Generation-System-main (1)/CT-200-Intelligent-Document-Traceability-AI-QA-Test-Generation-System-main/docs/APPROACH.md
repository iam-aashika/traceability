# CT-200 Intelligent Document Traceability & AI-Powered QA Test Generation System
## System Architecture, Engineering Approach, and Technical Decision Log

---

## 1. Executive Overview & Problem Context

In medical device software engineering (regulated under FDA 21 CFR Part 820, ISO 13485, and IEC 62304), **traceability** is a mandatory regulatory pillar: every software requirement must link to concrete verification test cases, and changes in source specifications must immediately trigger risk assessment and test case re-verification.

A silent and dangerous failure mode in regulated devices is **stale traceability**: when an engineering or regulatory specification is updated (e.g. reducing cuff deflation timeout from 2.0s to 1.5s, or reducing battery warning thresholds), existing test cases may continue passing obsolete criteria without flagging that the underlying specification changed.

This system delivers an end-to-end, production-grade backend platform that:
1. Forensically parses and reconstructs the document hierarchy of the CardioTrack CT-200 blood pressure monitor manuals (`v1` and `v2`) directly from PDF.
2. Ingests revisions without destroying historical data, assigning deterministic logical node IDs and SHA-256 content hashes.
3. Provides version-pinned requirement selections that freeze exact text snapshots.
4. Generates structured, FDA/ISO 13485-compliant QA test cases using LLMs, validated through strict Pydantic schemas.
5. Employs a multi-tier staleness and impact detection engine at retrieval time to differentiate between benign wording tweaks, critical numerical threshold shifts, error code modifications, and safety constraint alterations.

---

## 2. System Architecture & Component Design

The platform follows a clean, modular service-oriented architecture:

```
                                  [ PDF Manuals (v1 / v2) ]
                                              │
                                              ▼
                                 ┌─────────────────────────┐
                                 │     PDFInspector &      │
                                 │      PDFExtractor       │
                                 │  (NFKD Ligature Normal) │
                                 └────────────┬────────────┘
                                              │ Raw Section Items & Tables
                                              ▼
                                 ┌─────────────────────────┐
                                 │    HierarchyBuilder     │
                                 │   (Stack-Based Tree)    │
                                 └────────────┬────────────┘
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      ▼                                               ▼
         ┌─────────────────────────┐                     ┌─────────────────────────┐
         │     SQLite Database     │                     │     NoSQL Store         │
         │  (SQLAlchemy ORM)       │                     │  (JsonDocumentStore)    │
         │                         │                     │                         │
         │  * documents            │                     │  * storage/generations/ │
         │  * document_versions    │                     │    {gen_id}.json        │
         │  * sections             │                     │  * Immutable historical │
         │  * selections           │                     │    test generations     │
         └────────────┬────────────┘                     └────────────▲────────────┘
                      │                                               │
                      ▼                                               │
         ┌─────────────────────────┐                                  │
         │     VersionService &    │                                  │
         │       DiffService       │                                  │
         └────────────┬────────────┘                                  │
                      │                                               │
                      ├───────────────────────┐                       │
                      ▼                       ▼                       │
         ┌─────────────────────────┐ ┌─────────────────┐              │
         │    StalenessService     │ │   LLMService    │──────────────┘
         │ (Retrieval Impact Eval) │ │ (Pydantic Retry)│
         └────────────┬────────────┘ └─────────────────┘
                      │
                      ▼
         ┌─────────────────────────┐
         │     FastAPI Layer       │
         │  /api/documents         │
         │  /api/sections          │
         │  /api/selections        │
         │  /api/generations       │
         └─────────────────────────┘
```

---

## 3. Database Design & Data Model

### 3.1 Relational Schema (SQLite + SQLAlchemy)
- **`documents`**:
  - `id` (PK, string, e.g. `doc_ct200`)
  - `title` (string)
  - `description` (string)
  - `created_at`, `updated_at` (timestamps)
- **`document_versions`**:
  - `id` (PK, string, e.g. `ver_doc_ct200_v1`)
  - `document_id` (FK -> `documents.id`)
  - `version_number` (integer: 1, 2, ...)
  - `version_label` (string: `v1.0`, `v2.0`)
  - `filename` (string)
  - `file_hash` (SHA-256 of the raw PDF file bytes)
  - `total_pages` (integer)
  - `created_at` (timestamp)
- **`sections`**:
  - `id` (PK, string: `{version_id}_{logical_node_id}`)
  - `logical_node_id` (string: indexed, stable across versions, e.g. `sec_3_2_cuff_inflation_sequence`)
  - `document_id` (FK -> `documents.id`)
  - `version_id` (FK -> `document_versions.id`)
  - `section_number` (string, e.g. `"3.2"`)
  - `heading` (string, e.g. `"Cuff Inflation Sequence"`)
  - `level` (integer: 1 for L1 root, 2 for subsection, etc.)
  - `parent_id` (FK -> `sections.id`, self-referencing hierarchy)
  - `order_index` (integer: physical document layout sequence)
  - `path` (string, e.g. `"/3/3.2"`)
  - `body_text` (text: section content excluding sub-sections)
  - `full_text` (text: heading + body)
  - `content_hash` (string: SHA-256 of normalized heading + body)
  - `page_start`, `page_end` (integers)
  - `has_table` (boolean)
  - `table_data` (JSON text)
  - `extraction_confidence` (float)
  - `extraction_warnings` (JSON string list)
- **`selections`**:
  - `id` (PK, string, e.g. `sel_...`)
  - `selection_name` (string)
  - `document_id` (FK -> `documents.id`)
  - `version_id` (FK -> `document_versions.id`)
  - `node_ids` (JSON string list)
  - `logical_node_ids` (JSON string list)
  - `source_snapshots` (JSON string map: frozen copy of text, headings, and hashes at selection creation)
  - `created_at` (timestamp)

### 3.2 NoSQL Storage (JsonDocumentStore)
Generated QA test cases and execution metadata are stored as immutable JSON documents in `storage/generations/{generation_id}.json` with indexing by `selection_id` and `node_id`. This guarantees:
1. Zero runtime dependency on external databases (MongoDB daemon setup not required in test environments).
2. Complete auditability: historical test generations are immutable records that never overwrite earlier runs.
3. Preserved snapshots: test cases remain linked to the exact text and content hash they were created against.

---

## 4. PDF Inspection Findings & Extraction Engineering

A deep pre-implementation inspection revealed that the CT-200 manual cannot be parsed by naive text dump scripts:

### 4.1 Unicode Ligature Pitfall
- **Discovery**: Nimbus fonts embedded in the PDF use standard ligatures (`\ufb00` for `ff`, `\ufb01` for `fi`, `\ufb02` for `fl`).
- **Initial Failure**: Windows console output failed with `UnicodeEncodeError: 'charmap' codec can't encode character '\ufb01'`, and string searches for `"Cuff"` or `"Inflation"` failed.
- **Fix**: Implemented Unicode `NFKD` normalization in `app/utils/normalization.py`. NFKD decomposes ligatures into their constituent ASCII characters (`fi` -> `f` + `i`), ensuring uniform hashing and search indexing.

### 4.2 False-Positive Heading Triggers (Numbered Lists)
- **Discovery**: Under `3.3 Result Display and Classification`, clinical criteria are formatted as:
  `1. Normal: systolic < 120 and diastolic < 80`
  `2. Elevated: systolic 120-129 and diastolic < 80`
  `3. Hypertension Stage 1: ...`
- **Initial Failure**: Naive heading regex `r"^\d+\."` misclassified these list items as 5 distinct Level 1 root sections (`1`, `2`, `3`, `4`, `5`), creating 5 spurious root nodes and gutting the body text of `3.3`.
- **Debugging & Fix**: Analyzed font dictionaries. Real Level 1 headings are `16.5pt Bold` (`NimbusSans-Bold`). Real Level 2 headings are `12.9pt Bold` (or `11.0pt Bold` for `3.2`). These list items were `11.0pt Regular` (`NimbusSans-Regular`, flags=4). We updated `PDFExtractor` to require bold flags (`flags & 16` or `"bold"` in font name) or font size >= 12.0pt. Consequently, list items remain in the body text of `3.3`.

### 4.3 Multi-Column Tables
- **Discovery**: Tables exist on Page 2 (`General Specifications`) and Page 4 (`Error Codes`). In PyMuPDF text block reading, column blocks are read in arbitrary coordinate order, causing cell texts to interleave.
- **Fix**: Integrated PyMuPDF `find_tables()` to detect table bounding boxes, extract clean 2D row/column data, format them into GitHub-flavored Markdown tables within `body_text`, and attach the structured matrix as `table_data`.

---

## 5. Hierarchy Reconstruction Decisions

The hierarchy builder (`app/services/hierarchy_builder.py`) resolves document structure using a stack-based algorithm:

### 5.1 Disambiguating Duplicate Headings
- **Case**: `4.2 Error Codes` (under `4. Alarms and Safety Behavior`) vs. `7.1 Error Codes` (under `7. Troubleshooting`).
- **Decision**: Node uniqueness and logical identity must never rely on heading text alone.
- **Implementation**:
  - Logical node IDs incorporate canonical section numbers and parent paths:
    `sec_4_2_error_codes` vs. `sec_7_1_error_codes`.
  - Version-specific primary keys: `ver_v1_sec_4_2_error_codes` vs. `ver_v1_sec_7_1_error_codes`.
  - Parent pointers: `parent_id` points to `4` for `4.2`, and to `7` for `7.1`.

### 5.2 Out-of-Order Section Numbering
- **Case**: On Page 3, `3.2 Cuff Inflation Sequence` is followed by `3.4 Auto Shutoff`, which is followed by `3.3 Result Display and Classification`.
- **Decision**: Monotonic numbering assumptions are invalid in real-world regulatory documents.
- **Implementation**: The parser uses section prefix depth (both `3.4` and `3.3` have prefix `3`), attaching both to Section `3` while preserving their physical document reading order (`order_index`).

### 5.3 Skipped Hierarchy Levels
- **Case**: `2. Physical and Electrical Specifications` (L1) -> `2.1 General Specifications` (L2) -> `2.1.1.1 Battery Life Under Typical Use` (L4). No `2.1.1` exists.
- **Decision**: Do not crash or discard the node.
- **Implementation**: Stack unwinding matches the longest available prefix (`2.1`), attaches `2.1.1.1` directly to `2.1`, and records an explicit extraction warning in `extraction_warnings`.

---

## 6. Document Versioning & Matching Strategy

When re-ingesting a new revision (`v2`):
1. **Preservation**: Historical `v1` records, selections, and generations are strictly preserved.
2. **Multi-Stage Matching Pipeline**:
   - **Stage 1 (Primary)**: Match by stable `logical_node_id` (derived from canonical section number + heading slug).
   - **Stage 2 (Path)**: If logical ID shifted, match by identical hierarchical path (`path`).
   - **Stage 3 (Fuzzy Heading)**: If section was renumbered, match by fuzzy heading similarity (`difflib.SequenceMatcher >= 0.85`) within the same hierarchy level.
   - **Stage 4 (Content Similarity)**: Match by high body text similarity (`>= 0.80`) to capture renumbering of unchanged paragraphs.
3. **Change Classification**:
   - `UNCHANGED`: Content hash and structural path match exactly.
   - `MODIFIED`: Same logical node exists, but content hash differs.
   - `MOVED`: Content hash matches, but structural path or parent shifted.
   - `ADDED`: Exists in new version, absent in old version (e.g. `5.3 Data Export`).
   - `REMOVED`: Exists in old version, absent in new version.
   - `REVIEW_REQUIRED`: Fuzzy match confidence between 0.80 and 0.85.

---

## 7. Version-Pinned Selections

To prevent the common regulatory flaw where a selection silently re-resolves to whatever is currently the latest version of a document:
- When `POST /api/selections` is invoked, the request specifies `document_id`, `version_id`, and `node_ids`.
- The system validates that all selected nodes belong strictly to the specified `version_id`.
- The system captures a frozen snapshot of the exact node heading, body text, path, and `content_hash` into `source_snapshots`.
- If the document is later re-ingested with `v2`, the selection remains immutable, continuing to reference the exact `v1` content it was created against.

---

## 8. LLM Prompt Design, Structured Output & Duplicate Policy

### 8.1 Prompt Engineering & Grounding Rules
The system prompt establishes the persona of a Senior Medical Device QA Automation and Regulatory Traceability Engineer (IEC 80601-2-30 / ISO 81060-2 compliance).
Strict negative constraints are enforced:
- Rely exclusively on provided text; never invent numerical limits, timing, error codes, or unstated behaviors.
- Formulate concrete, repeatable test steps and explicit expected results.
- Explicitly cite source node IDs and exact requirement statements.

### 8.2 Pydantic Validation & Retries
- Output is validated against the `TestCaseCollection` Pydantic model:
  - Exact count between 3 and 5 test cases.
  - Priority validated against `{Critical, High, Medium, Low}`.
  - Test type validated against `{Functional, Boundary, Safety, Error-Handling, Negative}`.
  - Non-empty steps, objectives, and expected results.
- Robust JSON extraction handles markdown fences (````json ... ````) and embedded whitespace.
- Retry loop attempts regeneration up to `MAX_RETRIES` (default: 3) upon parsing or validation failure.

### 8.3 Duplicate Generation Policy
- When `POST /api/generations/{selection_id}` is submitted:
  - Default (`force_regenerate=false`): The system checks the NoSQL document store for an existing successful generation for this `selection_id`. If present, it reuses and returns the existing generation with `was_cached=true`.
  - Force mode (`force_regenerate=true`): The system generates a new independent generation record with a new `generation_id`, preserving both generations in history without overwriting.

---

## 9. Staleness and Impact Detection Engine

Staleness evaluation is performed **dynamically at retrieval time** (`GET /api/generations/{generation_id}`), ensuring historical generation records remain immutable while presenting up-to-date compliance status.

### 9.1 Multi-Tier Impact Analysis
When comparing a frozen source snapshot against the corresponding node in the latest document version:
1. **Hash Equality**: If `original_hash == latest_node.content_hash` -> **`CURRENT`** (`NONE`).
2. **Numerical & Timing Analysis**:
   - Uses regex extraction for numbers with medical/engineering units (`mmHg`, `bpm`, `cm`, `seconds`, `minutes`, `%`, `cycles`, `V`, `AA`).
   - If numbers differ (e.g. `40 mmHg` -> `30 mmHg`, `300` -> `250 cycles`, `15%` -> `10%`, `2s` -> `1.5s`):
     -> **`STALE`** (`NUMERICAL_THRESHOLD`).
     -> Recommendation: High-priority manual update required.
3. **Error Code Analysis**:
   - Detects alterations in error code definitions (e.g. `E1`–`E5` updated to `E1`–`E6`):
     -> **`STALE`** (`ERROR_CODE`).
4. **Safety & Negation Constraints**:
   - Detects changes in safety condition words (`not`, `never`, `cannot`, `prohibited`, `mandatory`, `abort`, `halt`, `emergency`):
     -> **`STALE`** (`SAFETY_BEHAVIOR`).
5. **Textual Wording Shift**:
   - If text changed but no numerical or error code alteration occurred:
     -> **`REVIEW_REQUIRED`** (`TEXT_MODIFIED`).
     -> Conservative principle: We never claim that semantic similarity proves clinical safety. A human QA engineer must review the diff.
6. **Node Deletion**:
   - If the logical node is absent in the latest version:
     -> **`SOURCE_REMOVED`** (`DELETED`).

---

## 10. Mandatory Decision Log

### Question 1: What is the one part of this system most likely to silently give wrong results without erroring? How would you catch it?
**Answer**:
The heading detection heuristic when encountering unnumbered, stylized callouts or safety warnings (e.g. bolded warnings like "WARNING: Do not submerge device in water"). Because the parser combines bold flags (`flags & 16`) with line-level formatting to detect headings, a stylized warning paragraph that happens to be bolded on its own line could be misidentified as a new section heading rather than body text, silently altering the hierarchy and parentage of following paragraphs without throwing any code exception.
**How to catch it**:
I would catch this by running an automated **Hierarchy Continuity & Anomaly Scanner** in CI that flags any detected heading lacking a standard section number or whose text matches standard regulatory safety alert keywords (`WARNING`, `CAUTION`, `NOTE`, `DANGER`), ensuring such lines are categorized as callout blocks rather than structural heading nodes.

### Question 2: Where did you choose simplicity over correctness because of time, and what would break first if this went to production as-is?
**Answer**:
In table boundary association inside `app/services/pdf_extractor.py`. Currently, the extractor uses PyMuPDF's `find_tables()` and assigns all tables on a page to whichever section is currently active when the table's vertical coordinates are crossed.
**What would break first in production**:
If a single page contains multiple distinct subsections and multiple small tables positioned side-by-side or closely packed, or if a table spans across a page break where the new page starts with a brand new heading before the table finishes, the table rows would be prematurely cut off or incorrectly attached to the succeeding section rather than the preceding section.

### Question 3: Name one input (to your parser, your versioning matcher, or your LLM call) that you did not handle, and what your system does when it sees it.
**Answer**:
**Input**: A scanned PDF page where text is embedded entirely within a vector drawing diagram (e.g. an electrical schematic or pneumatic flow chart with vector text paths rather than standard font glyphs or raster images).
**System Behavior**: The extractor detects that the page has zero raster images (`len(page.get_images()) == 0`) and zero selectable font spans (`len(page.get_text()) == 0`). As a result, it does not trigger the raster OCR fallback (`is_scanned_page` returns `False`), treats the page as empty body text, records an extraction warning, and moves to the next page, silently omitting the text inside the vector diagram.

---

## 11. Known Limitations & Production Roadmap

1. **Vector Drawing Text OCR**: Render all pages to high-resolution raster images for Tesseract OCR whenever extracted character count falls below 50 characters, regardless of whether PyMuPDF reports image objects.
2. **Multi-Page Table Stitching**: Implement cross-page table continuation detection when column counts and header signatures match across consecutive page boundaries.
3. **Async Generation Queue**: Offload external LLM API calls to Celery/Redis task queues with webhook notifications for high-throughput enterprise environments.
4. **FDA Audit Trail Export**: Add automated generation of 21 CFR Part 11 compliant audit logs detailing who approved requirement changes and when test cases were acknowledged as updated.
