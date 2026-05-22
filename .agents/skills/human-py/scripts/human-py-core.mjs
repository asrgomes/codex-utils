const SECTION_LABELS = new Set([
  "inputs",
  "outputs",
  "defaults",
  "constraints",
  "preconditions",
  "postconditions",
  "steps",
  "notes",
]);

const CONTEXTUAL_PLACEHOLDERS = new Set([
  "current_date",
  "timestamp",
  "user_name",
  "latest_status",
  "source",
]);

const RESERVED_PLACEHOLDER_WORDS = new Set([
  "a",
  "an",
  "and",
  "any",
  "all",
  "as",
  "based",
  "by",
  "false",
  "for",
  "has",
  "in",
  "is",
  "len",
  "none",
  "not",
  "of",
  "or",
  "the",
  "true",
  "where",
  "with",
]);

export function stripListMarker(line) {
  return line.replace(/^(\s*)(?:[-*+]|\d+\.)\s+/, "$1");
}

function parseArgs(rawArgs) {
  const trimmed = rawArgs.trim();
  if (!trimmed) {
    return [];
  }

  return trimmed
    .split(",")
    .map((arg) => arg.trim())
    .filter(Boolean)
    .map((arg) => {
      const [namePart, ...defaultParts] = arg.split("=");
      return {
        raw: arg,
        name: namePart.trim(),
        default: defaultParts.length > 0 ? defaultParts.join("=").trim() : null,
      };
    });
}

export function parseRecognizedForm(trimmed) {
  let match = trimmed.match(/^set\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$/);
  if (match) {
    return {
      form: "assignment",
      opensBlock: false,
      details: { name: match[1], value: match[2], explicitSet: true },
    };
  }

  match = trimmed.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$/);
  if (match) {
    return {
      form: "assignment",
      opensBlock: false,
      details: { name: match[1], value: match[2], explicitSet: false },
    };
  }

  match = trimmed.match(/^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\):$/);
  if (match) {
    return {
      form: "function_definition",
      opensBlock: true,
      details: { name: match[1], args: parseArgs(match[2]) },
    };
  }

  match = trimmed.match(/^(if|elif)\s+(.+):$/);
  if (match) {
    return {
      form: match[1],
      opensBlock: true,
      details: { condition: match[2] },
    };
  }

  if (trimmed === "else:") {
    return { form: "else", opensBlock: true, details: {} };
  }

  match = trimmed.match(/^for\s+each\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\s+(.+):$/);
  if (match) {
    return {
      form: "loop",
      opensBlock: true,
      details: { variable: match[1], collection: match[2], style: "for_each" },
    };
  }

  match = trimmed.match(/^for\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\s+(.+):$/);
  if (match) {
    return {
      form: "loop",
      opensBlock: true,
      details: { variable: match[1], collection: match[2], style: "for" },
    };
  }

  match = trimmed.match(/^call\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s+as\s+([A-Za-z_][A-Za-z0-9_]*)$/);
  if (match) {
    return {
      form: "function_call",
      opensBlock: false,
      details: {
        name: match[1],
        args: parseArgs(match[2]),
        result: match[3],
        legacyCall: true,
      },
    };
  }

  match = trimmed.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)(?:\s+as\s+([A-Za-z_][A-Za-z0-9_]*))?$/);
  if (match) {
    return {
      form: "function_call",
      opensBlock: false,
      details: {
        name: match[1],
        args: parseArgs(match[2]),
        result: match[3] || null,
        legacyCall: false,
      },
    };
  }

  match = trimmed.match(/^return\s+(.+)$/);
  if (match) {
    return {
      form: "return",
      opensBlock: false,
      details: { value: match[1] },
    };
  }

  match = trimmed.match(/^add\s+(.+)\s+to\s+(.+)$/);
  if (match) {
    return {
      form: "collection_add",
      opensBlock: false,
      details: { value: match[1], collection: match[2] },
    };
  }

  match = trimmed.match(/^use\s+(.+)\s+as\s+([A-Za-z_][A-Za-z0-9_]*)$/);
  if (match) {
    return {
      form: "alias",
      opensBlock: false,
      details: { value: match[1], name: match[2] },
    };
  }

  match = trimmed.match(/^([A-Za-z_][A-Za-z0-9_]*):$/);
  if (match && SECTION_LABELS.has(match[1])) {
    return {
      form: "section_label",
      opensBlock: true,
      details: { name: match[1] },
    };
  }

  return null;
}

