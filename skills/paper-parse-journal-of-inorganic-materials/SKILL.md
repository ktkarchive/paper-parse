---
name: paper-parse-journal-of-inorganic-materials
description: >
  Parse a Journal of Inorganic Materials (无机材料学报, JIM) PDF into a structured
  set of files: meta.json + clean Markdown + split body parts + cropped figure
  images. JIM is a bilingual (English/Chinese) journal published by the Chinese
  Ceramic Society. It uses "Fig. N" caption format (NO period after numeral),
  Chinese-style author names (SURNAME Firstname), parenthetical affiliation block,
  numbered sections without trailing periods, and bracketed references with
  ALL-CAPS author surnames. Use this skill whenever the user uploads or references
  a Journal of Inorganic Materials PDF and wants to parse, extract, convert, or
  decompose it. Always prefer this skill over ad-hoc approaches for JIM articles.
---

# paper-parse-journal-of-inorganic-materials

Transforms a Journal of Inorganic Materials (JIM, 无机材料学报) PDF into a structured
file set ready for downstream use.

**Journal identifiers:**
- Journal: *Journal of Inorganic Materials* (无机材料学报, JIM)
- Publisher: Chinese Ceramic Society / Science Press
- DOI prefix: `10.15541/jim`
- ISSN: 1000-324X
- Website: http://www.jim.org.cn/

---

## Key Differences from Other Journals

| Feature | Scientific Reports | Elsevier (MTC/SEMSC) | **JIM** |
|---|---|---|---|
| Caption format | `Figure N.` | `Fig. N.` | **`Fig. N`** (NO period after numeral) |
| Section headers | Unnumbered | `1. Introduction` | **`1 Introduction`** (no period) |
| Subsections | — | `2.1. Title` | **`2.1  Title`** (no period, two spaces) |
| Abstract | `## Abstract` | `A B S T R A C T` | **`Abstract:`** inline label |
| Keywords | — | One per line | **`Key words:`** semicolon-separated |
| Author format | First Last | First Last | **`SURNAME Firstname^N`** (Chinese pinyin) |
| Affiliations | Inline table | Inline table | **Parenthetical numbered block** `(1. ...; 2. ...; 3. ...)` |
| References | `1. Author` | `[N] F.I. Surname` | **`[N] SURNAME A, et al.`** ALL-CAPS surnames |
| Bilingual | No | No | **Yes — English body + Chinese abstract at end** |
| Supplementary | Separate PDF | Online SI | **None** |
| Slug | DOI number | `{AuthorYear}` | **`{FirstAuthorLastName_Year}`** |

---

## Pipeline

```
PDF  (JIM main article)
 │
 ├─ Step 1 — Image extraction
 │           "Fig. N" captions → crop → trim → {slug}-figure{N}.png
 │
 ├─ Step 2 — Full Markdown construction
 │           Transcribe English body → single .md with inline **Fig. N** captions
 │
 ├─ Step 3 — Caption splitting
 │           Extract **Fig. N** blocks → {slug}-figure{N}.md
 │           Remove captions + image links from .md
 │
 └─ Step 4 — Body split (3–4 parts)
             {slug}-header.md / {slug}-main.md
             {slug}-reference.md / {slug}-backmatter.md (Chinese abstract)
```

### Output File Set

```
output/{slug}/
├── meta.json
├── {slug}-header.md       ← article ID, DOI, title, authors/affiliations, abstract, keywords
├── {slug}-main.md         ← body text (Experimental/Introduction through Conclusions)
├── {slug}-reference.md    ← bracketed reference list
├── {slug}-backmatter.md   ← Chinese abstract section (if present)
├── {slug}-figure1.md      ← figure 1 caption
├── {slug}-figure1.png     ← figure 1 image (cropped)
├── {slug}-figure2.md
├── {slug}-figure2.png
└── manifest.json
```

`{slug}` = `{FirstAuthorLastName_Year}`, e.g. `Zhao_2020`.

---

## Step 1 — Image Extraction

### Setup

```bash
pip install pymupdf opencv-python-headless --break-system-packages -q
python scripts/extract_figures.py <input.pdf> <output_dir>
```

### Caption Detection

JIM uses `Fig.` + space + Arabic numeral with **NO trailing period**:

```python
CAPTION_RE_MAIN = re.compile(
    r'^(Fig\.)\s+(\d+)\b',
    re.IGNORECASE,
)
```

**Critical:** Do NOT use a pattern requiring a period after the numeral — JIM captions have none.

**Tables:** `Table N  Description` (no period). Caption appears above or below the table.

### Page Header Skipping

