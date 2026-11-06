import fs from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const directory = path.join(root, "src", "i18n", "catalogs");
const languagesSource = fs.readFileSync(path.join(root, "src", "i18n", "languages.ts"), "utf8");
const locales = [...languagesSource.matchAll(/\{\s*code:\s*"([^"]+)"/g)].map((match) => match[1]);
const english = JSON.parse(fs.readFileSync(path.join(directory, "en.json"), "utf8"));
const expected = Object.keys(english).sort();
const placeholders = (value) => [...value.matchAll(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g)].map((match) => match[1]).sort().join("|");
const failures = [];

for (const locale of locales) {
  const file = path.join(directory, `${locale}.json`);
  if (!fs.existsSync(file)) {
    failures.push(`${locale}: catalog is missing`);
    continue;
  }
  const catalog = JSON.parse(fs.readFileSync(file, "utf8"));
  const keys = Object.keys(catalog).sort();
  const missing = expected.filter((key) => !(key in catalog));
  const extra = keys.filter((key) => !(key in english));
  if (missing.length) failures.push(`${locale}: ${missing.length} missing messages`);
  if (extra.length) failures.push(`${locale}: ${extra.length} unknown messages`);
  for (const key of expected) {
    if (key in catalog && placeholders(key) !== placeholders(catalog[key])) {
      failures.push(`${locale}: placeholder mismatch for ${key}`);
      break;
    }
  }
}

const statusPath = path.join(directory, "catalog-status.json");
if (!fs.existsSync(statusPath)) failures.push("catalog-status.json: generation and review metadata is missing");
if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log(`Catalog check passed: ${locales.length} locales, ${expected.length} messages, placeholders preserved`);
