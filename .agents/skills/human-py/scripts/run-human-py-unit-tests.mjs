import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const skillDir = path.dirname(scriptDir);
const testsDir = path.join(skillDir, "tests");

function parseCase(filePath) {
  const raw = fs.readFileSync(filePath, "utf8");
  const frontmatter = raw.match(/^---\n([\s\S]*?)\n---\n/);
  if (!frontmatter) {
    throw new Error(`${path.basename(filePath)}: missing frontmatter`);
  }

  const metadata = {};
  for (const line of frontmatter[1].split("\n")) {
    const match = line.match(/^([a-z_]+):\s*(.+)$/);
    if (match) {
      metadata[match[1]] = match[2].trim();
    }
  }

  const block = raw.slice(frontmatter[0].length).match(/```(?:humanpy|human-py)\n([\s\S]*?)\n```/);
  if (!block) {
    throw new Error(`${path.basename(filePath)}: missing humanpy fenced block`);
  }

  return {
    name: metadata.name || path.basename(filePath),
    valid: metadata.valid === "true",
    source: block[1],
  };
}

function stripListMarker(line) {
  return line.replace(/^(\s*)(?:[-*+]|\d+\.)\s+/, "$1");
}

function classify(trimmed) {
  if (/^set\b/.test(trimmed) && !/^set\s+[A-Za-z_][A-Za-z0-9_]*\s*=\s*.+$/.test(trimmed)) {
    return { ok: false, reason: "malformed set assignment" };
  }

  if (/^call\b/.test(trimmed) && !/^call\s+[A-Za-z_][A-Za-z0-9_]*\s*\([^)]*\)\s+as\s+[A-Za-z_][A-Za-z0-9_]*$/.test(trimmed)) {
    return { ok: false, reason: "malformed legacy function call" };
  }

  if (/^(import|class|try|except)\b/.test(trimmed) || /^@/.test(trimmed)) {
    return { ok: false, reason: "executable Python construct" };
  }

  if (/->/.test(trimmed) || /(?:^|[^=!<>])=[^=]/.test(trimmed) && /^[A-Za-z_][A-Za-z0-9_]*(?:\.|\[)/.test(trimmed)) {
    return { ok: false, reason: "field or item mutation" };
  }

  if (/\+=|-=|\*=|\/=/.test(trimmed) || /^[A-Za-z_][A-Za-z0-9_]*\s*,\s*[A-Za-z_]/.test(trimmed)) {
    return { ok: false, reason: "complex assignment" };
  }

  const forms = [
    /^set\s+[A-Za-z_][A-Za-z0-9_]*\s*=\s*.+$/,
    /^[A-Za-z_][A-Za-z0-9_]*\s*=\s*.+$/,
    /^def\s+[A-Za-z_][A-Za-z0-9_]*\s*\([^)]*\):$/,
    /^(if|elif)\s+.+:$/,
    /^else:$/,
    /^for\s+[A-Za-z_][A-Za-z0-9_]*\s+in\s+.+:$/,
    /^for\s+each\s+[A-Za-z_][A-Za-z0-9_]*\s+in\s+.+:$/,
    /^[A-Za-z_][A-Za-z0-9_]*\s*\([^)]*\)(?:\s+as\s+[A-Za-z_][A-Za-z0-9_]*)?$/,
    /^call\s+[A-Za-z_][A-Za-z0-9_]*\s*\([^)]*\)\s+as\s+[A-Za-z_][A-Za-z0-9_]*$/,
    /^return\s+.+$/,
    /^add\s+.+\s+to\s+.+$/,
    /^use\s+.+\s+as\s+[A-Za-z_][A-Za-z0-9_]*$/,
  ];

  if (forms.some((form) => form.test(trimmed))) {
    return { ok: true, type: "python-like" };
  }

  if (/^[A-Za-z_][A-Za-z0-9_]*\s+.+\s+as\s+[A-Za-z_][A-Za-z0-9_]*$/.test(trimmed)) {
    return { ok: false, reason: "malformed function invocation" };
  }

  if (/[A-Za-z]/.test(trimmed) && /[\s,.]/.test(trimmed)) {
    return { ok: true, type: "english-like" };
  }

  return { ok: false, reason: "unclear line" };
}

function validate(source) {
  const errors = [];
  let previousWasBlockOpener = false;
  let previousIndent = 0;

  source.split("\n").forEach((rawLine, index) => {
    const lineNumber = index + 1;
    const listStripped = stripListMarker(rawLine);
    const trimmed = listStripped.trim();
    const indent = listStripped.match(/^ */)?.[0].length ?? 0;

    if (trimmed === "" || trimmed.startsWith("#")) {
      return;
    }

    if (indent > previousIndent && !previousWasBlockOpener) {
      errors.push(`line ${lineNumber}: indentation without an open block`);
    }

    const result = classify(trimmed);
    if (!result.ok) {
      errors.push(`line ${lineNumber}: ${result.reason}`);
    }

    previousWasBlockOpener = /^(def|if|elif|else|for\b|for each\b).+:$/.test(trimmed);
    previousIndent = indent;
  });

  return errors;
}

const files = fs.readdirSync(testsDir)
  .filter((name) => name.endsWith(".case.md"))
  .sort();

let failed = 0;

for (const file of files) {
  const testCase = parseCase(path.join(testsDir, file));
  const errors = validate(testCase.source);
  const passed = testCase.valid ? errors.length === 0 : errors.length > 0;

  if (passed) {
    console.log(`PASS ${testCase.name}`);
  } else {
    failed += 1;
    console.log(`FAIL ${testCase.name}`);
    if (testCase.valid) {
      console.log(`  expected valid, got errors: ${errors.join("; ")}`);
    } else {
      console.log("  expected invalid, got no validation errors");
    }
  }
}

const passed = files.length - failed;
console.log(`${passed}/${files.length} human-py unit tests passed`);

if (failed > 0) {
  process.exitCode = 1;
}
