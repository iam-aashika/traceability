# CT-200 Technical Manual PDF Inspection & Engineering Analysis Report

## 1. Executive Summary

A comprehensive forensic inspection was performed on both technical manual revisions provided for the CardioTrack CT-200 Home Blood Pressure Monitor:
- **Revision 1**: `data/ct200_manual_v1.pdf` (6 pages, 443,032 bytes)
- **Revision 2**: `data/ct200_manual_v2.pdf` (7 pages, 447,477 bytes)

The documents represent technical, regulatory-style medical device documentation. Rather than clean synthetic data, these PDFs contain distinct structural anomalies, typographical nuances, embedded tables, and cross-page text flows that fail generic PDF extraction scripts.

---

## 2. Document Profile & Technical Characteristics

| Metric / Attribute | CT-200 Manual v1 | CT-200 Manual v2 | Notes |
| :--- | :--- | :--- | :--- |
| **Total Pages** | 6 | 7 | Revision 2 expands to page 7 due to content additions |
| **Primary Typography** | `NimbusSans-Regular`, `NimbusSans-Bold` | `NimbusSans-Regular`, `NimbusSans-Bold` | 11.0pt body, 12.9pt L2 headings, 16.5pt L1, 22.0pt title |
| **Document Title** | Page 1, Size 22.0pt | Page 1, Size 22.0pt | "CardioTrack CT-200 Home Blood Pressure Monitor — Technical & User Manual" |
| **Selectable Text** | 100% digital text layer | 100% digital text layer | OCR is retained as a dynamic fallback for degraded/image scans |
| **Total Extracted Sections** | 27 sections | 28 sections | Section 5.3 ("Data Export") added in v2 |
| **Tables Detected** | 2 primary structured tables | 2 primary structured tables | Page 2 (Specifications) & Page 4 (Error Codes) |

---

## 3. Structural Inconsistencies & Edge Cases Discovered

### 3.1. Unicode Ligatures Decomposition
- **Finding**: The PDFs encode standard typographic ligatures:
  - `\ufb00` (`ff`) in "Cuff"
  - `\ufb01` (`fi`) in "Specifications", "Profile", "Deflation"
  - `\ufb02` (`fl`) in "Inflation", "Deflation"
- **Impact**: Default byte streams and basic regex matchers fail to match words like `"Cuff"`, throwing `UnicodeEncodeError` when writing to Windows consoles (`cp1252`), and corrupting search indexes and content hashing.
- **Resolution**: Implemented Unicode `NFKD` normalization in `app/utils/normalization.py` to decompose all ligatures into standard ASCII characters before hashing or tree building.

### 3.2. Duplicate Heading Titles Under Different Parents
- **Finding**: Two distinct sections across the document share the identical title `"Error Codes"`:
  - `4.2 Error Codes` (Parent: `4. Alarms and Safety Behavior`, Page 4) - Contains formal device error definitions, causes, and hardware reactions.
  - `7.1 Error Codes` (Parent: `7. Troubleshooting`, Page 6) - Contains consumer guidance on retry limits and contacting support.
- **Impact**: Naive dictionary keying or title-based node identity collapses these two into one node, silently corrupting hierarchy and traceability.
- **Resolution**: Strict separation by hierarchical section numbers and compound logical IDs: `sec_4_2_error_codes` and `sec_7_1_error_codes`.

### 3.3. Out-of-Order Section Numbering
- **Finding**: On Page 3:
  - `3.2 Cuff Inflation Sequence`
  - `3.4 Auto Shutoff`
  - `3.3 Result Display and Classification`
  Section `3.4` physically precedes `3.3` in the PDF layout.
- **Impact**: Stack-based parsers that assert monotonic numbering (`next > prev`) fail or incorrectly nest `3.3` inside `3.4`.
- **Resolution**: Parsing honors the dot-count hierarchy level (`3.X` is always Level 2) and preserves physical document order (`order_index`), while resolving parent-child relationships according to lexical dot prefixes.

### 3.4. Hierarchical Level Skipping
- **Finding**: Under Section 2:
  - `2. Physical and Electrical Specifications` (Level 1)
  - `2.1 General Specifications` (Level 2)
  - `2.1.1.1 Battery Life Under Typical Use` (Level 4 numbering, no `2.1.1` exists)
- **Impact**: Strict tree parsers expecting continuous levels (`1 -> 2 -> 3 -> 4`) throw parent lookup errors when `2.1.1` is absent.
- **Resolution**: Flexible stack-unwinding algorithm that attaches `2.1.1.1` as a child of the nearest active ancestor matching prefix `2.1`, recording an extraction warning.

