#!/usr/bin/env python3
import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.request
from collections import OrderedDict


SUPPORTED_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp", ".heic"}
DEFAULT_MODEL_CANDIDATES = ("qwen3.5-ocr", "qwen-vl-ocr")


def load_config(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def fail(message, code=1):
    print(message, file=sys.stderr)
    raise SystemExit(code)


def read_provider(config):
    providers = config.get("providers") or {}
    dashscope = providers.get("dashscope") or {}
    api_key = dashscope.get("apiKey")
    api_base = dashscope.get("apiBase")
    if not api_key:
        fail("Missing providers.dashscope.apiKey in config.")
    if not api_base:
        fail("Missing providers.dashscope.apiBase in config.")
    return api_key, api_base.rstrip("/")


def default_config_path():
    return os.environ.get("NANOBOT_CONFIG", "~/.nanobot/config.json")


def configured_model_candidates(config):
    values = []
    preset = (config.get("modelPresets") or {}).get("qwen3.5-ocr") or {}
    preset_model = preset.get("model")
    env_model = os.environ.get("QWEN_OCR_MODEL")
    for value in (env_model, preset_model, *DEFAULT_MODEL_CANDIDATES):
        if value:
            values.append(value)
    return tuple(OrderedDict.fromkeys(values))


def is_remote_url(value):
    return re.match(r"^https?://", value or "", re.IGNORECASE) is not None


def detect_mime(image_path):
    ext = os.path.splitext(image_path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        fail(f"Unsupported image extension: {ext}. This skill supports images only, not PDF.")
    mime = mimetypes.guess_type(image_path)[0]
    if not mime:
        if ext in {".jpg", ".jpeg"}:
            mime = "image/jpeg"
        elif ext == ".png":
            mime = "image/png"
        else:
            mime = "application/octet-stream"
    return mime


def build_image_url(image_source):
    if is_remote_url(image_source):
        return image_source

    image_path = os.path.abspath(os.path.expanduser(image_source))
    if not os.path.exists(image_path):
        fail(f"Image not found: {image_path}")

    mime = detect_mime(image_path)
    with open(image_path, "rb") as file:
        b64 = base64.b64encode(file.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def build_payload(model, image_source, prompt):
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": build_image_url(image_source)},
                        "min_pixels": 32 * 32 * 3,
                        "max_pixels": 32 * 32 * 8192,
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "max_tokens": 8192,
    }
    return payload


def is_unsupported_image_error(detail):
    return "Invalid value: image." in detail and "image_url" in detail


def post_chat_completion(api_key, api_base, payload):
    request = urllib.request.Request(
        api_base + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {detail}") from error


def parse_response(body):
    try:
        return body["choices"][0]["message"]["content"], body.get("usage"), body.get("model")
    except (KeyError, IndexError, TypeError):
        fail("Unexpected response: " + json.dumps(body, ensure_ascii=False)[:2000])


def call_qwen_ocr(api_key, api_base, image_source, prompt, model_candidates):
    errors = []
    for model in model_candidates:
        payload = build_payload(model, image_source, prompt)
        try:
            body = post_chat_completion(api_key, api_base, payload)
            text, usage, response_model = parse_response(body)
            return text, usage, response_model or model
        except RuntimeError as error:
            detail = str(error)
            errors.append((model, detail))
            if is_unsupported_image_error(detail):
                continue
            fail(detail)
    error_summary = " | ".join(f"{model}: {detail}" for model, detail in errors)
    fail(f"All Qwen OCR models failed. {error_summary}")


def main():
    parser = argparse.ArgumentParser(description="OCR local or remote image with qwen3.5-ocr.")
    parser.add_argument("--config", default=default_config_path())
    parser.add_argument("--image", required=True)
    parser.add_argument("--output")
    parser.add_argument(
        "--prompt",
        default="请识别图片中的全部可见文字，只输出识别结果。不要编造。",
    )
    args = parser.parse_args()

    config = load_config(os.path.abspath(os.path.expanduser(args.config)))
    api_key, api_base = read_provider(config)
    model_candidates = configured_model_candidates(config)
    text, usage, response_model = call_qwen_ocr(api_key, api_base, args.image, args.prompt, model_candidates)

    if args.output:
        output_path = os.path.abspath(os.path.expanduser(args.output))
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as file:
            file.write(text)
            file.write("\n")
        print(output_path)
    else:
        print(text)

    print(json.dumps({"model": response_model}, ensure_ascii=False), file=sys.stderr)
    if usage:
        print(json.dumps({"usage": usage}, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    main()
