#!/usr/bin/env node

const fsp = require("node:fs/promises");
const fsSync = require("node:fs");
const path = require("node:path");
const process = require("node:process");

const DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com";
const DEFAULT_DOWNLOAD_ROOT = process.env.HERMES_DOCK_PROFILE_HOME
  ? path.join(process.env.HERMES_DOCK_PROFILE_HOME, "outputs", "seedance")
  : "seedance-downloads";
const DEFAULT_POLL_INTERVAL_MS = 5000;
const DEFAULT_TIMEOUT_MS = 20 * 60 * 1000;
const TERMINAL_STATUSES = new Set(["succeeded", "failed", "expired", "cancelled"]);

// API Key 只从当前 profile 的 ARK_AGENT_PLAN_API_KEY 读取。

const MIME_BY_EXTENSION = new Map([
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".png", "image/png"],
  [".webp", "image/webp"],
  [".bmp", "image/bmp"],
  [".tiff", "image/tiff"],
  [".tif", "image/tiff"],
  [".gif", "image/gif"],
  [".heic", "image/heic"],
  [".heif", "image/heif"],
  [".mp4", "video/mp4"],
  [".mov", "video/quicktime"],
  [".webm", "video/webm"],
  [".mp3", "audio/mpeg"],
  [".wav", "audio/wav"],
  [".m4a", "audio/mp4"],
  [".aac", "audio/aac"],
  [".flac", "audio/flac"],
  [".ogg", "audio/ogg"],
]);

async function main() {
  const parsed = parseArgv(process.argv.slice(2));
  const command = parsed.command || "run";
  const options = parsed.options;

  if (options.help || command === "help") {
    printHelp();
    return;
  }

  switch (command) {
    case "run":
      await handleRun(options);
      return;
    case "create":
      await handleCreate(options);
      return;
    case "get":
      await handleGet(options);
      return;
    case "list":
      await handleList(options);
      return;
    case "delete":
      await handleDelete(options);
      return;
    case "download":
      await handleDownload(options);
      return;
    default:
      throw new Error(`Unknown command: ${command}`);
  }
}

function printHelp() {
  console.log(`
Seedance video task helper for Volcengine Ark APIs.

Default command: run

Usage:
  node seedance-video.js [run] [options]
  node seedance-video.js create [options]
  node seedance-video.js get --task-id <id> [options]
  node seedance-video.js list [options]
  node seedance-video.js delete --task-id <id>
  node seedance-video.js download (--task-file <file> | --task-id <id>) [options]

Common options:
  --base-url <url>               Override base URL (default: ${DEFAULT_BASE_URL})
  --model <id>                   Model ID (required unless payload JSON already contains model)
  --payload-file <file>          Load raw request JSON
  --prompt <text>                Add a text content item
  --image-url <url>              Add an image_url content item (repeatable)
  --image-file <path>            Add a local image as a base64 data URL (repeatable)
  --video-url <url>              Add a video_url content item (repeatable)
  --video-file <path>            Add a local video as a base64 data URL (repeatable)
  --audio-url <url>              Add an audio_url content item (repeatable)
  --audio-file <path>            Add a local audio as a base64 data URL (repeatable)
  --draft-task-id <id>           Add a draft_task content item (repeatable)
  --resolution <value>           e.g. 720p, 1080p, 4k
  --ratio <value>                e.g. 16:9, 9:16, 1:1
  --duration <seconds>           Video duration
  --frames <count>               Frame count
  --seed <number>                Sampling seed
  --camera-fixed <bool>          true / false
  --watermark <bool>             true / false
  --return-last-frame <bool>     true / false
  --callback-url <url>           Ark callback URL
  --draft <bool>                 Pass through draft mode if supported
  --download-dir <dir>           Where to save outputs
  --poll-interval <seconds>      Poll interval (default: 5)
  --timeout-sec <seconds>        Wait timeout (default: 1200)
  --wait                         Wait after create

List filters:
  --page-num <number>
  --page-size <number>
  --filter-status <status>
  --filter-model <model>
  --filter-task-id <id>          Repeatable

Download options:
  --task-file <path>             Load a saved task JSON and download outputs

Examples:
  node seedance-video.js --prompt "Rainy city at night, slow camera push" --download-dir "./out"
  node seedance-video.js --model "doubao-seedance-2-0-260128" --prompt "Rainy city at night, slow camera push" --download-dir "./out"
  node seedance-video.js create --model "doubao-seedance-2.0-mini" --payload-file "./payload.json"
  node seedance-video.js get --task-id cgt-xxxx --download-dir "./out"
  `.trim());
}

