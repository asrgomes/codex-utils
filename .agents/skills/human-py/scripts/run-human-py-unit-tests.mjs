import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { lintSource, validateSource } from "./human-py-core.mjs";

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

const files = fs.readdirSync(testsDir)
  .filter((name) => name.endsWith(".case.md"))
  .sort();

let failed = 0;
let total = 0;

for (const file of files) {
  total += 1;
  const testCase = parseCase(path.join(testsDir, file));
  const errors = validateSource(testCase.source).errors
    .map((error) => `line ${error.blockLine}: ${error.reason}`);
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

total += 1;
const lintReport = lintSource(`inputs:
    ticket: issue, document, or thread to review
    audience = "engineering leadership"

def summarize_ticket(ticket):
    Write <ticket> for <audience>.
    Include <missing_context> only if available.
    return summary
`);

const lintSmokePassed = lintReport.blocks[0].lines.some((line) => line.form === "function_definition")
  && lintReport.executionMap.inputs.some((input) => input.name === "ticket")
  && lintReport.executionMap.functions.some((fn) => fn.name === "summarize_ticket")
  && lintReport.warnings.some((warning) => warning.text === "<missing_context>")
  && !lintReport.warnings.some((warning) => warning.text === "<audience>");

if (lintSmokePassed) {
  console.log("PASS lint-json-analysis");
} else {
  failed += 1;
  console.log("FAIL lint-json-analysis");
}

const passed = total - failed;
console.log(`${passed}/${total} human-py unit tests passed`);

if (failed > 0) {
  process.exitCode = 1;
}
