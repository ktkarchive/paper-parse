---
name: paper-parse-thin-solid-films
description: >
  Parse a Thin Solid Films (TSF, Elsevier) PDF into a structured set of files:
  meta.json + clean Markdown + split body parts + cropped figure images.
  TSF uses "Fig. N." caption format (abbreviated, period after numeral), Arabic
  numbered section headers with subsections (1. Introduction, 2. Experimental,
  2.1., ...), two-column Elsevier layout, spaced-letter "A R T I C L E I N F O" /
  "A B S T R A C T" blocks (or lowercase "a b s t r a c t" in HAL preprints),
  and bracketed reference style [N]. IMPORTANT: Many TSF PDFs from repositories
  (HAL, SAM) have 2-3 cover pages before the actual article — skip these when
  extracting. Use this skill for Thin Solid Films PDFs.
---

# paper-parse-thin-solid-films

Transforms a Thin Solid Films PDF into a structured file set:
`meta.json` + clean Markdown + split body parts + cropped figure images.

**Journal identifiers:**
- Journal: *Thin Solid Films* (TSF)
- Publisher: Elsevier
- DOI prefix: `10.1016/j.tsf.`
- ISSN: 0040-6090
- Website: https://www.journals.elsevier.com/thin-solid-films

---

## Key Differences from Other Journals

| Feature | MTC (Elsevier) | **TSF (Elsevier)** |
|---|---|---|
| Caption format | `Fig. N.` | **`Fig. N.`** |
| Abstract heading | `A B S T R A C T` | **`A B S T R A C T`** (publisher) / **`a b s t r a c t`** (HAL) |
| Keywords | One per line → comma-sep | **`Keywords:` block**, comma-separated |
| HAL preprint | No | **Yes — 2–3 cover pages; MUST SKIP** |
| Slug convention | `{FirstAuthorYear}` | **`{FirstAuthorYear}`** (e.g. `Puchi-Cabrera_2015`) |

---

## Pipeline

```
PDF  (TSF article — may be HAL/SAM preprint)
 │
 ├─ Step 0 — Identify and skip preprint cover pages (CRITICAL for HAL PDFs)
 │
 ├─ Step 1 — Image extraction
 │           "Fig. N." captions → crop → trim → {slug}-figure{N}.png
 │
 ├─ Step 2 — Full Markdown construction
 │           Transcribe article pages only → single .md
 │           Strip HAL/SAM header text
 │
 ├─ Step 3 — Caption splitting
 │           Extract **Fig. N.** blocks → {slug}-figure{N}.md
 │
 └─ Step 4 — Body split + meta.json
             {slug}-header.md / {slug}-main.md
             {slug}-reference.md / {slug}-backmatter.md (if present)
             meta.json / manifest.json
```

### Output

```
output/{slug}/
├── meta.json
├── {slug}-header.md
├── {slug}-main.md
├── {slug}-reference.md
├── {slug}-backmatter.md  (if present)
├── {slug}-figure1.md
├── {slug}-figure1.png
├── {slug}-figure2.md
├── {slug}-figure2.png
└── manifest.json
```

`{slug}` = `{FirstAuthorYear}`, e.g. `Puchi-Cabrera_2015`.

---

## Step 0 — HAL/SAM Preprint Cover Pages (CRITICAL)

Many TSF PDFs from repositories (hal.science, SAM, institutional archives) have
**2–3 cover pages** before the actual article.

**Detection:** Check page 1 for HAL logo, "hal-XXXXXXX" identifier, or
"HAL is a multi-disciplinary open access archive..." disclaimer.

**Skip:** Do not extract figures or transcribe text from cover pages.
The actual article starts at the first page with the paper title in large font.

```python
COVER_PAGES = 3  # for typical HAL preprints (adjust if needed)
# In PyMuPDF (0-based): skip pages 0, 1, 2; start from page 3
```

---

## Step 1 — Image Extraction