async function handleRun(options) {
  const client = await createClient(options);
  const payload = await buildPayload(options);
  const createResponse = await client.createTask(payload);
  const taskId = assertTaskId(createResponse);
  const downloadDir = resolveDownloadDir(options.downloadDir, taskId);

  await ensureDir(downloadDir);
  await writeJson(path.join(downloadDir, "request.json"), sanitizePayloadForStorage(payload));

  console.error(`Created task: ${taskId}`);
  const task = await waitForTask(client, taskId, options);
  await writeJson(path.join(downloadDir, "task.json"), task);
  await maybeDownloadTaskOutputs(task, downloadDir);
  printSummary(task, downloadDir);
}

async function handleCreate(options) {
  const client = await createClient(options);
  const payload = await buildPayload(options);
  const response = await client.createTask(payload);
  console.log(JSON.stringify(response, null, 2));

  const shouldWait = parseBoolean(options.wait, false);
  if (!shouldWait) {
    return;
  }

  const taskId = assertTaskId(response);
  const downloadDir = resolveDownloadDir(options.downloadDir, taskId);
  await ensureDir(downloadDir);
  await writeJson(path.join(downloadDir, "request.json"), sanitizePayloadForStorage(payload));

  const task = await waitForTask(client, taskId, options);
  await writeJson(path.join(downloadDir, "task.json"), task);
  await maybeDownloadTaskOutputs(task, downloadDir);
  printSummary(task, downloadDir);
}

async function handleGet(options) {
  const client = await createClient(options);
  const taskId = requireOption(options.taskId, "--task-id is required for get");
  const task = await client.getTask(taskId);

  if (options.downloadDir) {
    const downloadDir = resolveDownloadDir(options.downloadDir, task.id || taskId);
    await ensureDir(downloadDir);
    await maybeDownloadTaskOutputs(task, downloadDir);
    // 🐛 下载后再写 task.json，确保 downloads 字段被持久化
    await writeJson(path.join(downloadDir, "task.json"), task);
  }
  
  console.log(JSON.stringify(task, null, 2));
}

async function handleList(options) {
  const client = await createClient(options);
  const response = await client.listTasks({
    pageNum: options.pageNum,
    pageSize: options.pageSize,
    status: options.filterStatus,
    model: options.filterModel,
    taskIds: toArray(options.filterTaskId),
  });
  console.log(JSON.stringify(response, null, 2));
}

async function handleDelete(options) {
  const client = await createClient(options);
  const taskId = requireOption(options.taskId, "--task-id is required for delete");
  const response = await client.deleteTask(taskId);
  console.log(JSON.stringify(response, null, 2));
}

async function handleDownload(options) {
  let task;

  if (options.taskFile) {
    task = await readJson(path.resolve(options.taskFile));
  } else {
    const client = await createClient(options);
    task = await client.getTask(
      requireOption(options.taskId, "--task-id or --task-file is required for download")
    );
  }

  const taskId = task.id || options.taskId || "unknown-task";
  const downloadDir = resolveDownloadDir(options.downloadDir, taskId);
  await ensureDir(downloadDir);
  await writeJson(path.join(downloadDir, "task.json"), task);
  await maybeDownloadTaskOutputs(task, downloadDir);
  printSummary(task, downloadDir);
}

// ============================================
// 🔑 Hermes Dock Agent Plan API Key
// ============================================

function validateArkKey(key) {
  if (!key || typeof key !== "string") {
    return { valid: false, reason: "API Key 为空" };
  }
  const trimmed = key.trim();
  if (!trimmed.startsWith("ark-")) {
    return { valid: false, reason: "Agent Plan API Key 必须以 ark- 开头" };
  }
  return { valid: true, trimmed };
}