JIM running headers contain Chinese characters and journal name:
- Left pages: `第N期 SURNAME, et al: Short title...`
- Right pages: `PPPP 无机材料学报 第NN卷`

Use `HEADER_H_PX = 150` (thinner than Elsevier headers).

### Auto-Trim (OpenCV)

1. **Dark-bar removal.** Check top ~5% of page. If `mean(top_band) < 200`, crop it off.
2. **White-margin crop.** `gray > 245` = background. Tight bounding box + 10 px padding.
3. **Right-side column trim.** Scan right-to-left; crop at first non-white column + 12 px.

### Column-Gap Detection (two-column layout)

JIM uses a two-column layout. Apply column-gap detection for single-column figures:

```python
MIN_COL_GAP_PX = 20

def find_column_gap(region_gray, white_thresh=245):
    """Return x of the largest white vertical gap in the middle-third, or None."""
    W = region_gray.shape[1]
    mid_start, mid_end = W // 3, W * 2 // 3
    col_nonwhite = np.sum(region_gray < white_thresh, axis=0)
    in_gap, gap_start, best = False, 0, (0, 0, 0)
    for x in range(mid_start, mid_end):
        if col_nonwhite[x] == 0:
            if not in_gap:
                in_gap, gap_start = True, x
        else:
            if in_gap:
                w = x - gap_start
                if w > best[2]:
                    best = (gap_start, x, w)
                in_gap = False
    if in_gap:
        w = mid_end - gap_start
        if w > best[2]:
            best = (gap_start, mid_end, w)
    return best[0] if best[2] >= MIN_COL_GAP_PX else None

col_gap_x = find_column_gap(fig_region)
if col_gap_x is not None and col_gap_x < cmax:
    cmax = min(cmax, col_gap_x - 1)
```

### Tuning Parameters

| Parameter | Default | Notes |
|---|---|---|
| `ZOOM` | `4` | ~300 dpi |
| `white_thresh` | `245` | |
| `pad` | `10` | |
| `HEADER_H_PX` | `150` | JIM header is thinner than Elsevier |
| `MIN_COL_GAP_PX` | `20` | |

---

## Step 2 — Markdown Construction

Transcribe the **English** body into a single `.md` using Gemini.

### Structure Rules

**Section headers.** JIM sections have NO period after numbers:

```markdown
## 1 Experimental
### 1.1  Materials and methods
## 2 Results and discussion
### 2.1  F: Mg molar ratio
### 2.2  Micro structure
## 3 Conclusions
## References
```

**Abstract.** Transcribe as:

```markdown
## Abstract

Body of abstract text…
```

**Keywords.** JIM uses `Key words:` with semicolons:

```markdown
**Key words:** MgF2 thin film; F deficiency; transmittance; sputtering power
```

**Captions.** Transcribe as `**Fig. N** description` (no period after N):

```markdown
**Fig. 1** Effect of sputtering power on XPS spectra of MgF2 thin film
```

**Authors.** JIM author line: `SURNAME Firstname^{1,2,3}, SURNAME Firstname^{1,2}, ...`
Affiliation block appears immediately after: `(1. School...; 2. State Key Lab...; 3. Beijing Institute...)`

Build a Markdown table resolving affiliation numbers to full strings:

```markdown
| Author | Affiliation | Notes |
|---|---|---|
| ZHAO Changjiang^{1,2,3} | School of Materials Science and Engineering, Tiangong University, Tianjin 300387, China; State Key Laboratory of Membrane Separation and Membrane Process, Tiangong University, Tianjin 300387, China; Beijing Institute of Spacecraft System Engineering, Beijing 100086, China | |
| LIU Juncheng^{1,2} | School of Materials Science and Engineering, Tiangong University, Tianjin 300387, China; State Key Laboratory of Membrane Separation and Membrane Process, Tiangong University, Tianjin 300387, China | *Corresponding |
```

Include: `*E-mail: corresponding@email.com`

**Every author must have at least one affiliation.**

**Journal metadata** (at top of header):

```
Journal of Inorganic Materials, Vol. 35, No. 9, 2020, pp. 1064–1070
Article ID: 1000-324X(2020)09-1064-07
DOI: https://doi.org/10.15541/jim200190565
```

---

## Step 3 — Caption Splitting

Standard `split_captions.py` expects `**Figure N.**` — JIM uses `**Fig. N**` (no period).
Use inline Python:

