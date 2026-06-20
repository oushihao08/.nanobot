#!/usr/bin/env python3
import argparse
import datetime
import hashlib
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    import fitz
except ImportError:
    fitz = None

try:
    from pdf2image import convert_from_path
except ImportError:
    convert_from_path = None

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from qwen_ocr import call_qwen_ocr, configured_model_candidates, load_config, read_provider  # noqa: E402


WATERMARK_PATTERNS = [
    re.compile(r"^[A-Za-z0-9]{3,12}[_-]\s*20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}.*$"),
    re.compile(r"^20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}\s+\d{1,2}[:：]\d{1,2}.*$"),
    re.compile(r"^[0-9A-Za-z]{4,8}[!！]?$"),
    re.compile(r"^<p>\s*(20\d{2}[-/.]\d{1,2}[-/.]?\d{0,2})\s*</p>$"),
    re.compile(r"^\$\\text\s*\{\s*(民|号)\s*\}\$$"),
    re.compile(r"^<div class=\"image\">\s*(<img/>)?\s*</div>$"),
    re.compile(r"^</?(html|body)>$"),
]


def fail(message, code=1):
    print(message, file=sys.stderr)
    raise SystemExit(code)


def default_config_path():
    return os.environ.get("NANOBOT_CONFIG", "~/.nanobot/config.json")


def default_workdir():
    return os.environ.get("QWEN_OCR_WORKDIR", "~/.nanobot/workspace/tmp_outputs/qwen-ocr-pdf")


def is_remote_url(value):
    return re.match(r"^https?://", value or "", re.IGNORECASE) is not None


def safe_name(value, fallback="document"):
    stem = os.path.splitext(os.path.basename(value))[0]
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")
    return cleaned[:80] or fallback


def safe_remote_pdf_name(url):
    parsed = urllib.parse.urlparse(url)
    path_name = os.path.basename(parsed.path) or "remote.pdf"
    stem, ext = os.path.splitext(path_name)
    if ext.lower() != ".pdf":
        ext = ".pdf"
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"{safe_name(stem, 'remote-pdf')}-{url_hash}{ext}"