async function resolveApiKey(options = {}) {
  if (options.apiKey || options.saveApiKey) {
    throw new Error("Hermes Dock 中请在“火山方舟 Agent Plan”供应商页管理 API 密钥，不要通过 skill 命令传入或保存密钥。");
  }
  const validation = validateArkKey(process.env.ARK_AGENT_PLAN_API_KEY);
  if (!validation.valid) {
    throw new Error("未配置火山方舟 Agent Plan API 密钥。请在 Hermes Dock 的供应商页填写并应用配置。");
  }
  return validation.trimmed;
}

async function createClient(options) {
  const apiKey = await resolveApiKey(options);

  const baseUrl = stripTrailingSlash(options.baseUrl || process.env.ARK_BASE_URL || DEFAULT_BASE_URL);
  const headers = {
    Authorization: `Bearer ${apiKey}`,
    "Content-Type": "application/json",
  };

  return {
    async createTask(payload) {
      return requestJson(`${baseUrl}/api/plan/v3/contents/generations/tasks`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });
    },
    async getTask(taskId) {
      return requestJson(`${baseUrl}/api/plan/v3/contents/generations/tasks/${encodeURIComponent(taskId)}`, {
        method: "GET",
        headers,
      });
    },
    async listTasks(filters) {
      const url = new URL(`${baseUrl}/api/plan/v3/contents/generations/tasks`);
      if (filters.pageNum) {
        url.searchParams.set("page_num", String(filters.pageNum));
      }
      if (filters.pageSize) {
        url.searchParams.set("page_size", String(filters.pageSize));
      }
      if (filters.status) {
        url.searchParams.set("filter.status", String(filters.status));
      }
      if (filters.model) {
        url.searchParams.set("filter.model", String(filters.model));
      }
      const taskIds = toArray(filters.taskIds).filter(Boolean);
      if (taskIds.length > 0) {
        url.searchParams.set("filter.task_ids", taskIds.join(","));
      }
      return requestJson(url.toString(), {
        method: "GET",
        headers,
      });
    },
    async deleteTask(taskId) {
      return requestJson(`${baseUrl}/api/plan/v3/contents/generations/tasks/${encodeURIComponent(taskId)}`, {
        method: "DELETE",
        headers,
      });
    },
  };
}

