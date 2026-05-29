import { cp, readdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(here, "..");
const source = resolve(webRoot, "dist");
const target = resolve(webRoot, "..", "scripts", "ai_flow", "web_static");

await rm(target, { recursive: true, force: true });
await cp(source, target, { recursive: true });

async function normalizeHtmlLineEndings(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = resolve(dir, entry.name);
    if (entry.isDirectory()) {
      await normalizeHtmlLineEndings(path);
    } else if (entry.isFile() && entry.name.endsWith(".html")) {
      const html = await readFile(path, "utf8");
      await writeFile(path, html.replace(/\r\n?/g, "\n"), "utf8");
    }
  }
}

await normalizeHtmlLineEndings(target);