def download_remote_pdf(url, workdir):
    input_dir = os.path.join(workdir, "inputs")
    os.makedirs(input_dir, exist_ok=True)
    output_path = os.path.join(input_dir, safe_remote_pdf_name(url))
    request = urllib.request.Request(url, headers={"User-Agent": "nanobot-qwen-ocr/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            with open(output_path, "wb") as file:
                shutil.copyfileobj(response, file)
    except urllib.error.URLError as error:
        fail(f"Failed to download PDF URL: {error}")
    return output_path


def short_file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]


def create_run_dir(workdir, pdf_path):
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    pdf_key = f"{safe_name(pdf_path)}-{short_file_hash(pdf_path)}"
    run_dir = os.path.join(workdir, "runs", f"{pdf_key}-{timestamp}-{os.getpid()}")
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


def make_logger(log_path):
    def log(message):
        line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {message}"
        print(line, file=sys.stderr, flush=True)
        with open(log_path, "a", encoding="utf-8") as file:
            file.write(line + "\n")

    return log


def page_range(value, page_count):
    if not value:
        return list(range(page_count))
    pages = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if start > end:
                fail(f"Invalid page range: {part}")
            pages.update(range(start - 1, end))
        else:
            pages.add(int(part) - 1)
    selected = sorted(p for p in pages if 0 <= p < page_count)
    if not selected:
        fail("No valid pages selected.")
    return selected


def is_mostly_boxes(line):
    chars = [char for char in line.strip() if not char.isspace()]
    if not chars:
        return False
    box_count = sum(1 for char in chars if char in {"□", "▢", "■", "▣"})
    return box_count >= 3 and box_count / len(chars) >= 0.7


def is_dense_repeated_short_line(line, page_line_counts):
    compact = re.sub(r"\s+", "", line)
    if len(compact) < 4 or len(compact) > 30:
        return False
    if page_line_counts.get(compact, 0) < 5:
        return False
    # Avoid deleting normal prose repeated a few times; this targets watermark grids.
    return not re.search(r"[，。；：、,.!?！？]", compact)


def normalize_ocr_markup(text):
    text = re.sub(r"```(?:html|json|text)?", "", text)
    text = text.replace("```", "")
    return text


def watermark_noise_score(text):
    normalized = normalize_ocr_markup(text)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    compact_lines = [re.sub(r"\s+", "", line) for line in lines]
    counts = {}
    for line in compact_lines:
        counts[line] = counts.get(line, 0) + 1

    score = 0
    score += normalized.count("□") // 5
    score += normalized.count("<p>") + normalized.count("<div")
    score += normalized.count("$\\text")
    for line, count in counts.items():
        if 4 <= len(line) <= 30 and count >= 5 and not re.search(r"[，。；：、,.!?！？]", line):
            score += count
    return score


def is_low_information_text(text):
    compact = re.sub(r"\s+", "", normalize_ocr_markup(text))
    if not compact:
        return True
    ellipsis_count = compact.count("…")
    return len(compact) < 80 or (ellipsis_count >= 10 and ellipsis_count / max(len(compact), 1) > 0.2)


def clean_watermark_lines(text):
    text = normalize_ocr_markup(text)
    compact_lines = [
        re.sub(r"\s+", "", raw_line.strip())
        for raw_line in text.splitlines()
        if raw_line.strip()
    ]
    page_line_counts = {}
    for compact in compact_lines:
        page_line_counts[compact] = page_line_counts.get(compact, 0) + 1

    cleaned = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            cleaned.append("")
            continue
        compact = re.sub(r"\s+", "", line)
        if is_mostly_boxes(line):
            continue
        if is_dense_repeated_short_line(line, page_line_counts):
            continue
        if any(pattern.match(compact) or pattern.match(line) for pattern in WATERMARK_PATTERNS):
            continue
        cleaned.append(raw_line.rstrip())
    return "\n".join(cleaned).strip()


def render_page_with_fitz(pdf, page_index, output_dir, dpi):
    page = pdf[page_index]
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    path = os.path.join(output_dir, f"page_{page_index + 1:04d}.png")
    pix.save(path)
    return path


def render_page_with_pdf2image(pdf_path, page_index, output_dir, dpi):
    images = convert_from_path(
        pdf_path,
        dpi=dpi,
        first_page=page_index + 1,
        last_page=page_index + 1,
        fmt="png",
        single_file=True,
    )
    if not images:
        fail(f"Failed to render page {page_index + 1}.")
    path = os.path.join(output_dir, f"page_{page_index + 1:04d}.png")
    images[0].save(path, "PNG")
    return path


def preprocess_image_for_ocr(image_path, mode):
    if mode == "none":
        return image_path
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("preprocess skipped: cv2/numpy unavailable", file=sys.stderr)
        return image_path

    image = cv2.imread(image_path)
    if image is None:
        return image_path

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    if mode == "watermark":
        cleaned = gray.copy()
        threshold = int(os.environ.get("QWEN_OCR_WATERMARK_THRESHOLD", "130"))
        cleaned[cleaned > threshold] = 255
        kernel = np.ones((2, 2), np.uint8)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel, iterations=1)
        output_path = image_path.replace(".png", f".{mode}.png")
        cv2.imwrite(output_path, cleaned)
        return output_path

    # Normalize uneven paper/background first; this suppresses pale repeated watermarks
    # while preserving darker foreground text for OCR.
    background = cv2.GaussianBlur(gray, (0, 0), sigmaX=25, sigmaY=25)
    normalized = cv2.divide(gray, background, scale=255)
    normalized = cv2.normalize(normalized, None, 0, 255, cv2.NORM_MINMAX)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(normalized)

    if mode == "threshold":
        cleaned = cv2.adaptiveThreshold(
            enhanced,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            41,
            13,
        )
    elif mode == "clean":
        _, otsu = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        adaptive = cv2.adaptiveThreshold(
            enhanced,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            41,
            11,
        )
        cleaned = cv2.bitwise_and(otsu, adaptive)
        kernel = np.ones((2, 2), np.uint8)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel, iterations=1)
    else:
        fail(f"Unknown preprocess mode: {mode}")

    output_path = image_path.replace(".png", f".{mode}.png")
    cv2.imwrite(output_path, cleaned)
    return output_path


def get_page_count(pdf_path):
    if fitz is not None:
        pdf = fitz.open(pdf_path)
        return pdf, pdf.page_count
    if convert_from_path is None:
        fail("Missing PDF renderer: install PyMuPDF/fitz or pdf2image in the runtime environment.")
    try:
        from pdf2image.pdf2image import pdfinfo_from_path
        return None, int(pdfinfo_from_path(pdf_path).get("Pages", 0))
    except Exception as error:
        fail(f"Failed to inspect PDF page count: {error}")