async function buildPayload(options) {
  const payload = options.payloadFile ? await readJson(path.resolve(options.payloadFile)) : {};
  const content = Array.isArray(payload.content) ? [...payload.content] : [];

  if (options.prompt) {
    content.push({ type: "text", text: String(options.prompt) });
  }

  // 处理在线图片 URL（恢复 V1 的首尾帧自动判断逻辑）
  const imageUrls = toArray(options.imageUrl);
  for (let i = 0; i < imageUrls.length; i++) {
    let role = 'reference_image';
    if (imageUrls.length === 1) role = 'first_frame';
    else if (imageUrls.length === 2 && i === 0) role = 'first_frame';
    else if (imageUrls.length === 2 && i === 1) role = 'last_frame';
    content.push({ type: "image_url", image_url: { url: imageUrls[i] }, role: role });
  }

  for (const item of toArray(options.videoUrl)) {
    content.push({ type: "video_url", video_url: { url: item } });
  }
  for (const item of toArray(options.audioUrl)) {
    content.push({ type: "audio_url", audio_url: { url: item } });
  }
  for (const item of toArray(options.draftTaskId)) {
    content.push({ type: "draft_task", draft_task: { id: item } });
  }

  // 处理本地图片文件（恢复 V1 的首尾帧自动判断逻辑）
  const imageFiles = toArray(options.imageFile);
  for (let i = 0; i < imageFiles.length; i++) {
    let role = 'reference_image';
    if (imageFiles.length === 1) role = 'first_frame';
    else if (imageFiles.length === 2 && i === 0) role = 'first_frame';
    else if (imageFiles.length === 2 && i === 1) role = 'last_frame';
    content.push({ type: "image_url", image_url: { url: await fileToDataUrl(imageFiles[i]) }, role: role });
  }

  for (const file of toArray(options.videoFile)) {
    content.push({ type: "video_url", video_url: { url: await fileToDataUrl(file) } });
  }
  for (const file of toArray(options.audioFile)) {
    content.push({ type: "audio_url", audio_url: { url: await fileToDataUrl(file) } });
  }

  if (content.length === 0) {
    throw new Error("No content specified. Use --prompt, media inputs, or --payload-file with a content array.");
  }

  payload.model = await resolveSelectedModel(options, payload.model);
  payload.content = content;

  // 基础参数
  applyIfDefined(payload, "resolution", options.resolution);
  applyIfDefined(payload, "ratio", options.ratio);
  applyNumberIfDefined(payload, "duration", options.duration);
  applyNumberIfDefined(payload, "frames", options.frames);
  applyNumberIfDefined(payload, "seed", options.seed);
  applyBooleanIfDefined(payload, "camera_fixed", options.cameraFixed);
  applyBooleanIfDefined(payload, "watermark", options.watermark);
  applyBooleanIfDefined(payload, "return_last_frame", options.returnLastFrame);
  applyBooleanIfDefined(payload, "draft", options.draft);
  applyIfDefined(payload, "callback_url", options.callbackUrl);

  // 【补齐功能】：恢复 V1 缺失的高级参数
  applyBooleanIfDefined(payload, "generate_audio", options.generateAudio);
  applyIfDefined(payload, "service_tier", options.serviceTier);
  
  if (options.enableWebSearch !== undefined && parseBoolean(options.enableWebSearch, false)) {
    payload.tools = [{ type: "web_search" }];
  }

  // 🛡️ 最终兼容校验：防止显式指定 1.5 pro 时，检测不支持的参数
  const finalModel = payload.model || '';
  const is15pro = 
    finalModel.toLowerCase().includes('seedance-1.5') || 
    finalModel.toLowerCase().includes('seedance-1-5');
  
  const hasWebSearch = options.enableWebSearch !== undefined && parseBoolean(options.enableWebSearch, false);
  
  if (is15pro) {
    // 1.5 Pro 支持 1-2 张图的图生视频（首帧/首尾帧），但不支持多模态参考
    const imageCount = 
      toArray(options.imageUrl).length +
      toArray(options.imageFile).length;
    const hasVideoRef = 
      toArray(options.videoUrl).length > 0 ||
      toArray(options.videoFile).length > 0;
    const hasAudioRef = 
      toArray(options.audioUrl).length > 0 ||
      toArray(options.audioFile).length > 0;
    
    if (hasWebSearch) {
      throw new Error('⚠️  Seedance 1.5 pro 不支持联网搜索，请使用 doubao-seedance-2.0 或 doubao-seedance-2.0-fast');
    }
    
    if (hasVideoRef || hasAudioRef) {
      throw new Error('⚠️  Seedance 1.5 pro 不支持视频/音频参考，请使用 doubao-seedance-2.0 或 doubao-seedance-2.0-fast');
    }
    
    if (imageCount > 2) {
      throw new Error('⚠️  Seedance 1.5 pro 仅支持首帧/首尾帧图生视频（最多2张图），不支持多图参考。如需多图参考，请使用 doubao-seedance-2.0 或 doubao-seedance-2.0-fast');
    }
  }

  return payload;
}

const MODEL_ALIASES = {
  "doubao-seedance-2.0-mini": "doubao-seedance-2-0-mini-260615",
  "doubao-seedance-2.0": "doubao-seedance-2-0-260128",
  "doubao-seedance-2.0-fast": "doubao-seedance-2-0-fast-260128",
  "doubao-seedance-1.5-pro": "doubao-seedance-1-0-pro-250528"
};

async function resolveSelectedModel(options, payloadModel) {
  const requested = options.model || payloadModel;
  if (!requested) {
    throw new Error("Missing model selection. Pass --model <MODEL_ID> or include model in --payload-file.");
  }
  
  // 版本号兜底策略：如果传入的是通用别名，则映射到底层带版本号的模型 ID
  return MODEL_ALIASES[requested] || requested;
}

