#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

let OpenAI;
try {
  ({ default: OpenAI } = await import("openai"));
} catch {
  console.error("Missing dependency: openai. Install it in the runtime environment or use qwen_ocr.py.");
  process.exit(1);
}

const SUPPORTED_EXTENSIONS = new Set([".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp", ".heic"]);

function parseArgs(argv) {
  const args = {
    config: process.env.NANOBOT_CONFIG || "~/.nanobot/config.json",
    prompt: "请识别图片中的全部可见文字，只输出识别结果。不要编造。",
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--config") {
      args.config = value;
      i += 1;
    } else if (key === "--image") {
      args.image = value;
      i += 1;
    } else if (key === "--output") {
      args.output = value;
      i += 1;
    } else if (key === "--prompt") {
      args.prompt = value;
      i += 1;
    } else if (key === "--help" || key === "-h") {
      printHelp();
      process.exit(0);
    } else {
      console.error(`Unknown argument: ${key}`);
      printHelp();
      process.exit(1);
    }
  }
  if (!args.image) {
    console.error("Missing required argument: --image");
    printHelp();
    process.exit(1);
  }
  return args;
}

function printHelp() {
  const currentFile = fileURLToPath(import.meta.url);
  console.log(`Usage:
node ${currentFile} --config ~/.nanobot/config.json --image /path/to/image.png [--output /path/to/result.txt]
`);
}

function readConfig(configPath) {
  return JSON.parse(fs.readFileSync(configPath, "utf8"));
}

function expandHome(inputPath) {
  if (inputPath === "~") return process.env.HOME || inputPath;
  if (inputPath.startsWith("~/")) return path.join(process.env.HOME || "", inputPath.slice(2));
  return inputPath;
}

function mimeForImage(imagePath) {
  const ext = path.extname(imagePath).toLowerCase();
  if (!SUPPORTED_EXTENSIONS.has(ext)) {
    throw new Error(`Unsupported image extension: ${ext}. This skill supports images only, not PDF.`);
  }
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".png") return "image/png";
  if (ext === ".bmp") return "image/bmp";
  if (ext === ".tif" || ext === ".tiff") return "image/tiff";
  if (ext === ".webp") return "image/webp";
  if (ext === ".heic") return "image/heic";
  return "application/octet-stream";
}

async function main() {
  const args = parseArgs(process.argv);
  const imagePath = path.resolve(expandHome(args.image));
  const configPath = path.resolve(expandHome(args.config));

  if (!fs.existsSync(imagePath)) {
    throw new Error(`Image not found: ${imagePath}`);
  }

  const config = readConfig(configPath);
  const dashscope = config.providers?.dashscope;
  if (!dashscope?.apiKey) {
    throw new Error("Missing providers.dashscope.apiKey in config.");
  }
  if (!dashscope?.apiBase) {
    throw new Error("Missing providers.dashscope.apiBase in config.");
  }

  const client = new OpenAI({
    apiKey: dashscope.apiKey,
    baseURL: dashscope.apiBase,
  });

  const mime = mimeForImage(imagePath);
  const imageBase64 = fs.readFileSync(imagePath).toString("base64");

  const completion = await client.chat.completions.create({
    model: "qwen-vl-ocr",
    messages: [
      {
        role: "user",
        content: [
          {
            type: "image_url",
            image_url: {
              url: `data:${mime};base64,${imageBase64}`,
            },
            min_pixels: 32 * 32 * 3,
            max_pixels: 32 * 32 * 8192,
          },
          {
            type: "text",
            text: args.prompt,
          },
        ],
      },
    ],
    max_tokens: 8192,
  });

  const text = completion.choices?.[0]?.message?.content ?? "";
  if (args.output) {
    const outputPath = path.resolve(args.output);
    fs.mkdirSync(path.dirname(outputPath), { recursive: true });
    fs.writeFileSync(outputPath, `${text}\n`, "utf8");
    console.log(outputPath);
    return;
  }
  console.log(text);
}

main().catch((error) => {
  console.error(`错误信息: ${error?.message || error}`);
  process.exit(1);
});
