import { existsSync, rmSync } from "node:fs";
import { basename, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(scriptDirectory, "..");
const outputDirectory = resolve(projectRoot, "_site");

if (basename(outputDirectory) !== "_site" || !existsSync(resolve(projectRoot, "package.json"))) {
  throw new Error("Refusing to clean an unexpected output directory.");
}

rmSync(outputDirectory, {
  recursive: true,
  force: true,
  maxRetries: 10,
  retryDelay: 200,
});
