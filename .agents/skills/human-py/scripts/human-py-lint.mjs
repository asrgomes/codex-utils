#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { lintSource, summarizeLint } from "./human-py-core.mjs";

function usage() {
  const scriptName = path.basename(fileURLToPath(import.meta.url));
  return `Usage:
  node ${scriptName} lint --json [--pretty] [file|-]
  node ${scriptName} --json [--pretty] [file|-]
  node ${scriptName} lint [file|-]

Reads a HumanPy Lite script, Markdown file with \`\`\`humanpy fences, or stdin.
With --json, emits line classifications, unresolved placeholders, and an execution map.
Without --json, emits a short human-readable lint summary.
`;
}

function parseArgs(argv) {
  const args = [...argv];
  const options = {
    json: false,
    pretty: false,
    file: "-",
    help: false,
  };

  if (args[0] === "lint") {
    args.shift();
  }

  for (const arg of args) {
    if (arg === "--json") {
      options.json = true;
    } else if (arg === "--pretty") {
      options.pretty = true;
    } else if (arg === "--help" || arg === "-h") {
      options.help = true;
    } else if (!arg.startsWith("-") || arg === "-") {
      options.file = arg;
    } else {
      throw new Error(`Unknown option: ${arg}`);
    }
  }

  return options;
}

function readInput(file) {
  if (!file || file === "-") {
    return {
      source: fs.readFileSync(0, "utf8"),
      path: null,
    };
  }

  return {
    source: fs.readFileSync(file, "utf8"),
    path: file,
  };
}

try {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    process.stdout.write(usage());
    process.exit(0);
  }

  const input = readInput(options.file);
  const report = lintSource(input.source, { path: input.path });

  if (options.json) {
    process.stdout.write(`${JSON.stringify(report, null, options.pretty ? 2 : 0)}\n`);
  } else {
    process.stdout.write(summarizeLint(report));
  }

  if (!report.valid) {
    process.exitCode = 1;
  }
} catch (error) {
  process.stderr.write(`${error.message}\n\n${usage()}`);
  process.exitCode = 2;
}

