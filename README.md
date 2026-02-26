# paper-parse

**Claude Code skills** that convert academic paper PDFs into structured files:
`meta.json` + clean Markdown + split body parts + cropped figure images.

> Korean version: [README.ko.md](README.ko.md)

Handles the tedious parts — figure cropping, body splitting, metadata extraction —
so you can focus on the content.

---

## Supported journals

| Skill | Journal |
|---|---|
| `paper-parse-scientificreports` | Scientific Reports (Nature Publishing Group) |
| `paper-parse-optics-express` | Optics Express (Optica Publishing Group) |
| `paper-parse-currentopticsandphotonics` | Current Optics and Photonics (Korean Optical Society) |
| `paper-parse-materials-science-poland` | Materials Science-Poland (De Gruyter) |
| `paper-parse-solar-energy-materials-solar-cells` | Solar Energy Materials and Solar Cells (Elsevier) |
| `paper-parse-materials-today-communications` | Materials Today Communications (Elsevier) |
| `paper-parse-journal-of-inorganic-materials` | Journal of Inorganic Materials (Chinese Ceramic Society) |

---

## Output

For every paper, the skill produces:

```
output/{slug}/
├── meta.json              ← title, journal, year, DOI, authors, abstract
├── {slug}-header.md       ← title block + authors/affiliations
├── {slug}-main.md         ← body text (Introduction → Conclusion)
├── {slug}-reference.md    ← reference list
├── {slug}-backmatter.md   ← acknowledgements etc. (if present)
├── {slug}-figure1.md      ← figure 1 caption
├── {slug}-figure1.png     ← figure 1 image (cropped)
├── {slug}-figure2.md
├── {slug}-figure2.png
└── manifest.json          ← index of all files
```

`meta.json` format:
```json
{
  "title": "Paper title",
  "journal": "Optics Express",
  "year": "2022",
  "volume": "30",
  "issue": "7",
  "pages": "11740",
  "doi": "10.1364/OE.XXX.XXXXXX",
  "authors": [{"name": "Author", "affiliations": ["Dept, Uni, Country"], "corresponding": true}],
  "abstract": "...",
  "keywords": ["word1", "word2"],
  "slug": "Kim_2022",
  "figures": [{"index": 1, "file": "figure1.png", "caption": "..."}]
}
```

---

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/ktkarchive/paper-parse.git
cd paper-parse
pip install -r requirements.txt
```

You also need a **Gemini API key** for the PDF → Markdown step:
- Get one at [aistudio.google.com](https://aistudio.google.com)
- Put it in a `.env` file: `GEMINI_API_KEY=your_key_here`

### 2. Install Claude Code skills

```bash
cp -r skills/* ~/.claude/skills/
```

### 3. Use a skill

Open Claude Code in this project directory, attach a PDF, and run the skill:

```
/paper-parse-scientificreports
```

or in Korean:
```
이 논문 파싱해줘  (with PDF attached)
```

Claude will automatically detect the journal and apply the matching skill.

---

## Using from the command line (without Claude Code)

You can also run the pipeline scripts directly:

```bash
# Step 1: PDF → Markdown (requires Gemini API key in .env)
python pdf_to_md.py path/to/paper.pdf --out-dir output/MyPaper/

# Step 2: Extract figures
pip install pymupdf opencv-python-headless
python scripts/extract_figures.py path/to/paper.pdf output/MyPaper/

# Step 3: Split captions
python scripts/split_captions.py output/MyPaper/MyPaper-full.md output/MyPaper/ --slug MyPaper

# Step 4: Split body
python scripts/split_body.py output/MyPaper/MyPaper-full-clean.md output/MyPaper/ --slug MyPaper
```

---

## Adding a new journal

1. Create `skills/paper-parse-<journal-slug>/SKILL.md`
2. Use an existing `SKILL.md` as a template
3. Key things to document:
   - Figure caption format (`Fig. N.` vs `Figure N.` vs `FIG. N.`)
   - Section heading style (numbered/Roman/unnumbered)
   - Abstract heading (explicit or unlabeled paragraph)
   - Author/affiliation line format
   - Any copyright/boilerplate lines to strip
4. Install: `cp -r skills/paper-parse-<journal-slug> ~/.claude/skills/`

---

## Requirements

- Python 3.10+
- `pymupdf` — PDF parsing and figure extraction
- `opencv-python-headless` — image cropping and trimming
- `numpy` — image processing
- **Gemini API key** — PDF → Markdown conversion (`pdf_to_md.py`)
- **Claude Code** — for using the skills

---

## License

MIT

Paper content (PDFs, extracted figures, Markdown text) is **not** included
and remains subject to the original publishers' copyright.
