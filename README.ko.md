# paper-parse

학술 논문 PDF를 구조화된 파일로 변환하는 **Claude Code 스킬 모음**:
`meta.json` + 정제된 Markdown + 본문 분리 + 그림 이미지 추출.

> English version: [README.md](README.md)

그림 크롭, 본문 분리, 메타데이터 추출 등 귀찮은 작업을 자동화합니다.

---

## 지원 저널

| 스킬 | 저널 |
|---|---|
| `paper-parse-scientificreports` | Scientific Reports (Nature Publishing Group) |
| `paper-parse-optics-express` | Optics Express (Optica Publishing Group) |
| `paper-parse-currentopticsandphotonics` | Current Optics and Photonics (한국광학회) |
| `paper-parse-materials-science-poland` | Materials Science-Poland (De Gruyter) |
| `paper-parse-solar-energy-materials-solar-cells` | Solar Energy Materials and Solar Cells (Elsevier) |
| `paper-parse-materials-today-communications` | Materials Today Communications (Elsevier) |
| `paper-parse-journal-of-inorganic-materials` | Journal of Inorganic Materials (중국세라믹학회) |
| `paper-parse-applied-optics` | Applied Optics (Optica Publishing Group) |

---

## 출력 결과

논문 1편 처리 시:

```
output/{slug}/
├── meta.json              ← 제목, 저널, 연도, DOI, 저자, 초록
├── {slug}-header.md       ← 타이틀 블록 + 저자/소속
├── {slug}-main.md         ← 본문 (서론 → 결론)
├── {slug}-reference.md    ← 참고문헌
├── {slug}-backmatter.md   ← 감사의 글 등 (있는 경우)
├── {slug}-figure1.md      ← 그림 1 캡션
├── {slug}-figure1.png     ← 그림 1 이미지 (크롭)
├── {slug}-figure2.md
├── {slug}-figure2.png
└── manifest.json          ← 전체 파일 목록
```

`meta.json` 형식:
```json
{
  "title": "논문 제목",
  "journal": "Optics Express",
  "year": "2022",
  "volume": "30",
  "issue": "7",
  "pages": "11740",
  "doi": "10.1364/OE.XXX.XXXXXX",
  "authors": [{"name": "저자명", "affiliations": ["소속"], "corresponding": true}],
  "abstract": "초록...",
  "keywords": ["키워드1", "키워드2"],
  "slug": "Kim_2022",
  "figures": [{"index": 1, "file": "figure1.png", "caption": "..."}]
}
```

---

## 빠른 시작

### 1. 클론 및 설치

```bash
git clone https://github.com/ktkarchive/paper-parse.git
cd paper-parse
pip install -r requirements.txt
```

PDF → Markdown 변환에 **Gemini API 키**가 필요합니다:
- [aistudio.google.com](https://aistudio.google.com) 에서 발급
- `.env` 파일에 추가: `GEMINI_API_KEY=your_key_here`

### 2. 스킬 설치

```bash
cp -r skills/* ~/.claude/skills/
```

### 3. 스킬 사용

Claude Code를 이 프로젝트 디렉토리에서 열고, PDF를 첨부한 뒤:

```
/paper-parse-scientificreports
```

또는:
```
이 논문 파싱해줘  (PDF 첨부)
```

Claude가 저널을 자동 감지하고 알맞은 스킬을 적용합니다.

---

## 커맨드라인으로 직접 사용 (Claude Code 없이)

```bash
# Step 1: PDF → Markdown (.env에 Gemini API 키 필요)
python pdf_to_md.py path/to/paper.pdf --out-dir output/MyPaper/

# Step 2: 그림 추출
pip install pymupdf opencv-python-headless
python scripts/extract_figures.py path/to/paper.pdf output/MyPaper/

# Step 3: 캡션 분리
python scripts/split_captions.py output/MyPaper/MyPaper-full.md output/MyPaper/ --slug MyPaper

# Step 4: 본문 분리
python scripts/split_body.py output/MyPaper/MyPaper-full-clean.md output/MyPaper/ --slug MyPaper
```

---

## 새 저널 추가

1. `skills/paper-parse-<저널-슬러그>/SKILL.md` 생성
2. 기존 `SKILL.md`를 템플릿으로 사용
3. 저널별로 문서화할 항목:
   - 그림 캡션 형식 (`Fig. N.` / `Figure N.` / `FIG. N.`)
   - 섹션 제목 스타일 (번호/로마자/없음)
   - 초록 제목 유무
   - 저자/소속 라인 형식
   - 저작권 등 제거할 보일러플레이트 라인
4. 설치: `cp -r skills/paper-parse-<저널-슬러그> ~/.claude/skills/`

---

## 의존성

- Python 3.10+
- `pymupdf` — PDF 파싱 및 그림 추출
- `opencv-python-headless` — 이미지 크롭/트리밍
- `numpy` — 이미지 처리
- **Gemini API 키** — PDF → Markdown 변환
- **Claude Code** — 스킬 실행용

---

## 라이선스

MIT

논문 원문 (PDF, 그림, Markdown 텍스트)은 포함되지 않으며 원 발행사의 저작권을 따릅니다.
