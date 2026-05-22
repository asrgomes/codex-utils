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

const scopeReport = lintSource(`def summarize_ticket(ticket):
    return summary

Write <ticket> outside the function.
`);

const scopeSmokePassed = scopeReport.warnings.some((warning) => warning.text === "<ticket>");

const sectionNameFunctionReport = lintSource(`def steps(ticket):
    Write <ticket> inside the function.

Write <ticket> outside the function.
`);

const sectionNameFunctionScopePassed = sectionNameFunctionReport.warnings.length === 1
  && sectionNameFunctionReport.warnings[0].text === "<ticket>"
  && sectionNameFunctionReport.warnings[0].line === 4;

const sectionScopeReport = lintSource(`inputs:
    ticket: issue to review

steps:
    summarize_ticket(ticket) as summary

outputs:
    final: Include <ticket.owner> and <summary>.

notes:
    Source: use the active issue.
`);

const sectionScopeSmokePassed = !sectionScopeReport.warnings.some((warning) => {
  return warning.text === "<ticket.owner>" || warning.text === "<summary>";
})
  && sectionScopeReport.executionMap.notes.some((note) => note.text === "Source: use the active issue.")
  && sectionScopeReport.executionMap.orderedSteps.some((step) => {
    return step.text === "final: Include <ticket.owner> and <summary>." && step.form === "section_entry";
  });

if (lintSmokePassed && scopeSmokePassed && sectionNameFunctionScopePassed && sectionScopeSmokePassed) {
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