async function waitForTask(client, taskId, options) {
  const intervalMs = Math.max(1000, Number(options.pollInterval || DEFAULT_POLL_INTERVAL_MS / 1000) * 1000);
  const timeoutMs = Math.max(intervalMs, Number(options.timeoutSec || DEFAULT_TIMEOUT_MS / 1000) * 1000);
  const startedAt = Date.now();

  while (true) {
    const task = await client.getTask(taskId);
    const status = String(task.status || "").toLowerCase();
    console.error(`Task ${taskId} status: ${status || "unknown"}`);

    if (TERMINAL_STATUSES.has(status)) {
      if (status !== "succeeded") {
        const message = task.error ? `${task.error.code || "task_error"}: ${task.error.message || "task failed"}` : `Task ended with status ${status}`;
        throw new Error(message);
      }
      return task;
    }

    if (Date.now() - startedAt > timeoutMs) {
      throw new Error(`Timed out waiting for task ${taskId} after ${Math.round(timeoutMs / 1000)} seconds.`);
    }

    await sleep(intervalMs);
  }
}

async function maybeDownloadTaskOutputs(task, downloadDir) {
  const urls = collectOutputUrls(task.content || {});
  if (urls.length === 0) {
    console.error("No downloadable output URLs found in task content.");
    task.downloads = [];
    return;
  }

  console.error(`Downloading ${urls.length} output file(s) to ${downloadDir}`);
  const downloads = [];
  for (let index = 0; index < urls.length; index += 1) {
    const item = urls[index];
    const filename = await buildDownloadFilename(item, index);
    const targetPath = path.join(downloadDir, filename);
    
    try {
      await downloadToFile(item.url, targetPath);
      console.error(`Saved ${item.key} -> ${targetPath}`);
      
      // 记录真实下载结果
      const ext = path.extname(filename).toLowerCase();
      downloads.push({
        key: item.key,
        url: item.url,
        local_path: targetPath,
        filename: filename,
        type: ['.mp4', '.mov', '.webm', '.avi'].includes(ext) ? 'video' : 
              ['.jpg', '.jpeg', '.png', '.webp'].includes(ext) ? 'image' : 'other',
        download_success: true
      });
    } catch (e) {
      // 下载失败不中断，记录结构化错误
      console.error(`Failed to download ${item.key}: ${e.message}`);
      downloads.push({
        key: item.key,
        url: item.url,
        local_path: null,
        filename: filename,
        download_success: false,
        download_error: e.message
      });
    }
  }
  task.downloads = downloads;
}

function collectOutputUrls(value, prefix = "content") {
  const results = [];

  if (typeof value === "string") {
    if (isHttpUrl(value)) {
      results.push({ key: prefix, url: value });
    }
    return results;
  }

  if (Array.isArray(value)) {
    value.forEach((item, index) => {
      results.push(...collectOutputUrls(item, `${prefix}-${index}`));
    });
    return results;
  }

  if (!value || typeof value !== "object") {
    return results;
  }

  for (const [key, child] of Object.entries(value)) {
    const nextPrefix = `${prefix}.${key}`;
    if ((key === "url" || key.endsWith("_url")) && typeof child === "string" && isHttpUrl(child)) {
      results.push({ key: nextPrefix, url: child });
      continue;
    }
    results.push(...collectOutputUrls(child, nextPrefix));
  }

  return dedupeBy(results, (item) => `${item.key}|${item.url}`);
}

async function buildDownloadFilename(item, index) {
  const url = new URL(item.url);
  const pathname = url.pathname || "";
  let extension = path.extname(pathname);
  if (!extension) {
    extension = await inferExtensionFromUrl(item.url);
  }

  if (!extension) {
    extension = item.key.includes("video") ? ".mp4" : ".bin";
  }

  const safeKey = item.key.replace(/[^a-zA-Z0-9._-]+/g, "_").replace(/^_+|_+$/g, "");
  return `${String(index + 1).padStart(2, "0")}-${safeKey}${extension}`;
}

async function inferExtensionFromUrl(url) {
  const response = await fetch(url, { method: "HEAD" }).catch(() => null);
  if (!response || !response.ok) {
    return "";
  }
  return extensionFromContentType(response.headers.get("content-type"));
}

