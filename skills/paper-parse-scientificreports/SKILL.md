---
name: paper-parse-scientificreports
description: >
  Parse a Scientific Reports (Nature Publishing Group) PDF — either a main
  article or a Supplementary Information (SI) file — into a structured set of
  files: meta.json, full Markdown, split body parts, and cropped figure images.
  Use this skill whenever the user wants to parse, convert, or extract content
  from a Scientific Reports PDF — including requests like "논문 파싱", "그림/표 추출",
  "md로 변환", "parse this paper", "extract figures", "SI 파싱", "부록 추출".
  Output goes to a user-specified directory (default: ./output/{slug}/).
---

# paper-parse-scientificreports

Converts a Scientific Reports PDF into a structured file set for downstream use
(RAG ingestion, annotation, knowledge base, etc.).

**Journal identifiers:**
- Journal: *Scientific Reports* (Sci. Rep.)
- Publisher: Nature Publishing Group (Springer Nature)
- DOI prefix: `10.1038/`
- ISSN: 2045-2322

---

## Step 0 — Identify PDF Type

Determine whether the PDF is a **main article** or **Supplementary Information (SI)**:

**Check A — Page 1 title block.**
If it begins with "Supplementary Information", "Supplementary Material", or
"Supporting Information" → **SI**.

**Check B — Figure/Table caption prefix.**
If captions follow `Fig. S\d+` or `Table S\d+` → **SI**.

**Check C — Journal header.**
Main articles have a gray raster header bar (`www.nature.com/scientificreports/`).
SI files typically lack this bar.

**Default:** treat as main article.

---

## Pipeline A — Main Article

```
PDF
 ├─ Step 1 — Image extraction
 │           Detect captions → crop → trim → figure{N}.png / table{N}.png
 │
 ├─ Step 2 — Full Markdown construction
 │           Transcribe paper → {slug}-full.md with inline captions
 │
 ├─ Step 3 — Caption splitting
 │           Extract **Figure N.** / **Table N.** → {slug}-figure{N}.md
 │           Remove captions + image links from .md
 │
 ├─ Step 4 — Body split (4 parts)
 │           {slug}-header.md / {slug}-main.md
 │           {slug}-reference.md / {slug}-backmatter.md
 │
 └─ Step 5 — Metadata extraction
             {slug}-header.md → meta.json
```

### Output File Set — Main Article

| File | Contents |
|---|---|
| `meta.json` | Structured metadata (title, journal, authors, year, DOI, abstract) |
| `{slug}-header.md` | Title, journal metadata, authors/affiliations table |
| `{slug}-main.md` | Abstract through Conclusion — body text and equations |
| `{slug}-reference.md` | Numbered reference list |
| `{slug}-backmatter.md` | Acknowledgements, Author Contributions, license (omit if absent) |
| `{slug}-figure{N}.png` | Tightly cropped figure image |
| `{slug}-table{N}.png` | Tightly cropped table image |
| `{slug}-figure{N}.md` | Caption text for Figure N |
| `{slug}-table{N}.md` | Caption text for Table N |
| `manifest.json` | Index of all extracted assets |

`{slug}` = DOI article number (e.g. `srep22941`).
All files go to `./output/{slug}/` unless the user specifies a different path.

---

## Pipeline B — Supplementary Information (SI)

```
PDF (SI)
 ├─ Step 1 — Image extraction  → {slug}-sfigure{N}.png / stable{N}.png
 ├─ Step 2 — SI Markdown       → {slug}-SI.md
 └─ Step 3 — Caption splitting → {slug}-sfigure{N}.md / {slug}-stable{N}.md
```

No 4-part body split for SI. No `meta.json` needed (meta already captured in main article).

---

## Step 1 — Image Extraction

### Setup

```bash
pip install pymupdf opencv-python-headless
python scripts/extract_figures.py <input.pdf> <output_dir> [--si]
```

### Caption Detection

