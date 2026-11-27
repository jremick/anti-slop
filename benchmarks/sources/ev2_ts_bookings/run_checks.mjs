#!/usr/bin/env node
import { readdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = dirname(fileURLToPath(import.meta.url));
const testsDir = join(rootDir, "tests");
const testFiles = readdirSync(testsDir)
  .filter((name) => name.endsWith(".test.ts") || name.endsWith(".test.mts"))
  .sort()
  .map((name) => join(testsDir, name));

if (testFiles.length === 0) {
  console.error("No *.test.ts files found in tests/");
  process.exit(1);
}

const result = spawnSync(process.execPath, ["--test", ...testFiles], {
  cwd: rootDir,
  stdio: "inherit",
});

process.exit(result.status ?? 1);
