import { access, cp, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const targetArg = process.argv[2];
if (!targetArg) {
  throw new Error("用法：node init-deck.mjs <目标目录>");
}

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const starterDir = path.resolve(scriptDir, "../assets/starter");
const targetDir = path.resolve(targetArg);

try {
  await access(targetDir);
  throw new Error(`目标目录已存在，拒绝覆盖：${targetDir}`);
} catch (error) {
  if (error.code !== "ENOENT") {
    throw error;
  }
}

await mkdir(path.dirname(targetDir), { recursive: true });
await cp(starterDir, targetDir, { recursive: true, force: false, errorOnExist: true });
await mkdir(path.join(targetDir, "public"), { recursive: true });

console.log(`已创建 Slidev 项目：${targetDir}`);