def main():
    parser = argparse.ArgumentParser(description="OCR local PDF through qwen3.5-ocr page by page.")
    parser.add_argument("--config", default=default_config_path())
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--pages", help="Page range, 1-based. Example: 1,3-5")
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument(
        "--preprocess",
        choices=["auto", "watermark", "clean", "threshold", "none"],
        default="auto",
        help="Image preprocessing before Qwen OCR. auto uses normal OCR first, then retries watermark mode only for noisy pages.",
    )
    parser.add_argument("--keep-images", action="store_true")
    parser.add_argument("--no-clean-watermarks", action="store_true")
    parser.add_argument(
        "--workdir",
        default=default_workdir(),
    )
    parser.add_argument(
        "--prompt",
        default=(
            "请识别这页扫描文档中的正文文字。"
            "忽略水印、重复背景水印、页眉页脚中的时间戳、重复编号、背景干扰和明显非正文内容。"
            "如果图片中仍残留浅色或斜向重复文字，请视为水印，不要输出。"
            "不要输出 HTML、Markdown 代码块、LaTeX 包裹文本或图片占位标签。"
            "保留自然段、标题、案号、表格中的文字。只输出识别出的正文。"
        ),
    )
    args = parser.parse_args()

    output_path = os.path.abspath(os.path.expanduser(args.output))
    config_path = os.path.abspath(os.path.expanduser(args.config))
    workdir = os.path.abspath(os.path.expanduser(args.workdir))
    os.makedirs(workdir, exist_ok=True)

    if is_remote_url(args.pdf):
        pdf_path = download_remote_pdf(args.pdf, workdir)
    else:
        pdf_path = os.path.abspath(os.path.expanduser(args.pdf))

    if not os.path.exists(pdf_path):
        fail(f"PDF not found: {pdf_path}")
    if not pdf_path.lower().endswith(".pdf"):
        fail("Input is not a PDF.")

    config = load_config(config_path)
    api_key, api_base = read_provider(config)
    model_candidates = configured_model_candidates(config)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    pdf, page_count = get_page_count(pdf_path)
    selected_pages = page_range(args.pages, page_count)
    failures = []
    page_results = []

    run_dir = create_run_dir(workdir, pdf_path)
    log_path = os.path.join(run_dir, "progress.log")
    log = make_logger(log_path)
    image_root = os.path.join(run_dir, "images")
    os.makedirs(image_root, exist_ok=True)

    log(f"run_dir={run_dir}")
    log(f"pdf={pdf_path}")
    log(f"output={output_path}")
    log(f"pages={len(selected_pages)}/{page_count}")
    log(f"dpi={args.dpi} preprocess={args.preprocess}")

    try:
        for page_index in selected_pages:
            page_no = page_index + 1
            page_started_at = time.monotonic()
            try:
                log(f"page {page_no}/{page_count} render start")
                if pdf is not None:
                    image_path = render_page_with_fitz(pdf, page_index, image_root, args.dpi)
                else:
                    image_path = render_page_with_pdf2image(pdf_path, page_index, image_root, args.dpi)
                log(f"page {page_no}/{page_count} render ok image={image_path}")
                if args.preprocess == "auto":
                    log(f"page {page_no}/{page_count} ocr start")
                    text, usage, model_name = call_qwen_ocr(api_key, api_base, image_path, args.prompt, model_candidates)
                    original_low_info = is_low_information_text(text)
                    if watermark_noise_score(text) >= 8 or original_low_info:
                        log(f"page {page_no}/{page_count} watermark retry start")
                        retry_image_path = preprocess_image_for_ocr(image_path, "watermark")
                        retry_text, retry_usage, retry_model_name = call_qwen_ocr(
                            api_key, api_base, retry_image_path, args.prompt, model_candidates
                        )
                        retry_len = len(re.sub(r"\s+", "", normalize_ocr_markup(retry_text)))
                        original_len = len(re.sub(r"\s+", "", normalize_ocr_markup(text)))
                        if (original_low_info and retry_len > original_len and retry_len >= 20) or (
                            retry_len > original_len * 1.2 and retry_len >= 40
                        ):
                            text, usage, model_name = retry_text, retry_usage, retry_model_name
                        else:
                            log(f"page {page_no}/{page_count} watermark retry discarded due to lower information")
                else:
                    log(f"page {page_no}/{page_count} preprocess start mode={args.preprocess}")
                    image_path = preprocess_image_for_ocr(image_path, args.preprocess)
                    log(f"page {page_no}/{page_count} ocr start image={image_path}")
                    text, usage, model_name = call_qwen_ocr(api_key, api_base, image_path, args.prompt, model_candidates)
                cleaned = text.strip() if args.no_clean_watermarks else clean_watermark_lines(text)
                page_results.append(f"\n\n===== 第 {page_no} 页 =====\n\n{cleaned}\n")
                usage_text = f" usage={usage}" if usage else ""
                elapsed = time.monotonic() - page_started_at
                log(f"page {page_no}/{page_count} ok elapsed={elapsed:.1f}s model={model_name}{usage_text}")
            except Exception as error:
                failures.append((page_no, str(error)))
                elapsed = time.monotonic() - page_started_at
                log(f"page {page_no}/{page_count} failed elapsed={elapsed:.1f}s error={error}")

        with open(output_path, "w", encoding="utf-8") as file:
            file.write("\n".join(page_results).strip())
            file.write("\n")

        print(output_path)
        log(f"output_written={output_path}")
        if failures:
            log("failed_pages=" + ",".join(str(page) for page, _ in failures))
            for page, error in failures:
                log(f"page {page}: {error}")
    finally:
        if pdf is not None:
            pdf.close()
        if args.keep_images:
            log(f"images_kept={image_root}")
        else:
            shutil.rmtree(image_root, ignore_errors=True)
            log(f"images_removed={image_root}")
        log(f"log={log_path}")


if __name__ == "__main__":
    main()