### 3.5. Inconsistent Heading Font Sizes
- **Finding**: Most Level 2 headings are styled with `12.9pt NimbusSans-Bold`. However:
  - `2.1.1.1 Battery Life Under Typical Use` is styled at `11.0pt NimbusSans-Bold`.
  - `3.2 Cuff Inflation Sequence` is styled at `11.0pt NimbusSans-Bold` (same font size as body text, but bolded).
- **Impact**: Pure font-size thresholding (`size >= 12.0`) fails to recognize `3.2` and `2.1.1.1` as headings, causing them to be merged into previous section bodies.
- **Resolution**: Multi-factor heading detection combining section numbering patterns (`^\d+(\.\d+)*`) with bold styling flags (`flags & 16` or font name containing "bold").

### 3.6. Numbered Lists vs. Section Headings (False-Positive Hazard)
- **Finding**: Under `3.3 Result Display and Classification`, the manual defines clinical classification criteria:
  - `1. Normal: systolic < 120 and diastolic < 80`
  - `2. Elevated: systolic 120–129 and diastolic < 80`
  - `3. Hypertension Stage 1: systolic 130–139 or diastolic 80–89`
  - `4. Hypertension Stage 2: systolic ≥ 140 or diastolic ≥ 90`
  - `5. Hypertensive Crisis: systolic > 180 or diastolic > 120`
- **Impact**: A naive regex `^\d+\.` matches these list items. If parsed as headings, they create 5 bogus Level 1 root sections (`1`, `2`, `3`, `4`, `5`), shredding the document tree.
- **Resolution**: Checked font properties: these list items use `NimbusSans-Regular` at `11.0pt` with flag 4 (serif/regular), while true headings are bold. List items are correctly aggregated into the body text of `3.3`.

### 3.7. Multi-Column Tables
- **Finding**: Two tables exist:
  - `General Specifications` (Page 2, 2 columns)
  - `Error Codes` (Page 4, 3 columns: Code, Meaning, Device Behavior)
- **Impact**: Standard line-by-line PDF reading interleaves bounding boxes across columns (e.g. "Aborts measurement" colliding with "E1 Cuff not connected").
- **Resolution**: Integrated PyMuPDF `find_tables()` to detect table bounding boxes, extract clean tabular rows, convert them into GitHub-flavored Markdown tables, and associate raw tabular JSON with the node.

### 3.8. Cross-Page Paragraph Continuations
- **Finding**: Multiple sections cross page boundaries:
  - `3.1 Powering On and Profile Selection`: Headings & opening sentence on Page 2, second paragraph at top of Page 3.
  - `4. Alarms and Safety Behavior`: Level 1 heading at bottom of Page 3, subsection `4.1` on Page 4.
  - In v2, `4.3 Alarm Thresholds` text `"(overpressure), which cannot be silenced..."` continues across Page 4 and Page 5.
  - In v2, `6.1 Cleaning Instructions` text `"use alcohol, solvents..."` continues across Page 5 and Page 6.
  - In v2, `8.1 Classification` continues onto Page 7.
- **Impact**: Inattentive parsers treat text at the top of a new page as orphaned or assign it to the first heading on that page.
- **Resolution**: State-machine parser maintains the active open section across page transitions until an explicit new heading is encountered.

---

## 4. Revision Comparison: v1 vs. v2 Forensic Matrix

| Section | V1 State | V2 State | Semantic Change Category | Traceability Impact |
| :--- | :--- | :--- | :--- | :--- |
| **2.1.1.1** Battery Life | 300 cycles; warning at 15% | 250 cycles; warning at 10% | **NUMERICAL_THRESHOLD** | **STALE** (Numerical limits decreased) |
| **3.1** Powering On | Page 2-3 | Page 3 | **UNCHANGED** (Text identical, layout shift) | **CURRENT** |
| **3.2** Cuff Inflation | 40 mmHg increments | 30 mmHg increments | **NUMERICAL_THRESHOLD** | **STALE** (Inflation step size reduced) |
| **4. Alarms & Safety** | Bottom Page 3 | Top Page 4 | **UNCHANGED** (Layout shift) | **CURRENT** |
| **4.2** Error Codes | E3 deflates within 2s; E1–E5 | E3 deflates within 1.5s; E1–E6 | **NUMERICAL_THRESHOLD & ERROR_CODE** | **STALE** (Deflation timing 2s -> 1.5s; added E6) |
| **4.3** Alarm Thresholds | Audible alarms for E1–E5 | Audible alarms for E1–E6 | **SAFETY_BEHAVIOR** | **STALE** (New error code covered) |
| **5.3** Data Export | Did not exist | Added: CSV export specs | **ADDED** | Brand new feature |
| **6.1, 6.2, 7.1, 7.2, 8.1** | Identical content | Identical content | **UNCHANGED** | **CURRENT** |

This forensic analysis forms the baseline for our hierarchy reconstruction, version matching, and staleness detection engines.
