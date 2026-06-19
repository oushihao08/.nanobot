---
name: qwen-ocr
description: MUST use this skill whenever the user mentions recognizing, extracting, reading, parsing, identifying, transcribing, or OCR for images or PDFs, including close synonyms and colloquial variants. Trigger examples include 识别图片, 提取图片, 读图, 看图取字, 图片识字, 图片转文字, 图片文字提取, OCR图片, 识别pdf, 提取pdf, 读pdf, 看pdf取字, PDF识字, PDF转文字, PDF文字提取, OCR, 扫描件识别, 文档识别. This skill routes OCR work through Alibaba Bailian Qwen OCR and avoids local OCR tools such as tesseract, pdftotext, or ad-hoc package installs.
---

# Qwen OCR Skill

Use this skill for image/PDF OCR routing.

This skill is the formal implementation of these capabilities:

- 识别图片
- 识别 PDF
- 提取图片文本
- 提取 PDF 文本
- 识别图片文本
- 识别 PDF 文本

## When To Use

- User asks to recognize text in a local image or a remote image URL.
- User asks to extract content from an image.
- User asks to recognize text in a PDF.
- User asks to extract content from a PDF.
- User says any of: `识别图片`, `提取图片`, `读图`, `看图取字`, `图片识字`, `图片转文字`, `图片文字提取`, `OCR 图片`, `识别 pdf`, `提取 pdf`, `读 pdf`, `看 pdf 取字`, `PDF识字`, `PDF转文字`, `PDF文字提取`, `OCR`, `扫描件识别`, `文档识别`.
- User wants to use `qwen3.5-ocr`.
- User wants stable OCR through Alibaba Bailian instead of guessing from a file path.

## Boundaries

- Do not use `pdftotext`, `tesseract`, OCRmyPDF, or `pip install`.
- Do not guess image content from the path.
- Do not answer OCR tasks by visually describing the image from `read_file` output.
- Do not re-open the image for manual interpretation before running the approved OCR script.
- Do not supplement OCR output with your own visual guessing.
- Do not print API keys.
- PDF tasks must still start from this skill. For local PDFs, use the controlled PDF-to-image + Qwen OCR script. Do not use random local OCR tools.
- Do not create new OCR scripts in `tmp_outputs` or any scratch directory.
- Do not reuse old scratch scripts such as `batch_ocr.py` or `batch_ocr_*.py`.
- Do not use `spawn` or subagents for OCR. Run the approved script directly and wait/poll the process.
- Do not continue from old session memory or old scratch state. Current filesystem and this skill file are authoritative.
- If the approved script fails, stop and report the failure; do not invent a replacement script.
- Request debugging must always compare against the official `qwen3.5-ocr` request shape first.
- If `qwen3.5-ocr` returns the known OpenAI-compatible image 400 on the current workspace endpoint, the approved fallback is `qwen-vl-ocr` with the same request shape.
- The only approved scripts are:
  - `scripts/qwen_ocr.py` for images.
  - `scripts/qwen_ocr_pdf.py` for PDFs.
  - `scripts/qwen_ocr_openai.mjs` only when Node OpenAI SDK is available.
- Final reply for OCR tasks must be minimal:
  - Default: return only recognized text itself.
  - Do not append image description, content summary, interpretation, or visual analysis.
  - Do not expose chain-of-thought, tool steps, script steps, fallback explanation, model name, or token usage unless user explicitly asks.
  - If user requested file export, return recognized text plus output path only when needed.

Official request shape:
- `model: qwen3.5-ocr`
- `messages[0].content[0].type: image_url`
- `messages[0].content[0].image_url.url: remote URL or local data URL`
- `messages[0].content[1].type: text`

## Image Command

```bash
python3 scripts/qwen_ocr.py \
  --config ~/.nanobot/config.json \
  --image "/absolute/path/to/image.png"
```

Remote image URL is also allowed:

```bash
python3 scripts/qwen_ocr.py \
  --config ~/.nanobot/config.json \
  --image "https://example.com/example.png"
```

## Optional Output File

```bash
python3 scripts/qwen_ocr.py \
  --config ~/.nanobot/config.json \
  --image "/absolute/path/to/image.png" \
  --output "/absolute/path/to/result.txt"
```

## PDF Command

```bash
python3 scripts/qwen_ocr_pdf.py \
  --config ~/.nanobot/config.json \
  --pdf "/absolute/path/to/input.pdf" \
  --output "/absolute/path/to/result.txt"
```

If the user explicitly asks to remove watermarks, prefer:

```bash
--preprocess auto
```

Quality rule:

- `--preprocess auto`: default and recommended. It runs normal OCR first, then retries watermark preprocessing only for noisy pages.
- `--preprocess none`: best for normal pages and highest text fidelity.
- `--preprocess watermark`: force suppresses pale repeated background watermarks before OCR, but may lose faint form text. Use only for visibly watermark-dominated pages, not whole documents by default.

For a small verification run:

```bash
python3 scripts/qwen_ocr_pdf.py \
  --config ~/.nanobot/config.json \
  --pdf "/absolute/path/to/input.pdf" \
  --output "/absolute/path/to/result.txt" \
  --pages 1-2
```

## Expected Agent Behavior

1. If the user asks for image recognition/extraction, use this skill.
2. If the user asks for PDF recognition/extraction, use this skill first and do not fall back to `pdftotext`, `tesseract`, or package installation.
3. Check whether the input is image or PDF.
4. For image input, use `qwen_ocr.py` and keep the request shape aligned with the official `qwen3.5-ocr` example.
5. For remote image URLs, pass the URL directly. For local images, convert them to a data URL and keep the rest of the request shape unchanged.
6. For local PDF input, call `qwen_ocr_pdf.py`. It may render PDF pages to images, but OCR recognition must be done through `qwen3.5-ocr`.
7. If the user says 不含水印, 去水印, remove watermark, or similar, pass `--preprocess auto`.
8. For full PDF input, call `qwen_ocr_pdf.py` directly with the requested output path and wait for completion.
9. If tempted to write a new OCR script, stop and use the approved script instead.
10. If the approved script fails, report the error and do not create a replacement implementation.
11. Return only the OCR result itself by default. If output path was explicitly requested and user needs confirmation, return result plus path; otherwise do not add explanation.
12. For OCR tasks, do not call `read_file` on the target image just to inspect it manually unless the approved OCR script has already failed and the user explicitly asks for visual analysis instead of OCR.