```python
import re, pathlib

slug = "Zhao_2020"
out_dir = pathlib.Path(f"output/{slug}")
full_md = (out_dir / f"{slug}-full.md").read_text(encoding="utf-8")

CAPTION_RE = re.compile(r'^\*\*Fig\.\s+(\d+)\*\*\s*', re.IGNORECASE | re.MULTILINE)
parts = CAPTION_RE.split(full_md)

clean_md = parts[0]
for i in range(0, len(parts[1::2])):
    fig_num = parts[1 + i*2]
    rest = parts[2 + i*2]
    cap_end = re.search(r'\n\n', rest)
    cap_text = rest[:cap_end.start()].strip() if cap_end else rest.strip()
    after = rest[cap_end.end():] if cap_end else ""
    cap_file = out_dir / f"{slug}-figure{fig_num}.md"
    cap_file.write_text(f"# Figure {fig_num}\n\n**Fig. {fig_num}** {cap_text}\n", encoding="utf-8")
    clean_md += after

clean_md = re.sub(r'!\[.*?\]\(.*?\)\n?', '', clean_md)
clean_md = re.sub(r'\n{3,}', '\n\n', clean_md)
(out_dir / f"{slug}-full-clean.md").write_text(clean_md, encoding="utf-8")
```

---

## Step 4 — Body Split

JIM order: Header → Body sections → Conclusions → References → Chinese abstract

```python
import re, pathlib

slug = "Zhao_2020"
out_dir = pathlib.Path(f"output/{slug}")
text = (out_dir / f"{slug}-full-clean.md").read_text(encoding="utf-8")

intro_m = re.search(r'^## 1\b', text, re.MULTILINE)
ref_m = re.search(r'^## References', text, re.MULTILINE)
chinese_m = re.search(r'^溅射|^摘\s*要|^[^\x00-\x7F]{4}', text, re.MULTILINE)

(out_dir / f"{slug}-header.md").write_text(text[:intro_m.start()].strip(), encoding="utf-8")
(out_dir / f"{slug}-main.md").write_text(text[intro_m.start():ref_m.start()].strip(), encoding="utf-8")
end = chinese_m.start() if chinese_m else len(text)
(out_dir / f"{slug}-reference.md").write_text(text[ref_m.start():end].strip(), encoding="utf-8")
if chinese_m:
    (out_dir / f"{slug}-backmatter.md").write_text(text[end:].strip(), encoding="utf-8")
```

---

## meta.json Format

```json
{
  "title": "Sputtering Power on the Microstructure and Properties of MgF2 Thin Films Prepared with Magnetron Sputtering",
  "journal": "Journal of Inorganic Materials",
  "year": "2020",
  "volume": "35",
  "issue": "9",
  "pages": "1064-1070",
  "article_id": "1000-324X(2020)09-1064-07",
  "doi": "10.15541/jim200190565",
  "received": "2019-11-06",
  "revised": "2019-12-10",
  "authors": [
    {
      "name": "ZHAO Changjiang",
      "affiliation_keys": ["1", "2", "3"],
      "affiliations": [
        "School of Materials Science and Engineering, Tiangong University, Tianjin 300387, China",
        "State Key Laboratory of Membrane Separation and Membrane Process, Tiangong University, Tianjin 300387, China",
        "Beijing Institute of Spacecraft System Engineering, Beijing 100086, China"
      ],
      "corresponding": false
    },
    {
      "name": "LIU Juncheng",
      "affiliation_keys": ["1", "2"],
      "affiliations": [
        "School of Materials Science and Engineering, Tiangong University, Tianjin 300387, China",
        "State Key Laboratory of Membrane Separation and Membrane Process, Tiangong University, Tianjin 300387, China"
      ],
      "corresponding": true,
      "email": "jchliu@tjpu.edu.cn"
    }
  ],
  "abstract": "To reduce the F deficiency defect in MgF2 thin films...",
  "keywords": ["MgF2 thin film", "F deficiency", "transmittance", "antireflection", "sputtering power", "magnetron sputtering"],
  "slug": "Zhao_2020",
  "figures": [
    {"index": 1, "file": "figure1.png", "caption": "Effect of sputtering power on XPS spectra of MgF2 thin film"}
  ]
}
```

---

## Quality Checklist

- [ ] Every `Fig. N` in the text has a corresponding `.png` and `.md`
- [ ] Caption format uses `**Fig. N**` (NO period after numeral)
- [ ] Running header not visible in any PNG
- [ ] Body text does not bleed into figure crops (column-gap detection applied)
- [ ] Abstract has `## Abstract` heading
- [ ] Keywords use `**Key words:**` with semicolons
- [ ] Author table uses `SURNAME Firstname^{N}` format
- [ ] Every author has at least one affiliation
- [ ] Received/Revised dates present in header
- [ ] References use `[N] SURNAME A, ...` ALL-CAPS format
- [ ] Chinese abstract section handled (backmatter or omitted)
- [ ] `meta.json` populated with `article_id` field