```bash
pip install pymupdf opencv-python-headless --break-system-packages -q
python pdf_to_md.py path/to/paper.pdf --out-dir output/Puchi-Cabrera_2015/
python scripts/extract_figures.py path/to/paper.pdf output/Puchi-Cabrera_2015/ --skip-pages 3
```

**Caption pattern:** `^(Fig\.)\s*(\d+)\.` (case-insensitive)

**Auto-trim:** white margin crop + column-gap detection (two-column Elsevier layout).

**HAL cover pages:** Pass `--skip-pages N` (where N = number of cover pages) to
`extract_figures.py` to skip repository cover pages.

---

## Step 2 — Markdown Construction

Use Gemini to transcribe article pages only (skip cover pages).

**Key formatting rules:**
- Section headers: `## 1. Introduction`, `### 2.1. Sub-section` (numbered, with period)
- Abstract: always `## Abstract` (regardless of HAL/publisher variant)
- Captions: `**Fig. N.** caption text` inline at figure location
- Equations: LaTeX (`$…$` inline, `$$…$$` display)
- Keywords: `**Keywords:** word1, word2, word3`
- Strip HAL metadata: "hal-XXXXXXX", "Submitted on...", disclaimer text

**Authors** — Markdown table:

```markdown
| Author | Affiliation | Notes |
|---|---|---|
| E.S. Puchi-Cabrera^{a,b,c} | Universidad Central de Venezuela...; Venezuelan National Academy...; Université Lille Nord de France... | *Corresponding |
| M.H. Staia^{a,b,d} | Universidad Central de Venezuela...; Venezuelan National Academy...; Arts et Métiers ParisTech... | |
| A. Iost^{d} | Arts et Métiers ParisTech, MSMP, Centre de Lille, France | |
```

---

## Step 3 — Caption Splitting

```bash
python scripts/split_captions.py output/{slug}/{slug}-full.md output/{slug}/ --slug {slug} --out-main {slug}-full-clean.md
```

---

## Step 4 — Body Split + meta.json

```bash
python scripts/split_body.py output/{slug}/{slug}-full-clean.md output/{slug}/ --slug {slug}
```

**Splits:**
- Header: before `## 1. Introduction`
- Main: `## 1. Introduction` through last body section
- References: `## References`
- Backmatter: Acknowledgements / Declaration / Data availability (if present)

**meta.json format:**

```json
{
  "title": "Modeling the composite hardness of multilayer coated systems",
  "journal": "Thin Solid Films",
  "year": "2015",
  "volume": "578",
  "issue": null,
  "pages": "53-62",
  "doi": "10.1016/j.tsf.2015.01.070",
  "authors": [
    {"name": "E.S. Puchi-Cabrera", "affiliations": ["Universidad Central de Venezuela", "Venezuelan National Academy for Engineering and Habitat", "Université Lille Nord de France, USTL, LML, CNRS"], "corresponding": true},
    {"name": "M.H. Staia", "affiliations": ["Universidad Central de Venezuela", "Venezuelan National Academy for Engineering and Habitat", "Arts et Métiers ParisTech, MSMP"], "corresponding": false},
    {"name": "A. Iost", "affiliations": ["Arts et Métiers ParisTech, MSMP"], "corresponding": false}
  ],
  "abstract": "...",
  "keywords": ["Hardness modeling", "Multilayer coatings", "Indentation loading response", "Nanoindentation testing"],
  "slug": "Puchi-Cabrera_2015",
  "figures": [{"index": 1, "file": "figure1.png", "caption": "..."}]
}
```

---

## Quality Checklist

- [ ] HAL/SAM cover pages not included in any output
- [ ] Every `Fig. N.` in text has corresponding `.png` and `.md`
- [ ] HAL metadata stripped from markdown
- [ ] Abstract heading is `## Abstract`
- [ ] Author table has non-empty Affiliation for every author
- [ ] `meta.json` populated with all fields
- [ ] References use bracketed format `[N] F.I. Surname, ...`
