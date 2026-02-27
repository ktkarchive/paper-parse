---
name: paper-parse-proceedings-estonian-academy-sciences
description: >
  Parse a Proceedings of the Estonian Academy of Sciences (PEA) PDF into a
  structured set of files: cropped figure images, per-figure caption markdown,
  and split body markdown files. PEA uses "Fig. N." caption format (abbreviated,
  period after numeral), Arabic numbered ALL CAPS section headers (1. INTRODUCTION,
  2. EXPERIMENTAL, ...) with decimal subsections (3.1., 3.2.1.), two-column layout,
  and an Estonian-language abstract at the end of the paper (backmatter). Open access
  under CC BY-NC 4.0. No supplementary information (SI) is published separately.
  Use this skill whenever the user uploads or references a PEA PDF and wants to
  parse, extract, convert, or decompose it — including requests like "논문 파싱",
  "그림 추출", "md로 변환", "parse this paper", "extract figures", "unpack paper".
  Always prefer this skill over ad-hoc approaches for PEA articles.
---

# paper-parse-proceedings-estonian-academy-sciences

Transforms a Proceedings of the Estonian Academy of Sciences PDF into a structured file set.

**Journal identifiers:**
- Journal: *Proceedings of the Estonian Academy of Sciences* (PEA)
- Publisher: Estonian Academy of Sciences
- DOI prefix: `10.3176/proc.`
- ISSN: 1736-6046 (print), 1736-7530 (online)
- Website: https://www.eap.ee/proceedings
- License: Open access, CC BY-NC 4.0

---

## Key Format Characteristics

| Feature | Value |
|---|---|
| Caption format | `Fig. N.` (abbreviated, period after numeral) |
| Table caption | `Table N.` (above the table; tables are typeset, not images) |
| Section headers | Arabic numbered, ALL CAPS top-level: `1. INTRODUCTION`, `2. EXPERIMENTAL` |
| Subsections | Decimal: `3.1.`, `3.2.1.` |
| ACKNOWLEDGEMENTS | ALL CAPS: `## ACKNOWLEDGEMENTS` |
| REFERENCES | ALL CAPS: `## REFERENCES` |
| Keywords | `**Key words:**` in PDF → transcribe as `**Keywords:**` |
| Bilingual | English paper + Estonian abstract on last page |
| License | CC BY-NC 4.0 (Open access) |
| Running headers | Alternating: author short form / journal info |
| Page 1 | Contains journal logo + institution logo (skip all images on page 1) |
| Supplementary Info | None |
| Slug convention | `{FirstAuthorYear}` e.g. `Oluwabi_2018` |

---

## Pipeline

```
PDF  (PEA main article)
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
 └─ Step 4 — Body split (4 parts)
             {slug}-header.md / {slug}-main.md
             {slug}-reference.md / {slug}-backmatter.md
```

### Output File Set

| File | Contents |
|---|---|
| `{slug}-header.md` | Journal metadata (DOI, vol/issue/year/pages), title, authors/affiliations table, dates, abstract, keywords |
| `{slug}-main.md` | `## 1. INTRODUCTION` through last body section (`## N. CONCLUSIONS`) |
| `{slug}-reference.md` | Numbered reference list |
| `{slug}-backmatter.md` | `## ACKNOWLEDGEMENTS` + Estonian abstract section |
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

### Page 1 Logo Skipping

PEA page 1 has journal logo and institution logo. Skip all image blocks on page 1:

```python
for page_num in range(len(pdf)):
    page = pdf[page_num]
    blocks = page.get_text("dict")["blocks"]
    for b in blocks:
        if b["type"] == 1:
            if page_num == 0:
                continue  # skip page 1 logos
            image_blocks.append({"page": page_num, "bbox": fitz.Rect(b["bbox"])})
```

### Figure Matching

PEA uses both single-column and full-width figures. Proximity matching:

```python
# Same page, image bottom within 40 pt of caption top
candidates = [
    (i, blk) for i, blk in enumerate(image_blocks)
    if blk["page"] == page_num
    and blk["bbox"].y1 <= cap_top + 40
    and i not in used_blocks
]
# Fallback: previous page image
if not candidates and page_num > 0:
    candidates = [(i, blk) for i, blk in enumerate(image_blocks)
                  if blk["page"] == page_num - 1 and i not in used_blocks]
```

### Auto-Trim (OpenCV)

```python
def trim_whitespace(img_bgr, pad=10, white_thresh=245):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    mask = gray < white_thresh
    coords = np.argwhere(mask)
    if len(coords) == 0: return img_bgr
    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0)
    h, w = gray.shape
    return img_bgr[max(0,y0-pad):min(h,y1+pad+1), max(0,x0-pad):min(w,x1+pad+1)]
```

### Tuning Parameters

| Parameter | Default | Notes |
|---|---|---|
| `ZOOM` | `4` | ~300 dpi |
| `white_thresh` | `245` | |
| `pad_pt` | `6` | PDF pts padding before rasterization |
| `tolerance` | `40` | Cap top ± 40 pt for matching |

---

## Step 2 — Markdown Construction

Transcribe the full paper into a single `.md` file.

### Structure Rules

**Section headers.** Map to `##` for ALL CAPS sections, `###` for decimal subsections,
`####` for sub-subsections:

```markdown
## Abstract

## 1. INTRODUCTION
## 2. EXPERIMENTAL
## 3. RESULTS AND DISCUSSIONS
### 3.1. Surface morphology and composition
### 3.2. Structural and phase characterization
#### 3.2.1. XRD study
#### 3.2.2. Raman study
## 4. CONCLUSIONS
## ACKNOWLEDGEMENTS
## REFERENCES
## {Estonian title}
```

**Abstract:** Transcribe PEA's inline `**Abstract.**` as:
```markdown
## Abstract

Abstract text here...
```