async function downloadToFile(url, targetPath, timeoutMs = 300000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  
  try {
    const response = await fetch(url, { 
      redirect: 'follow',
      signal: controller.signal
    });
    
    // 校验 HTTP 状态码
    if (!response.ok) {
      const contentType = response.headers.get('content-type') || 'unknown';
      throw new Error(`HTTP ${response.status} / content-type: ${contentType}`);
    }
    
    // 校验 Content-Type
    const contentType = response.headers.get('content-type') || '';
    if (!contentType.startsWith('video/') && !contentType.startsWith('image/') && 
        !contentType.startsWith('application/octet-stream')) {
      throw new Error(`无效资源类型: ${contentType}（不是视频/图片）`);
    }
    
    // 🐛 流式下载：避免大视频一次性读入内存
    const fileStream = fsSync.createWriteStream(targetPath);
    const reader = response.body.getReader();
    let totalBytes = 0;
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      totalBytes += value.length;
      // 写入文件流
      await new Promise((resolve, reject) => {
        fileStream.write(value, (err) => err ? reject(err) : resolve());
      });
    }
    
    // 关闭文件流
    await new Promise((resolve) => fileStream.end(resolve));
    
    // 校验文件大小 > 0
    if (totalBytes === 0) {
      throw new Error('下载文件大小为 0');
    }
  } finally {
    clearTimeout(timeout);
  }
}

// 🛡️ 错误信息脱敏：移除 API Key 和 base64 数据
function sanitizeErrorText(text) {
  return String(text)
    .replace(/ark-[A-Za-z0-9._-]+/g, 'ark-***REDACTED***')
    .replace(/data:[^;]+;base64,[A-Za-z0-9+/=]+/g, '[REDACTED_DATA_URL]');
}

async function requestJson(url, init, timeoutMs = 60000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  
  try {
    const response = await fetch(url, {
      ...init,
      signal: controller.signal
    });
    const text = await response.text();
    const data = text ? tryParseJson(text) : {};

    if (!response.ok) {
      const details = data && typeof data === "object"
        ? sanitizeErrorText(JSON.stringify(data))
        : sanitizeErrorText(text || `${response.status} ${response.statusText}`);
      throw new Error(`Ark API request failed: ${response.status} ${response.statusText} - ${details}`);
    }

    return data;
  } finally {
    clearTimeout(timeout);
  }
}

function parseArgv(argv) {
  let command = null;
  const options = {};

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];

    if (!token.startsWith("-") && command === null) {
      command = token;
      continue;
    }

    if (token === "--help" || token === "-h") {
      options.help = true;
      continue;
    }

    if (!token.startsWith("--")) {
      throw new Error(`Unexpected argument: ${token}`);
    }

    const eqIndex = token.indexOf("=");
    const keyPart = eqIndex >= 0 ? token.slice(2, eqIndex) : token.slice(2);
    const rawValue = eqIndex >= 0 ? token.slice(eqIndex + 1) : null;
    const key = toCamelCase(keyPart);
    const expectsValue = rawValue !== null || (argv[index + 1] && !argv[index + 1].startsWith("--"));
    const value = rawValue !== null ? rawValue : expectsValue ? argv[++index] : true;
    assignOption(options, key, value);
  }

  return { command, options };
}

function assignOption(options, key, value) {
  const repeatable = new Set([
    "imageUrl",
    "imageFile",
    "videoUrl",
    "videoFile",
    "audioUrl",
    "audioFile",
    "draftTaskId",
    "filterTaskId",
  ]);

  if (repeatable.has(key)) {
    if (!Array.isArray(options[key])) {
      options[key] = [];
    }
    options[key].push(value);
    return;
  }

  options[key] = value;
}

function toCamelCase(value) {
  return value.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
}

function toArray(value) {
  if (value === undefined || value === null) {
    return [];
  }
  return Array.isArray(value) ? value : [value];
}

function applyIfDefined(target, key, value) {
  if (value !== undefined && value !== null && value !== "") {
    target[key] = value;
  }
}

function applyNumberIfDefined(target, key, value) {
  if (value === undefined || value === null || value === "") {
    return;
  }

  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    throw new Error(`Expected a number for ${key}, got: ${value}`);
  }
  target[key] = parsed;
}

function applyBooleanIfDefined(target, key, value) {
  if (value === undefined || value === null || value === "") {
    return;
  }
  target[key] = parseBoolean(value);
}

