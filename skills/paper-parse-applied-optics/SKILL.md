---
name: paper-parse-applied-optics
description: >
  Parse an Applied Optics (Optica Publishing Group, formerly OSA) PDF into a
  structured set of files: cropped figure images, per-figure caption markdown,
  and split body markdown files. Applied Optics uses "Fig. N." caption format
  (abbreviated, period after numeral), Arabic numbered section headers with ALL CAPS
  (1. INTRODUCTION, 2. EXPERIMENTAL, ...) and lettered subsections (A. Subsection, B. ...),
  OCIS codes as keywords, two-column layout, and OSA-style references.
  No separate Supplementary Information (SI) PDF is typically published.
  Use this skill whenever the user uploads or references an Applied Optics PDF and
  wants to parse, extract, convert, or decompose it — including requests like "논문 파싱",
  "그림 추출", "md로 변환", "parse this paper", "extract figures", "unpack paper".
  Always prefer this skill over ad-hoc approaches for Applied Optics articles.
---

# paper-parse-applied-optics

Transforms an Applied Optics PDF into a structured file set of markdown and images.

**Journal identifiers:**
- Journal: *Applied Optics* (AO)
- Publisher: Optica Publishing Group (formerly OSA — The Optical Society)
- DOI prefix: `10.1364/AO.`
- ISSN: 1559-128X (print), 2155-3165 (online)
- Website: https://opg.optica.org/ao/home.cfm

---

## Key Format Characteristics

| Feature | Value |
|---|---|
| Caption format | `Fig. N.` (abbreviated, period after numeral) |
| Table caption | `Table N.` |
| Section headers | Arabic numbered, ALL CAPS: `1. INTRODUCTION`, `2. EXPERIMENTAL` |
| Subsections | Lettered: `A. Subsection`, `B. Subsection` (not Arabic-numbered) |
| Keywords | OCIS codes: `(310.1860) Deposition and fabrication` |
| Submission info | Received/Revised/Accepted/Published + Doc. ID |
| Reference format | Numbered: `N. A. Author, "Title," J. Abbrev. XX, pp (year).` |
| Layout | Two-column |
| Page running header | Text-based, thin strips in PDF image blocks (~18 pt) |
| Page 1 banner | Journal logo/banner image — skip all images on page 1 |
| Supplementary Info | None typically |
| Slug convention | `{FirstAuthorYear}` e.g. `Li_2017` |

---

## Pipeline

```
PDF  (Applied Optics main article)
 │
 ├─ Step 1 — Image extraction
 │           "Fig. N." captions → crop → trim → {slug}-figure{N}.png
 │
 ├─ Step 2 — Full Markdown construction
 │           Transcribe paper → single .md with inline captions as **Fig. N.**
 │
 ├─ Step 3 — Caption splitting
 │           Extract **Fig. N.** blocks → {slug}-figure{N}.md
 │           Remove captions + image links from .md
 │
 └─ Step 4 — Body split (3–4 parts)
             {slug}-header.md / {slug}-main.md
             {slug}-reference.md / {slug}-backmatter.md (if present)
```

### Output File Set

| File | Contents |
|---|---|
| `{slug}-header.md` | Title, journal metadata (DOI, dates, Doc. ID), authors/affiliations table, abstract, OCIS keywords |
| `{slug}-main.md` | `## 1. INTRODUCTION` through final body section (CONCLUSIONS) |
| `{slug}-reference.md` | Numbered reference list |
| `{slug}-backmatter.md` | Acknowledgments (omit file if absent) |
| `{slug}-figure{N}.md` | Caption text for Figure N |
| `{slug}-figure{N}.png` | Tightly cropped figure image |
| `meta.json` | Paper metadata (title, authors, journal, DOI, year, slug) |
| `manifest.json` | Index of all extracted assets |

All files go to `./output/{slug}/`.

---

## Step 1 — Image Extraction

### Dependencies

```bash
pip install pymupdf opencv-python-headless
```

### Caption Detection

```python
import re
CAPTION_RE = re.compile(r'^(Fig\.)\s*(\d+)\.', re.IGNORECASE)
```

### Running Header Filtering

Applied Optics running headers appear as very thin image blocks in the PDF (~18 pt height).
Filter them by height threshold. Also skip all images on page 1 (journal banner):

```python
MIN_BLOCK_HEIGHT_PT = 25  # skip running headers (~18 pt) and page 1 banner

for b in blocks:
    if b["type"] == 1:  # image block
        bbox = fitz.Rect(b["bbox"])
        height = bbox.y1 - bbox.y0
        if height < MIN_BLOCK_HEIGHT_PT:
            continue  # skip thin header strips
        if page_num == 0:
            continue  # skip page 1 journal banner
        image_blocks.append({"page": page_num, "bbox": bbox})
```

### Column-Aware Figure Matching

Applied Optics uses two-column layout. Use x-coordinate of caption block to
determine column, then prefer image blocks in the same column:

```python
PAGE_MID_X = 300  # PDF pts — approximate page midpoint

def col_of(bbox):
    cx = (bbox.x0 + bbox.x1) / 2
    return "left" if cx < PAGE_MID_X else "right"
```

Priority matching order:
1. Same column, image bottom (`bbox.y1`) above caption top + 20 pt tolerance
2. Any column, image bottom above caption top + 20 pt
3. Same column, image center above caption top
4. Any column, image center above caption top

### Auto-Trim (OpenCV)

```python
def trim_whitespace(img_bgr, pad=10, white_thresh=245):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    mask = gray < white_thresh
    coords = np.argwhere(mask)
    if len(coords) == 0:
        return img_bgr
    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0)
    return img_bgr[max(0,y0-pad):min(h,y1+pad+1), max(0,x0-pad):min(w,x1+pad+1)]
```