export function classifyLine(rawLine, options = {}) {
  const { insideFence = true } = options;
  const listStripped = stripListMarker(rawLine);
  const trimmed = listStripped.trim();
  const indent = listStripped.match(/^ */)?.[0].length ?? 0;

  const base = {
    raw: rawLine,
    content: trimmed,
    indent,
  };

  if (trimmed === "") {
    return { ok: true, type: "comment/blank", form: "blank", opensBlock: false, details: {}, ...base };
  }

  if (insideFence && trimmed.startsWith("#")) {
    return { ok: true, type: "comment/blank", form: "comment", opensBlock: false, details: {}, ...base };
  }

  if (/^set\b/.test(trimmed) && !/^set\s+[A-Za-z_][A-Za-z0-9_]*\s*=\s*.+$/.test(trimmed)) {
    return { ok: false, reason: "malformed set assignment", type: "error", form: "error", opensBlock: false, details: {}, ...base };
  }

  if (/^def\b/.test(trimmed) && !/^def\s+[A-Za-z_][A-Za-z0-9_]*\s*\([^)]*\):$/.test(trimmed)) {
    return { ok: false, reason: "malformed function definition", type: "error", form: "error", opensBlock: false, details: {}, ...base };
  }

  if (/^(if|elif)\b/.test(trimmed) && !/^(if|elif)\s+.+:$/.test(trimmed)) {
    return { ok: false, reason: "malformed conditional", type: "error", form: "error", opensBlock: false, details: {}, ...base };
  }

  if (/^else\b/.test(trimmed) && trimmed !== "else:") {
    return { ok: false, reason: "malformed else block", type: "error", form: "error", opensBlock: false, details: {}, ...base };
  }

  if (/^for\b/.test(trimmed)
    && !/^for\s+[A-Za-z_][A-Za-z0-9_]*\s+in\s+.+:$/.test(trimmed)
    && !/^for\s+each\s+[A-Za-z_][A-Za-z0-9_]*\s+in\s+.+:$/.test(trimmed)) {
    return { ok: false, reason: "malformed loop", type: "error", form: "error", opensBlock: false, details: {}, ...base };
  }

  if (/^call\b/.test(trimmed) && !/^call\s+[A-Za-z_][A-Za-z0-9_]*\s*\([^)]*\)\s+as\s+[A-Za-z_][A-Za-z0-9_]*$/.test(trimmed)) {
    return { ok: false, reason: "malformed legacy function call", type: "error", form: "error", opensBlock: false, details: {}, ...base };
  }

  if (/^add\b/.test(trimmed) && !/^add\s+.+\s+to\s+.+$/.test(trimmed)) {
    return { ok: false, reason: "malformed add-to-collection statement", type: "error", form: "error", opensBlock: false, details: {}, ...base };
  }

  if (/^use\b/.test(trimmed) && !/^use\s+.+\s+as\s+[A-Za-z_][A-Za-z0-9_]*$/.test(trimmed)) {
    return { ok: false, reason: "malformed alias statement", type: "error", form: "error", opensBlock: false, details: {}, ...base };
  }

  if (/^(import|class|try|except|finally|with|while)\b/.test(trimmed)
    || /^from\s+\S+\s+import\b/.test(trimmed)
    || /^@/.test(trimmed)) {
    return { ok: false, reason: "executable Python construct", type: "error", form: "error", opensBlock: false, details: {}, ...base };
  }

  if (/->/.test(trimmed)
    || (/(?:^|[^=!<>])=[^=]/.test(trimmed) && /^[A-Za-z_][A-Za-z0-9_]*(?:\.|\[)/.test(trimmed))) {
    return { ok: false, reason: "field or item mutation", type: "error", form: "error", opensBlock: false, details: {}, ...base };
  }

  if (/\+=|-=|\*=|\/=/.test(trimmed) || /^[A-Za-z_][A-Za-z0-9_]*\s*,\s*[A-Za-z_]/.test(trimmed)) {
    return { ok: false, reason: "complex assignment", type: "error", form: "error", opensBlock: false, details: {}, ...base };
  }

  const parsed = parseRecognizedForm(trimmed);
  if (parsed) {
    return {
      ok: true,
      type: "python-like",
      form: parsed.form,
      opensBlock: parsed.opensBlock,
      details: parsed.details,
      ...base,
    };
  }

  if (/^[A-Za-z_][A-Za-z0-9_]*\s+.+\s+as\s+[A-Za-z_][A-Za-z0-9_]*$/.test(trimmed)) {
    return { ok: false, reason: "malformed function invocation", type: "error", form: "error", opensBlock: false, details: {}, ...base };
  }

  if (/[A-Za-z]/.test(trimmed) && /[\s,.:-]/.test(trimmed)) {
    return { ok: true, type: "english-like", form: "prose", opensBlock: false, details: {}, ...base };
  }

  return { ok: false, reason: "unclear line", type: "error", form: "error", opensBlock: false, details: {}, ...base };
}