function parseBoolean(value, defaultValue) {
  if (value === undefined || value === null || value === "") {
    if (defaultValue !== undefined) {
      return defaultValue;
    }
    throw new Error("Expected a boolean value.");
  }

  if (typeof value === "boolean") {
    return value;
  }

  const normalized = String(value).trim().toLowerCase();
  if (["true", "1", "yes", "y", "on"].includes(normalized)) {
    return true;
  }
  if (["false", "0", "no", "n", "off"].includes(normalized)) {
    return false;
  }

  throw new Error(`Invalid boolean value: ${value}`);
}

function requireOption(value, message) {
  if (value === undefined || value === null || value === "") {
    throw new Error(message);
  }
  return value;
}

function assertTaskId(response) {
  const taskId = response.id || response.task_id || response.taskId;
  if (!taskId) {
    throw new Error(`Could not find task ID in create response: ${JSON.stringify(response)}`);
  }
  return taskId;
}

function resolveDownloadDir(downloadDir, taskId) {
  if (downloadDir) {
    return path.resolve(downloadDir);
  }
  return path.resolve(process.cwd(), DEFAULT_DOWNLOAD_ROOT, taskId);
}

async function ensureDir(dirPath) {
  await fsp.mkdir(dirPath, { recursive: true });
}

async function writeJson(filePath, data) {
  await fsp.writeFile(filePath, JSON.stringify(data, null, 2));
}

async function readJson(filePath) {
  const content = await fsp.readFile(filePath, "utf8");
  return JSON.parse(content);
}

function sanitizePayloadForStorage(value) {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizePayloadForStorage(item));
  }

  if (!value || typeof value !== "object") {
    if (typeof value === "string" && isDataUrl(value)) {
      return redactDataUrl(value);
    }
    return value;
  }

  const result = {};
  for (const [key, child] of Object.entries(value)) {
    if (typeof child === "string" && isDataUrl(child)) {
      result[key] = redactDataUrl(child);
      continue;
    }
    result[key] = sanitizePayloadForStorage(child);
  }
  return result;
}

function isDataUrl(value) {
  return /^data:[^;]+;base64,/i.test(String(value));
}

function redactDataUrl(value) {
  const text = String(value);
  const prefix = text.slice(0, text.indexOf(","));
  return `[REDACTED_DATA_URL ${prefix};bytes=${text.length}]`;
}

function tryParseJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function stripTrailingSlash(url) {
  return String(url).replace(/\/+$/, "");
}

function extensionFromContentType(contentType) {
  if (!contentType) {
    return "";
  }

  const normalized = contentType.split(";")[0].trim().toLowerCase();
  for (const [extension, mime] of MIME_BY_EXTENSION.entries()) {
    if (mime === normalized) {
      return extension;
    }
  }
  return "";
}

function isHttpUrl(value) {
  return /^https?:\/\//i.test(String(value));
}

async function fileToDataUrl(filePath) {
  const absolutePath = path.resolve(filePath);
  const buffer = await fsp.readFile(absolutePath);
  const extension = path.extname(absolutePath).toLowerCase();
  const mimeType = MIME_BY_EXTENSION.get(extension);

  if (!mimeType) {
    throw new Error(`Unsupported file extension for data URL conversion: ${extension || "<none>"} (${absolutePath})`);
  }

  return `data:${mimeType};base64,${buffer.toString("base64")}`;
}

function printSummary(task, downloadDir) {
  const lines = [
    `Task ID: ${task.id || "unknown"}`,
    `Model: ${task.model || "unknown"}`,
    `Status: ${task.status || "unknown"}`,
  ];

  if (task.content && task.content.video_url) {
    lines.push(`Video URL: ${task.content.video_url}`);
  }
  if (task.content && task.content.last_frame_url) {
    lines.push(`Last frame URL: ${task.content.last_frame_url}`);
  }
  if (downloadDir) {
    lines.push(`Download dir: ${downloadDir}`);
  }

  console.error(lines.join("\n"));
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function dedupeBy(items, keyFn) {
  const seen = new Set();
  const result = [];

  for (const item of items) {
    const key = keyFn(item);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    result.push(item);
  }

  return result;
}

main().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exitCode = 1;
});
