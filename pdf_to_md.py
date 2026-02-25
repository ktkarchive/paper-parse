"""Convert PDF papers to Markdown via Gemini with optional figure extraction."""

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

def load_env_file(path: Path) -> None:
    """Lightweight .env loader so we can run without python-dotenv."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


# Load .env from project root.
load_env_file(Path(__file__).resolve().parent.parent / ".env")

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash")
TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0"))

def get_api_keys() -> list[str]:
    """Load API keys with rotation support."""
    keys_raw = os.getenv("GEMINI_API_KEYS", "").strip()
    keys: list[str] = []
    if keys_raw:
        normalized = keys_raw.replace("\n", ",").replace(";", ",")
        for item in normalized.split(","):
            key = item.strip()
            if key:
                keys.append(key)
    single_key = os.getenv("GEMINI_API_KEY", "").strip()
    if single_key:
        keys.append(single_key)
    # De-duplicate while preserving order.
    dedup: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key not in seen:
            dedup.append(key)
            seen.add(key)
    return dedup


API_KEYS = get_api_keys()

if not API_KEYS:
    print("ERROR: set GEMINI_API_KEYS or GEMINI_API_KEY in .env")
    sys.exit(1)


def build_prompt(figure_dir_name: str | None) -> str:
    figure_rule = (
        "9. If a figure is present, keep figure references and captions. "
        "If local figure files are extracted, prefer markdown image links like "
        f"'![Figure X]({figure_dir_name}/<filename>)' when you can confidently align them."
        if figure_dir_name
        else "9. Keep all figure references and captions as explicit markdown text placeholders."
    )
    return f"""Convert this PDF paper into faithful Markdown.

Rules:
1. Preserve all text sections (title, abstract, intro, methods, results, discussion, conclusion, references).
2. Keep equations in LaTeX style ($...$ or $$...$$).
3. Convert tables to markdown tables when possible.
4. Keep figure placeholders/captions in output near their original positions.
5. Preserve citation numbering/style from the source.
6. Preserve heading hierarchy.
7. Include author and affiliation blocks.
8. Do not summarize, paraphrase, or add claims not in the source.
{figure_rule}
"""


def extract_pdf_images(
    pdf_path: Path,
    image_dir: Path,
    min_width: int = 180,
    min_height: int = 180,
    min_bytes: int = 12_000,
) -> list[dict[str, Any]]:
    """Extract images from PDF for downstream figure analysis."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("WARN: PyMuPDF (fitz) not installed; trying pdfimages CLI fallback.")
        return extract_pdf_images_with_pdfimages(
            pdf_path=pdf_path,
            image_dir=image_dir,
            min_bytes=min_bytes,
        )

    image_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    extracted: list[dict[str, Any]] = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        images = page.get_images(full=True)
        for image_idx, img in enumerate(images, start=1):
            xref = img[0]
            base = doc.extract_image(xref)
            data = base.get("image")
            ext = base.get("ext", "png")
            width = int(base.get("width", 0))
            height = int(base.get("height", 0))
            if not data:
                continue
            if width < min_width or height < min_height or len(data) < min_bytes:
                continue

            file_name = f"figure_p{page_idx + 1:03d}_{image_idx:02d}.{ext}"
            output_path = image_dir / file_name
            output_path.write_bytes(data)

            extracted.append(
                {
                    "figure_id": f"p{page_idx + 1}_{image_idx}",
                    "file_name": file_name,
                    "path": str(output_path),
                    "page": page_idx + 1,
                    "width": width,
                    "height": height,
                    "bytes": len(data),
                }
            )

    doc.close()
    return extracted


def extract_pdf_images_with_pdfimages(
    pdf_path: Path,
    image_dir: Path,
    min_bytes: int = 12_000,
) -> list[dict[str, Any]]:
    """Fallback image extraction using poppler's pdfimages CLI."""
    if not shutil_which("pdfimages"):
        print("WARN: pdfimages not found; skipping image extraction.")
        return []

    image_dir.mkdir(parents=True, exist_ok=True)
    prefix = image_dir / "figure"
    cmd = ["pdfimages", "-all", str(pdf_path), str(prefix)]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="ignore")
        print(f"WARN: pdfimages extraction failed: {detail}")
        return []

    extracted: list[dict[str, Any]] = []
    files = sorted(image_dir.glob("figure-*"))
    for idx, path in enumerate(files, start=1):
        size = path.stat().st_size
        if size < min_bytes:
            continue
        extracted.append(
            {
                "figure_id": f"asset_{idx}",
                "file_name": path.name,
                "path": str(path),
                "page": None,
                "width": None,
                "height": None,
                "bytes": size,
            }
        )
    return extracted


def shutil_which(binary: str) -> str | None:
    """Minimal local wrapper to avoid another import at top-level call sites."""
    import shutil

    return shutil.which(binary)