export function validateSource(source, options = {}) {
  const errors = [];
  let previousWasBlockOpener = false;
  let previousIndent = 0;

  source.split("\n").forEach((rawLine, index) => {
    const lineNumber = index + 1;
    const classified = classifyLine(rawLine, options);

    if (classified.form === "blank" || classified.form === "comment") {
      return;
    }

    if (classified.indent > previousIndent && !previousWasBlockOpener) {
      errors.push({
        line: lineNumber,
        blockLine: lineNumber,
        reason: "indentation without an open block",
        raw: rawLine,
      });
    }

    if (!classified.ok) {
      errors.push({
        line: lineNumber,
        blockLine: lineNumber,
        reason: classified.reason,
        raw: rawLine,
      });
    }

    previousWasBlockOpener = classified.opensBlock;
    previousIndent = classified.indent;
  });

  return { valid: errors.length === 0, errors };
}

export function extractHumanPyBlocks(source) {
  const blocks = [];
  const fencePattern = /(^|\n)([`~]{3,})[ \t]*(humanpy|human-py)[^\n]*\n([\s\S]*?)\n\2[ \t]*(?=\n|$)/g;
  let match;

  while ((match = fencePattern.exec(source)) !== null) {
    const openingLine = source.slice(0, match.index + match[1].length).split("\n").length;
    const content = match[4];
    const startLine = openingLine + 1;
    const endLine = startLine + content.split("\n").length - 1;

    blocks.push({
      index: blocks.length,
      language: match[3],
      fenced: true,
      startLine,
      endLine,
      source: content,
    });
  }

  if (blocks.length > 0) {
    return blocks;
  }

  return [{
    index: 0,
    language: "humanpy",
    fenced: false,
    startLine: 1,
    endLine: source.split("\n").length,
    source,
  }];
}

function maskInlineCodeAndQuotedAngles(line) {
  let masked = line.replace(/`[^`]*`/g, (text) => " ".repeat(text.length));
  masked = masked.replace(/"[^"\n]*<[^"\n]*>[^"\n]*"/g, (text) => " ".repeat(text.length));
  masked = masked.replace(/'[^'\n]*<[^'\n]*>[^'\n]*'/g, (text) => " ".repeat(text.length));
  return masked;
}

function maskStringLiterals(text) {
  return text.replace(/(["'])(?:\\.|(?!\1)[^\\\n])*\1/g, (literal) => " ".repeat(literal.length));
}

function previousNonSpace(text, index) {
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    if (!/\s/.test(text[cursor])) {
      return text[cursor];
    }
  }
  return "";
}

function placeholderRoots(expression) {
  const maskedExpression = maskStringLiterals(expression);
  const identifiers = maskedExpression.matchAll(/[A-Za-z_][A-Za-z0-9_]*/g);
  const roots = [];

  for (const match of identifiers) {
    const identifier = match[0];
    const lower = identifier.toLowerCase();
    if (RESERVED_PLACEHOLDER_WORDS.has(lower)) {
      continue;
    }

    if (previousNonSpace(maskedExpression, match.index) === ".") {
      continue;
    }

    if (!roots.includes(identifier)) {
      roots.push(identifier);
    }
  }

  return roots;
}

function extractPlaceholders(rawLine, absoluteLine, blockLine, scopePath, visibleScopePath) {
  const masked = maskInlineCodeAndQuotedAngles(rawLine);
  const placeholders = [];
  const placeholderPattern = /<([^>\n]+)>/g;
  let match;

  while ((match = placeholderPattern.exec(masked)) !== null) {
    const expression = match[1].trim();
    if (!expression) {
      continue;
    }

    placeholders.push({
      text: `<${expression}>`,
      expression,
      roots: placeholderRoots(expression),
      line: absoluteLine,
      blockLine,
      column: match.index + 1,
      scope: scopePath,
      visibleScope: visibleScopePath,
    });
  }

  return placeholders;
}

function addSymbol(symbols, symbol) {
  if (!symbols.has(symbol.name)) {
    symbols.set(symbol.name, []);
  }

  symbols.get(symbol.name).push(symbol);
}

function scopePath(scopeStack, options = {}) {
  const { includeSections = true } = options;
  return scopeStack
    .filter((scope) => includeSections || scope.type !== "section")
    .map((scope) => scope.name);
}

function visibilityPath(scopeStack) {
  return scopePath(scopeStack, { includeSections: false });
}

function currentScope(scopeStack, type) {
  for (let index = scopeStack.length - 1; index >= 0; index -= 1) {
    if (scopeStack[index].type === type) {
      return scopeStack[index];
    }
  }
  return null;
}

function sectionEntry(content) {
  let match = content.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+)$/);
  if (match) {
    return { name: match[1], value: match[2], style: "colon" };
  }

  match = content.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$/);
  if (match) {
    return { name: match[1], value: match[2], style: "assignment" };
  }

  return null;
}

function symbolList(symbols) {
  return [...symbols.values()].flat().sort((left, right) => {
    if (left.line !== right.line) {
      return left.line - right.line;
    }
    return left.name.localeCompare(right.name);
  });
}

function isScopePrefix(candidate, target) {
  if (!Array.isArray(candidate) || !Array.isArray(target) || candidate.length > target.length) {
    return false;
  }

  return candidate.every((part, index) => part === target[index]);
}

function symbolVisibleToPlaceholder(symbol, placeholder) {
  const visibleScope = symbol.visibleScope || symbol.scope || ["global"];
  const placeholderScope = placeholder.visibleScope || placeholder.scope || ["global"];
  return isScopePrefix(visibleScope, placeholderScope);
}

function mergeExecutionMaps(blocks) {
  const empty = {
    inputs: [],
    defaults: [],
    constraints: [],
    preconditions: [],
    postconditions: [],
    variables: [],
    aliases: [],
    functions: [],
    calls: [],
    branches: [],
    loops: [],
    collections: [],
    outputs: [],
    returns: [],
    orderedSteps: [],
    notes: [],
    unresolvedPlaceholders: [],
  };

  for (const block of blocks) {
    for (const key of Object.keys(empty)) {
      empty[key].push(...(block.executionMap[key] || []));
    }
  }

  return empty;
}

function addOrderedStep(executionMap, lineRecord) {
  if (lineRecord.form === "blank" || lineRecord.form === "comment" || lineRecord.form === "section_label") {
    return;
  }

  executionMap.orderedSteps.push({
    line: lineRecord.line,
    scope: lineRecord.scope,
    form: lineRecord.form,
    text: lineRecord.content,
  });
}

function lintBlock(block) {
  const errors = [];
  const symbols = new Map();
  const placeholders = [];
  const lines = [];
  const executionMap = {
    inputs: [],
    defaults: [],
    constraints: [],
    preconditions: [],
    postconditions: [],
    variables: [],
    aliases: [],
    functions: [],
    calls: [],
    branches: [],
    loops: [],
    collections: [],
    outputs: [],
    returns: [],
    orderedSteps: [],
    notes: [],
    unresolvedPlaceholders: [],
  };

  const rootScope = { id: "global", type: "global", name: "global", indent: -1 };
  const scopeStack = [rootScope];
  let previousWasBlockOpener = false;
  let previousIndent = 0;

  block.source.split("\n").forEach((rawLine, index) => {
    const blockLine = index + 1;
    const absoluteLine = block.startLine + index;
    const classified = classifyLine(rawLine, { insideFence: block.fenced });

    if (classified.form !== "blank" && classified.form !== "comment") {
      while (scopeStack.length > 1 && classified.indent <= scopeStack[scopeStack.length - 1].indent) {
        scopeStack.pop();
      }
    }

    const activeScopePath = scopePath(scopeStack);
    const activeVisibleScopePath = visibilityPath(scopeStack);
    const linePlaceholders = extractPlaceholders(rawLine, absoluteLine, blockLine, activeScopePath, activeVisibleScopePath);
    placeholders.push(...linePlaceholders);

    const lineRecord = {
      line: absoluteLine,
      blockLine,
      raw: rawLine,
      content: classified.content,
      indent: classified.indent,
      classification: classified.ok ? classified.type : "error",
      form: classified.form,
      scope: activeScopePath,
      details: classified.details,
      placeholders: linePlaceholders.map((placeholder) => placeholder.text),
    };

    if (classified.form !== "blank" && classified.form !== "comment") {
      if (classified.indent > previousIndent && !previousWasBlockOpener) {
        const error = {
          blockIndex: block.index,
          line: absoluteLine,
          blockLine,
          reason: "indentation without an open block",
          raw: rawLine,
        };
        errors.push(error);
        lineRecord.error = error.reason;
      }

      if (!classified.ok) {
        const error = {
          blockIndex: block.index,
          line: absoluteLine,
          blockLine,
          reason: classified.reason,
          raw: rawLine,
        };
        errors.push(error);
        lineRecord.error = lineRecord.error ? `${lineRecord.error}; ${error.reason}` : error.reason;
      }

      const sectionScope = currentScope(scopeStack, "section");
      const functionScope = currentScope(scopeStack, "function");

      if (classified.ok) {
        if (sectionScope && classified.form === "prose") {
          const entry = sectionEntry(classified.content);
          if (entry) {
            lineRecord.form = "section_entry";
            lineRecord.details = { ...entry, section: sectionScope.name };

            if (sectionScope.name === "inputs") {
              const input = { name: entry.name, value: entry.value, line: absoluteLine, scope: activeScopePath };
              executionMap.inputs.push(input);
              addSymbol(symbols, { ...input, kind: "input", visibleScope: activeVisibleScopePath });
            } else if (sectionScope.name === "outputs") {
              const output = { name: entry.name, value: entry.value, line: absoluteLine, scope: activeScopePath };
              executionMap.outputs.push(output);
              addSymbol(symbols, { ...output, kind: "output", visibleScope: activeVisibleScopePath });
            } else if (sectionScope.name === "defaults") {
              const defaultValue = { name: entry.name, value: entry.value, line: absoluteLine, scope: activeScopePath };
              executionMap.defaults.push(defaultValue);
              addSymbol(symbols, { ...defaultValue, kind: "default", visibleScope: activeVisibleScopePath });
            }
          }

          if (["constraints", "preconditions", "postconditions", "notes"].includes(sectionScope.name)) {
            executionMap[sectionScope.name].push({
              line: absoluteLine,
              text: classified.content,
              scope: activeScopePath,
            });
          }
        }

        if (classified.form === "assignment") {
          const variable = {
            name: classified.details.name,
            value: classified.details.value,
            line: absoluteLine,
            scope: activeScopePath,
          };

          if (sectionScope?.name === "inputs") {
            executionMap.inputs.push(variable);
            addSymbol(symbols, { ...variable, kind: "input", visibleScope: activeVisibleScopePath });
          } else if (sectionScope?.name === "outputs") {
            executionMap.outputs.push(variable);
            addSymbol(symbols, { ...variable, kind: "output", visibleScope: activeVisibleScopePath });
          } else if (sectionScope?.name === "defaults") {
            executionMap.defaults.push(variable);
            addSymbol(symbols, { ...variable, kind: "default", visibleScope: activeVisibleScopePath });
          } else {
            executionMap.variables.push(variable);
            addSymbol(symbols, { ...variable, kind: "variable", visibleScope: activeVisibleScopePath });
          }
        } else if (classified.form === "alias") {
          const alias = {
            name: classified.details.name,
            value: classified.details.value,
            line: absoluteLine,
            scope: activeScopePath,
          };
          executionMap.aliases.push(alias);
          addSymbol(symbols, { ...alias, kind: "alias", visibleScope: activeVisibleScopePath });
        } else if (classified.form === "function_definition") {
          const functionInfo = {
            name: classified.details.name,
            args: classified.details.args,
            line: absoluteLine,
            scope: activeScopePath,
            returns: [],
            calls: [],
          };
          executionMap.functions.push(functionInfo);
          addSymbol(symbols, { name: functionInfo.name, kind: "function", line: absoluteLine, scope: activeScopePath, visibleScope: activeVisibleScopePath });

          const functionScopeRecord = {
            id: `function:${functionInfo.name}:${absoluteLine}`,
            type: "function",
            name: functionInfo.name,
            indent: classified.indent,
            functionInfo,
          };
          scopeStack.push(functionScopeRecord);

          for (const arg of classified.details.args) {
            if (/^[A-Za-z_][A-Za-z0-9_]*$/.test(arg.name)) {
              addSymbol(symbols, {
                name: arg.name,
                kind: "argument",
                default: arg.default,
                line: absoluteLine,
                scope: scopePath(scopeStack),
                visibleScope: visibilityPath(scopeStack),
              });
            }
          }
        } else if (classified.form === "function_call") {
          const call = {
            name: classified.details.name,
            args: classified.details.args,
            result: classified.details.result,
            line: absoluteLine,
            scope: activeScopePath,
          };
          executionMap.calls.push(call);
          if (functionScope?.functionInfo) {
            functionScope.functionInfo.calls.push(call);
          }
          if (classified.details.result) {
            addSymbol(symbols, {
              name: classified.details.result,
              kind: "result",
              source: classified.details.name,
              line: absoluteLine,
              scope: activeScopePath,
              visibleScope: activeVisibleScopePath,
            });
          }
        } else if (classified.form === "if" || classified.form === "elif" || classified.form === "else") {
          const branch = {
            type: classified.form,
            condition: classified.details.condition || null,
            line: absoluteLine,
            scope: activeScopePath,
          };
          executionMap.branches.push(branch);
          scopeStack.push({
            id: `branch:${classified.form}:${absoluteLine}`,
            type: "branch",
            name: classified.form,
            indent: classified.indent,
          });
        } else if (classified.form === "loop") {
          const loop = {
            variable: classified.details.variable,
            collection: classified.details.collection,
            style: classified.details.style,
            line: absoluteLine,
            scope: activeScopePath,
          };
          executionMap.loops.push(loop);
          const loopScope = {
            id: `loop:${classified.details.variable}:${absoluteLine}`,
            type: "loop",
            name: `for ${classified.details.variable}`,
            indent: classified.indent,
          };
          scopeStack.push(loopScope);
          addSymbol(symbols, {
            name: classified.details.variable,
            kind: "loop_variable",
            collection: classified.details.collection,
            line: absoluteLine,
            scope: scopePath(scopeStack),
            visibleScope: visibilityPath(scopeStack),
          });
        } else if (classified.form === "collection_add") {
          executionMap.collections.push({
            action: "add",
            value: classified.details.value,
            collection: classified.details.collection,
            line: absoluteLine,
            scope: activeScopePath,
          });
        } else if (classified.form === "return") {
          const returnInfo = {
            value: classified.details.value,
            line: absoluteLine,
            scope: activeScopePath,
          };
          executionMap.returns.push(returnInfo);
          if (functionScope?.functionInfo) {
            functionScope.functionInfo.returns.push(returnInfo);
          }
        } else if (classified.form === "section_label") {
          scopeStack.push({
            id: `section:${classified.details.name}:${absoluteLine}`,
            type: "section",
            name: classified.details.name,
            indent: classified.indent,
          });
        }

        addOrderedStep(executionMap, lineRecord);
      }

      previousWasBlockOpener = classified.opensBlock;
      previousIndent = classified.indent;
    }

    lines.push(lineRecord);
  });

  const resolvedPlaceholders = placeholders.map((placeholder) => {
    const unresolvedRoots = placeholder.roots.filter((root) => {
      if (CONTEXTUAL_PLACEHOLDERS.has(root)) {
        return false;
      }

      const definitions = symbols.get(root) || [];
      return !definitions.some((symbol) => symbolVisibleToPlaceholder(symbol, placeholder));
    });

    return {
      ...placeholder,
      resolved: unresolvedRoots.length === 0 && placeholder.roots.length > 0,
      unresolvedRoots,
    };
  });

  const unresolvedPlaceholders = resolvedPlaceholders.filter((placeholder) => !placeholder.resolved);
  executionMap.unresolvedPlaceholders = unresolvedPlaceholders.map((placeholder) => ({
    text: placeholder.text,
    expression: placeholder.expression,
    unresolvedRoots: placeholder.unresolvedRoots,
    line: placeholder.line,
    blockLine: placeholder.blockLine,
    scope: placeholder.scope,
  }));

  return {
    ...block,
    valid: errors.length === 0,
    errors,
    lines,
    symbols: symbolList(symbols),
    placeholders: resolvedPlaceholders,
    unresolvedPlaceholders,
    executionMap,
  };
}

export function lintSource(source, options = {}) {
  const blocks = extractHumanPyBlocks(source);
  const lintedBlocks = blocks.map(lintBlock);
  const errors = lintedBlocks.flatMap((block) => block.errors);
  const unresolvedPlaceholders = lintedBlocks.flatMap((block) => block.unresolvedPlaceholders);

  return {
    version: 1,
    source: {
      path: options.path || null,
      mode: options.path ? "file" : "stdin",
      blockCount: lintedBlocks.length,
    },
    valid: errors.length === 0,
    errors,
    warnings: unresolvedPlaceholders.map((placeholder) => ({
      type: "unresolved-placeholder",
      text: placeholder.text,
      expression: placeholder.expression,
      unresolvedRoots: placeholder.unresolvedRoots,
      line: placeholder.line,
      blockLine: placeholder.blockLine,
      scope: placeholder.scope,
    })),
    blocks: lintedBlocks,
    executionMap: mergeExecutionMaps(lintedBlocks),
  };
}

export function summarizeLint(report) {
  const lines = [
    `HumanPy lint: ${report.valid ? "valid" : "invalid"}`,
    `Blocks: ${report.source.blockCount}`,
    `Validation errors: ${report.errors.length}`,
    `Unresolved placeholders: ${report.warnings.length}`,
  ];

  for (const error of report.errors) {
    lines.push(`Validation error: line ${error.line}: ${error.reason}`);
  }

  for (const warning of report.warnings) {
    const roots = warning.unresolvedRoots.length > 0 ? ` (${warning.unresolvedRoots.join(", ")})` : "";
    lines.push(`Unresolved placeholder: line ${warning.line}: ${warning.text}${roots}`);
  }

  return `${lines.join("\n")}\n`;
}
