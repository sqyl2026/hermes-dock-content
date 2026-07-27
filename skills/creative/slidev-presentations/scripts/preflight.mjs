import { access, readdir, readFile } from "node:fs/promises";
import path from "node:path";

const projectArg = process.argv[2];
if (!projectArg) {
  throw new Error("用法：node preflight.mjs <项目目录>");
}

const projectDir = path.resolve(projectArg);
const publicDir = path.join(projectDir, "public");
const slidesPath = path.join(projectDir, "slides.md");
const packagePath = path.join(projectDir, "package.json");

await access(slidesPath);
await access(packagePath);

const slides = await readFile(slidesPath, "utf8");
if (!slides.trim()) {
  throw new Error(`幻灯片内容为空：${slidesPath}`);
}

const placeholderTokens = [
  "[演示类型 · 日期]",
  "[演示标题]",
  "[一句话说明这套演示的核心价值]",
  "[章节标题]",
  "[章节推进说明]",
  "[本页结论]",
  "[支持结论的证据]",
  "[视觉内容]",
  "[视觉说明]",
  "[关键数字]",
  "[数字代表的含义]",
  "[数字口径、比较对象和来源]",
  "[结束行动]",
  "[下一步说明]",
];
const placeholders = placeholderTokens.filter((token) => slides.includes(token));
placeholders.push(...(slides.match(/\b(?:TODO|TBD|Lorem ipsum)\b/gi) ?? []));
if (placeholders.length > 0) {
  throw new Error(`仍有占位内容：${[...new Set(placeholders)].join("、")}`);
}

const sourceFiles = await collectSourceFiles(projectDir);
const remoteFindings = [];
const localAssets = new Map();

for (const filePath of sourceFiles) {
  const content = await readFile(filePath, "utf8");
  const relativePath = path.relative(projectDir, filePath);

  collectMatches(content, /!\[[^\]]*\]\(\s*(https?:\/\/[^)\s]+)[^)]*\)/gi, remoteFindings, relativePath);
  collectMatches(content, /\b(?:src|poster)\s*=\s*["'](https?:\/\/[^"']+)["']/gi, remoteFindings, relativePath);
  collectMatches(content, /url\(\s*["']?(https?:\/\/[^)'"\s]+)["']?\s*\)/gi, remoteFindings, relativePath);
  collectMatches(content, /^\s*(?:background|favicon)\s*:\s*["']?(https?:\/\/[^\s"']+)/gim, remoteFindings, relativePath);

  collectAssets(content, /!\[[^\]]*\]\(\s*\/([^)\s]+)[^)]*\)/g, localAssets, relativePath);
  collectAssets(content, /\b(?:src|poster)\s*=\s*["']\/([^"']+)["']/gi, localAssets, relativePath);
  collectAssets(content, /url\(\s*["']?\/([^)'"\s]+)["']?\s*\)/gi, localAssets, relativePath);
  collectAssets(content, /^\s*(?:background|favicon)\s*:\s*["']?\/([^\s"']+)/gim, localAssets, relativePath);

  if (filePath.endsWith(".md")) {
    collectReferenceImages(content, remoteFindings, localAssets, relativePath);
  }
}

if (remoteFindings.length > 0) {
  const details = [...new Set(remoteFindings.map(({ url, file }) => `${file}: ${redactUrl(url)}`))];
  throw new Error(`请先把远程图片下载到 public/：${details.join("、")}`);
}

for (const [asset, files] of localAssets) {
  const cleanAsset = asset.split(/[?#]/, 1)[0];
  const assetPath = path.resolve(publicDir, cleanAsset);
  if (assetPath !== publicDir && !assetPath.startsWith(`${publicDir}${path.sep}`)) {
    throw new Error(`本地素材路径越过 public/：/${asset}（${[...files].join("、")}）`);
  }
  try {
    await access(assetPath);
  } catch (error) {
    if (error.code === "ENOENT") {
      throw new Error(`本地素材不存在：/${asset}（${[...files].join("、")}）`);
    }
    throw error;
  }
}

console.log(`预检通过：${slidesPath}`);

async function collectSourceFiles(rootDir) {
  const sourceExtensions = new Set([".css", ".html", ".js", ".jsx", ".md", ".ts", ".tsx", ".vue"]);
  const skippedDirectories = new Set([".git", "dist", "node_modules", "public"]);
  const files = [];

  async function walk(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const entryPath = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        if (!skippedDirectories.has(entry.name)) {
          await walk(entryPath);
        }
      } else if (entry.isFile() && sourceExtensions.has(path.extname(entry.name))) {
        files.push(entryPath);
      }
    }
  }

  await walk(rootDir);
  return files;
}

function collectMatches(content, pattern, findings, file) {
  for (const match of content.matchAll(pattern)) {
    findings.push({ url: match[1], file });
  }
}

function collectAssets(content, pattern, assets, file) {
  for (const match of content.matchAll(pattern)) {
    const files = assets.get(match[1]) ?? new Set();
    files.add(file);
    assets.set(match[1], files);
  }
}

function collectReferenceImages(content, remoteFindings, localAssets, file) {
  const references = new Map();
  for (const match of content.matchAll(/^\s*\[([^\]]+)\]:\s*(?:<([^>]+)>|(\S+))/gm)) {
    references.set(match[1].toLowerCase(), match[2] ?? match[3]);
  }
  for (const match of content.matchAll(/!\[([^\]]*)\]\[([^\]]*)\]/g)) {
    const key = (match[2] || match[1]).toLowerCase();
    const target = references.get(key);
    if (!target) {
      continue;
    }
    if (/^https?:\/\//i.test(target)) {
      remoteFindings.push({ url: target, file });
    } else if (target.startsWith("/")) {
      const files = localAssets.get(target.slice(1)) ?? new Set();
      files.add(file);
      localAssets.set(target.slice(1), files);
    }
  }
}

function redactUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    return `${url.host}${url.pathname}`;
  } catch {
    return "远程地址";
  }
}