def convert_pdf_to_markdown(
    pdf_path: Path,
    output_md: Path,
    model: str,
    extract_images: bool = False,
    image_dir: Path | None = None,
    meta_json: Path | None = None,
) -> str:
    """Convert a PDF file to Markdown and optionally extract figure assets."""
    if not pdf_path.exists():
        raise FileNotFoundError(f"Input PDF not found: {pdf_path}")

    output_md.parent.mkdir(parents=True, exist_ok=True)
    figure_dir_name = image_dir.name if image_dir else None

    images: list[dict[str, Any]] = []
    if extract_images:
        if image_dir is None:
            image_dir = output_md.with_suffix("").parent / f"{output_md.stem}_figures"
            figure_dir_name = image_dir.name
        print(f"Extracting images from PDF: {pdf_path}")
        images = extract_pdf_images(pdf_path=pdf_path, image_dir=image_dir)
        print(f"Extracted {len(images)} image(s) to: {image_dir}")

    prompt = build_prompt(figure_dir_name=figure_dir_name if extract_images else None)

    print(f"Converting with {model} (temperature={TEMPERATURE})...")
    md_content = generate_markdown_with_gemini(
        pdf_path=pdf_path,
        prompt=prompt,
        model=model,
        api_keys=API_KEYS,
    )
    if extract_images and images:
        md_content += "\n\n## Extracted Figure Assets\n\n"
        for item in images:
            md_content += (
                f"- FigureAsset `{item['figure_id']}`: "
                f"`{figure_dir_name}/{item['file_name']}` (page {item['page']})\n"
            )

    output_md.write_text(md_content, encoding="utf-8")
    print(f"Saved markdown: {output_md} ({len(md_content)} chars)")

    if meta_json is None:
        meta_json = output_md.with_suffix(".assets.json")
    payload = {
        "input_pdf": str(pdf_path),
        "output_md": str(output_md),
        "model": model,
        "temperature": TEMPERATURE,
        "extracted_images": images,
    }
    meta_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved metadata: {meta_json}")
    return md_content


def extract_text_from_response(payload: dict[str, Any]) -> str:
    """Extract concatenated text parts from Gemini REST response."""
    candidates = payload.get("candidates", [])
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    chunks: list[str] = []
    for part in parts:
        text = part.get("text")
        if text:
            chunks.append(text)
    return "\n".join(chunks).strip()


def is_quota_error(http_code: int, detail: str) -> bool:
    return http_code == 429 or "RESOURCE_EXHAUSTED" in detail or "quota" in detail.lower()


def generate_markdown_with_gemini(
    pdf_path: Path,
    prompt: str,
    model: str,
    api_keys: list[str],
) -> str:
    """Call Gemini REST API directly, without external SDK dependency."""
    pdf_b64 = base64.b64encode(pdf_path.read_bytes()).decode("ascii")
    request_body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "application/pdf", "data": pdf_b64}},
                ]
            }
        ],
        "generationConfig": {"temperature": TEMPERATURE},
    }
    data = json.dumps(request_body).encode("utf-8")
    last_error: str | None = None

    for idx, api_key in enumerate(api_keys, start=1):
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{urllib.parse.quote(model, safe='')}:generateContent?key={urllib.parse.quote(api_key)}"
        )
        request = urllib.request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=540) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = extract_text_from_response(payload)
            if not text:
                raise RuntimeError(
                    f"Gemini API returned no text payload: {json.dumps(payload)[:1000]}"
                )
            if idx > 1:
                print(f"Switched to fallback API key #{idx} successfully.")
            return text
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            last_error = f"Gemini API HTTP {exc.code}: {detail}"
            if idx < len(api_keys) and is_quota_error(exc.code, detail):
                print(f"API key #{idx} quota-exhausted. Trying next key...")
                continue
            raise RuntimeError(last_error) from exc
        except urllib.error.URLError as exc:
            last_error = f"Gemini API connection failed: {exc}"
            raise RuntimeError(last_error) from exc

    raise RuntimeError(last_error or "Gemini API call failed with unknown error.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert PDF to Markdown with Gemini API.")
    parser.add_argument("input_pdf", help="Path to input PDF")
    parser.add_argument("output_md", help="Path to output markdown")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Gemini model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--extract-images",
        action="store_true",
        help="Extract figure image assets from PDF using PyMuPDF.",
    )
    parser.add_argument(
        "--image-dir",
        default=None,
        help="Directory to store extracted images (used with --extract-images).",
    )
    parser.add_argument(
        "--meta-json",
        default=None,
        help="Output JSON metadata path (default: <output>.assets.json).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    image_dir_path = Path(args.image_dir).expanduser().resolve() if args.image_dir else None
    meta_json_path = Path(args.meta_json).expanduser().resolve() if args.meta_json else None

    try:
        convert_pdf_to_markdown(
            pdf_path=Path(args.input_pdf).expanduser().resolve(),
            output_md=Path(args.output_md).expanduser().resolve(),
            model=args.model,
            extract_images=args.extract_images,
            image_dir=image_dir_path,
            meta_json=meta_json_path,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        sys.exit(1)