```python
# Main article
CAPTION_RE = re.compile(r'^(Figure|Table)\s+(\d+)[\.\s]', re.IGNORECASE)

# SI
CAPTION_RE = re.compile(r'^(Fig(?:ure)?|Table)\.?\s+(S?\d+)[\.\s]', re.IGNORECASE)
```

For SI, always prepend `s` to the label (e.g. `Fig. S1` → `sfigure1`).

### Region Determination

For each caption at `y = cap_top`:
- **Top:** bottom Y of previous caption on same page, or page content start
- **Bottom:** `cap_top − 3 pt`
- **Horizontal:** full page width ±3 pt
- Rendered at **4× zoom** (`fitz.Matrix(4, 4)`)

### Auto-Trim (OpenCV)

1. **Dark-bar removal.** Strip rows where `row_mean < 200` (removes `www.nature.com/...` header bar).
2. **White-margin crop.** `gray > 245` = background; tight bounding box + 10 px padding.
3. **Right-side column trim.** Crop at first non-white column from right; +12 px padding.

### Layout Quirks — Main Article

**Dashed separator lines.** Detected via `get_drawings()` where `dashes = [0, 2.992]`.
Use dashed line Y as top boundary of figure below.

### Layout Quirks — SI

**TOC page.** Page 0 of SI is skipped entirely for caption detection.

---

## Step 2 — Markdown Construction

### Main Article Rules

**Section headers.** Add `1.`, `2.`, `2.1` numbering if paper lacks explicit numbering.

**Captions.** Inline at figure location: `**Figure N.** caption text`.

**Equations.** `$…$` inline, `$$…$$` display. Convert Unicode math to LaTeX.

**Authors.** Build a Markdown table:

| Author | Affiliation | Notes |
|---|---|---|
| Author Name¹* | Dept, Inst, City, Country | *Corresponding |

Include email: `*Corresponding author: email@domain.com`

### SI Rules

Single file `{slug}-SI.md` with Contents list → Supplementary Notes → References.

---

## Step 3 — Caption Splitting

```bash
python scripts/split_captions.py {slug}-full.md <output_dir> --slug {slug}
# or for SI:
python scripts/split_captions.py {slug}-SI.md <output_dir> --slug {slug} --si
```

---

## Step 4 — Body Split (main article only)

```bash
python scripts/split_body.py {slug}-full-clean.md <output_dir> --slug {slug}
```

- **Header:** everything before Abstract
- **Main:** Abstract through Conclusion
- **References:** numbered reference list
- **Backmatter:** Acknowledgements / Author Contributions / license (omit if absent)

---

## Step 5 — meta.json

Extract from `{slug}-header.md` and write `meta.json`:

```json
{
  "title": "Full paper title",
  "journal": "Scientific Reports",
  "year": "2016",
  "volume": null,
  "issue": null,
  "pages": null,
  "doi": "10.1038/srep22941",
  "authors": [
    {
      "name": "Author Name",
      "affiliations": ["Dept, University, City, Country"],
      "corresponding": true,
      "email": "author@domain.com"
    }
  ],
  "abstract": "Abstract text…",
  "keywords": [],
  "slug": "srep22941",
  "figures": [
    {"index": 1, "file": "figure1.png", "caption_file": "srep22941-figure1.md", "caption": "Caption text…"}
  ]
}
```

---

## Quality Checklist

- [ ] PDF type correctly identified (main vs. SI)
- [ ] Every Figure/Table in the text has a `.png` and `.md`
- [ ] No journal header bars visible in any PNG
- [ ] No body text bleeds into figure crops
- [ ] Right-side white space trimmed for single-column figures
- [ ] Equations in LaTeX, not raw Unicode
- [ ] Image links removed from all `.md` files
- [ ] `meta.json` populated with title, authors, year, DOI, abstract
- [ ] **[Main only]** 4-part body split complete
- [ ] **[SI only]** `s` prefix on all figure/table labels