**Keywords:** `**Key words:**` in PDF → `**Keywords:**` in markdown.

**Captions:** `**Fig. N.** caption text` at figure's location in text.

**Tables:** Typeset tables — reproduce in Markdown with `|---|` columns and
`**Table N.** caption above`.

**Equations:** `$…$` inline, `$$…$$` display, numbered `(N)` at end of display line.

**Authors.** Markdown table with `^{letter}` for affiliations:

```markdown
| Author | Affiliation | Notes |
|---|---|---|
| Abayomi T. Oluwabi^{a} | Laboratory of Thin Film Chemical Technologies, Department of Materials Science, Tallinn University of Technology, Ehitajate tee 5, 19086 Tallinn, Estonia | *Corresponding |
| Albert O. Juma^{b} | Department of Physics and Astronomy, Botswana International University of Science and Technology, Private Bag 16, Palapye, Botswana | |
```

`*Corresponding author: author@institution.ee`

**Journal metadata** (top of header):
```
Proceedings of the Estonian Academy of Sciences, 2018, 67, 2, 147–157
DOI: https://doi.org/10.3176/proc.2018.2.05
© 2018 Authors. Open Access under Creative Commons Attribution-NonCommercial 4.0 International License (CC BY-NC 4.0).
```

**Dates:**
```
**Received:** 19 October 2017; **Revised:** 19 December 2017; **Accepted:** 20 December 2017; **Available online:** 5 April 2018
```

**Estonian abstract.** Last page — include verbatim as `## {Estonian title}`:
```markdown
## Zr-legeerimise mõju pihustuspürolüüsimeetodil sadestatud TiO2 õhukeste kilede struktuursetele ja elektrilistele omadustele

Abayomi T. Oluwabi, Albert O. Juma, Ilona Oja Acik, Arvo Mere ja Malle Krunks

{Estonian abstract text...}
```

---

## Step 3 — Caption Splitting

Detect `**Fig. N.**` blocks → write `{slug}-figure{N}.md`, remove from source.
Also remove any `[Figure N: ...]` code blocks left by Gemini:

```python
import re
cleaned = re.sub(r'!\[.*?\]\(.*?\)\n?', '', content)
cleaned = re.sub(r'```\n\[Figure[^\]]*\][^`]*```\n?', '', cleaned, flags=re.DOTALL)
cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
```

**Caption file format:**
```markdown
# Figure N

**Fig. N.** Full caption text describing the figure…
```

---

## Step 4 — Body Split

Split boundaries:

```
header   : 0 .. ## 1. INTRODUCTION
main     : ## 1. INTRODUCTION .. ## ACKNOWLEDGEMENTS
backmatter: ## ACKNOWLEDGEMENTS .. ## REFERENCES  +  ## {Estonian} .. end
reference: ## REFERENCES .. ## {Estonian title}
```

- **Header**: journal metadata, title, authors, dates, abstract, keywords
- **Main**: INTRODUCTION through CONCLUSIONS
- **References**: REFERENCES section
- **Backmatter**: ACKNOWLEDGEMENTS + Estonian abstract (combine)

---

## meta.json Format

```json
{
  "slug": "Oluwabi_2018",
  "title": "Effect of Zr doping on the structural and electrical properties of spray deposited TiO2 thin films",
  "authors": ["Abayomi T. Oluwabi", "Albert O. Juma", "Ilona Oja Acik", "Arvo Mere", "Malle Krunks"],
  "journal": "Proceedings of the Estonian Academy of Sciences",
  "publisher": "Estonian Academy of Sciences",
  "volume": "67",
  "issue": "2",
  "year": "2018",
  "pages": "147–157",
  "doi": "10.3176/proc.2018.2.05",
  "received": "19 October 2017",
  "revised": "19 December 2017",
  "accepted": "20 December 2017",
  "available_online": "5 April 2018",
  "license": "CC BY-NC 4.0",
  "keywords": ["chemical spray pyrolysis", "doping", "thin films", "dielectric relaxation", "Zr-TiO2"],
  "n_figures": 9,
  "n_tables": 2
}
```

---

## File Naming Convention

```
{slug}-header.md          ← journal metadata, title, authors, abstract, keywords
{slug}-main.md            ← body text (INTRODUCTION through CONCLUSIONS)
{slug}-reference.md       ← numbered reference list
{slug}-backmatter.md      ← ACKNOWLEDGEMENTS + Estonian abstract
{slug}-figure{N}.md       ← figure caption
{slug}-figure{N}.png      ← cropped figure image
meta.json                 ← paper metadata
manifest.json             ← index of all extracted assets
```

All files go to `./output/{slug}/`.

---

## Quality Checklist

- [ ] Every `Fig. N.` in the text has a corresponding `.png` and `.md`
- [ ] Caption format uses abbreviated `Fig. N.` (not `Figure N.`)
- [ ] Page 1 logos not included as figures
- [ ] Abstract has `## Abstract` heading
- [ ] Keywords use `**Keywords:**` (not `**Key words:**`)
- [ ] ALL CAPS top-level headers: `## 1. INTRODUCTION`, `## 4. CONCLUSIONS`
- [ ] Decimal subsections: `### 3.1.`, `#### 3.2.1.`
- [ ] `## 1. INTRODUCTION` present in `{slug}-main.md`
- [ ] `## REFERENCES` present in `{slug}-reference.md`
- [ ] `## ACKNOWLEDGEMENTS` present in `{slug}-backmatter.md`
- [ ] Estonian abstract included in backmatter
- [ ] Author affiliations matched to superscript letters
- [ ] All Unicode math converted to LaTeX in `.md`
- [ ] `meta.json` populated
- [ ] `manifest.json` lists all figure PNGs and MDs
