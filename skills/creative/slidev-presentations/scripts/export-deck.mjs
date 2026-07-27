import { access } from "node:fs/promises";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const [projectArg, format, outputArg] = process.argv.slice(2);
if (!projectArg || !format || !outputArg) {
  throw new Error("用法：node export-deck.mjs <项目目录> <png|pdf|pptx|web> <输出路径>");
}
if (!new Set(["png", "pdf", "pptx", "web"]).has(format)) {
  throw new Error(`不支持的导出格式：${format}`);
}

const projectDir = path.resolve(projectArg);
const outputPath = path.resolve(outputArg);
const browserPath = process.env.AGENT_BROWSER_EXECUTABLE_PATH;
if (format !== "web" && !browserPath) {
  throw new Error("缺少 AGENT_BROWSER_EXECUTABLE_PATH，无法复用 Hermes 内置 Chromium");
}

await access(projectDir);
if (browserPath) {
  await access(browserPath);
}
await access(path.dirname(outputPath));
try {
  await access(outputPath);
  throw new Error(`输出路径已存在，拒绝覆盖：${outputPath}`);
} catch (error) {
  if (error.code !== "ENOENT") {
    throw error;
  }
}

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
run(process.execPath, [path.join(scriptDir, "preflight.mjs"), projectDir]);

const installEnv = {
  ...process.env,
  PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD: "1",
};
run("corepack", ["pnpm", "install", "--frozen-lockfile"], installEnv);

if (format === "web") {
  run("corepack", ["pnpm", "exec", "slidev", "build", "slides.md", "--base", "./", "--out", outputPath]);
} else {
  run("corepack", [
    "pnpm",
    "exec",
    "slidev",
    "export",
    "slides.md",
    "--format",
    format,
    "--with-clicks",
    "false",
    "--executable-path",
    browserPath,
    "--timeout",
    "120000",
    "--output",
    outputPath,
  ]);
}

await access(outputPath);
console.log(`已导出：${outputPath}`);

function run(command, args, env = process.env) {
  const result = spawnSync(command, args, {
    cwd: projectDir,
    env,
    stdio: "inherit",
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(`命令失败（退出码 ${result.status}）：${command} ${args.join(" ")}`);
  }
}