### Tuning Parameters

| Parameter | Default | Notes |
|---|---|---|
| `ZOOM` | `4` | ~300 dpi |
| `white_thresh` | `245` | Lower to `230` for off-white/gray figure backgrounds |
| `pad_pt` | `6` | Padding in PDF pts before rasterization |
| `MIN_BLOCK_HEIGHT_PT` | `25` | Filters running headers (~18 pt) |
| `PAGE_MID_X` | `300` | Page midpoint in PDF pts for column discrimination |

---

## Step 2 — Markdown Construction

Transcribe the full paper into a single `.md` file.

### Structure Rules

**Section headers.** Map to `##` for sections, `###` for lettered subsections:

```markdown
## 1. INTRODUCTION
## 2. EXPERIMENTAL
## 3. THICKNESS DISTRIBUTION MODELING
### A. Sputtering Yield
### B. Sputtering Angular Distribution
### C. Thickness Simulation
## 4. MASK OPTIMIZATION
## 5. CONCLUSIONS
## Acknowledgments
## References
```

**Abstract:**

```markdown
## Abstract

Abstract text here...
```

**OCIS Keywords:**

```markdown
**Keywords:** (310.1860) Deposition and fabrication; (310.3840) Materials and process characterization.
```

**Captions:** `**Fig. N.** caption text` immediately at figure's location in text.

**Equations:** Use `$…$` inline, `$$…$$` display. Number equations `(N)` at end of line.

**Authors.** Markdown table with `^{N}` superscripts for affiliations:

```markdown
| Author | Affiliation | Notes |
|---|---|---|
| Cheng Li^{1} | Institute of Thin Films, ..., University of the West of Scotland, Paisley, Scotland, UK | |
| Des Gibson^{1} | Institute of Thin Films, ..., University of the West of Scotland, Paisley, Scotland, UK | *Corresponding |
| Ewan Waddell^{2} | Thin Film Solutions Ltd., ..., Glasgow G20 0SP, Scotland, UK | |
```

`*Corresponding author: Author.Name@institution.ac.uk`

**Journal metadata** (top of header):

```
Applied Optics, Vol. 56, No. 4, February 1 2017, pp. C65–C70
DOI: https://doi.org/10.1364/AO.56.000C65
© 2016 Optical Society of America
```

**Submission dates:**

```
**Received:** 30 August 2016; **Revised:** 17 October 2016; **Accepted:** 18 October 2016; **Published:** 15 November 2016 (Doc. ID 274929)
```

---

## Step 3 — Caption Splitting

Detect `**Fig. N.**` blocks → write `{slug}-figure{N}.md`, remove from source.

**Caption file format:**

```markdown
# Figure N

**Fig. N.** Full caption text describing the figure…
```

Remove image links from all `.md` files:

```python
import re
cleaned = re.sub(r'!\[.*?\]\(.*?\)\n?', '', content)
cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
```

---

## Step 4 — Body Split

- **Header**: everything before `## 1. INTRODUCTION`
- **Main**: `## 1. INTRODUCTION` through last body section (typically `## N. CONCLUSIONS`)
- **References**: from `## References` to end (or until backmatter)
- **Backmatter**: `## Acknowledgments` (omit file if absent)

---

## meta.json Format

```json
{
  "slug": "Li_2017",
  "title": "Modeling and validation of uniform large-area optical coating deposition on a rotating drum using microwave plasma reactive sputtering",
  "authors": ["Cheng Li", "Shigeng Song", "Des Gibson", "David Child", "Hin On Chu", "Ewan Waddell"],
  "journal": "Applied Optics",
  "volume": "56",
  "issue": "4",
  "year": "2017",
  "pages": "C65–C70",
  "doi": "10.1364/AO.56.000C65",
  "received": "30 August 2016",
  "accepted": "18 October 2016",
  "published": "15 November 2016",
  "doc_id": "274929",
  "keywords": ["(310.1860) Deposition and fabrication", "(310.3840) Materials and process characterization"],
  "n_figures": 9
}
```

---

## File Naming Convention

```
{slug}-header.md          ← title, metadata, authors, abstract, keywords
{slug}-main.md            ← body text (INTRODUCTION through CONCLUSIONS)
{slug}-reference.md       ← numbered reference list
{slug}-backmatter.md      ← acknowledgments (omit if absent)
{slug}-figure{N}.md       ← figure caption
{slug}-figure{N}.png      ← cropped figure image
meta.json                 ← paper metadata
manifest.json             ← index of all extracted assets
```

All files go to `./output/{slug}/`.

---

## Quality Checklist

- [ ] Every `Fig. N.` in the text has a corresponding `.png` and `.md`
- [ ] Caption format uses abbreviated `Fig. N.` (not `Figure N.` or `FIG. N.`)
- [ ] Running header strips not visible in any PNG (filtered by height < 25 pt)
- [ ] Page 1 journal banner not included as a figure
- [ ] Body text does not bleed into figure crops (column-aware matching applied)
- [ ] Abstract has `## Abstract` heading
- [ ] OCIS codes preserved in keyword line with parenthetical codes
- [ ] Section headers use ALL CAPS: `## 1. INTRODUCTION`
- [ ] Subsections use letters: `### A. Subsection`
- [ ] `## 1. INTRODUCTION` present in `{slug}-main.md`
- [ ] `## References` present in `{slug}-reference.md`
- [ ] Author affiliations matched to superscript numbers
- [ ] All Unicode math characters converted to LaTeX in `.md`
- [ ] `meta.json` populated
- [ ] `manifest.json` lists all figure PNGs and MDs
