import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const skillDir = path.resolve(import.meta.dirname, '..');

function readSkillFile(relativePath) {
  return readFileSync(path.join(skillDir, relativePath), 'utf8');
}

function frontmatterDescription(skillMarkdown) {
  const match = skillMarkdown.match(/^---\n(?<frontmatter>[\s\S]*?)\n---/);
  assert.ok(match, 'SKILL.md should contain YAML frontmatter');
  const description = match.groups.frontmatter
    .split('\n')
    .find((line) => line.startsWith('description: '));
  assert.ok(description, 'SKILL.md frontmatter should contain description');
  return description.slice('description: '.length);
}

test('skill trigger description is explicitly WSL-only', () => {
  const description = frontmatterDescription(readSkillFile('SKILL.md'));

  assert.match(description, /^Use only when /);
  assert.match(description, /\bWSL2?\b/);
  assert.match(description, /Do not use for native Windows, macOS, Linux desktop, containers, or remote browser services\./);
});

test('OpenAI skill metadata keeps the WSL-only prompt surface', () => {
  const metadata = readSkillFile('agents/openai.yaml');

  assert.match(metadata, /short_description: "WSL2-only Windows Chrome control"/);
  assert.match(metadata, /default_prompt: "Use \$windows-chrome-playwright-mcp only from WSL2/);
});

test('SKILL.md stays as a small applicability gate', () => {
  const skillMarkdown = readSkillFile('SKILL.md');

  assert.ok(skillMarkdown.length <= 2200, `SKILL.md is ${skillMarkdown.length} bytes`);
  assert.ok(skillMarkdown.split(/\s+/).filter(Boolean).length <= 300);
  assert.doesNotMatch(skillMarkdown, /## Sandbox Escalation/);
  assert.doesNotMatch(skillMarkdown, /## Browser Workflow/);
  assert.doesNotMatch(skillMarkdown, /## Safety Rules/);
  assert.match(skillMarkdown, /references\/operating-guide\.md/);
});

test('operating guide contains detailed browser workflow after applicability passes', () => {
  const guide = readSkillFile('references/operating-guide.md');

  assert.match(guide, /## Sandbox Escalation/);
  assert.match(guide, /## Browser Workflow/);
  assert.match(guide, /## Safety Rules/);
  assert.match(guide, /references\/browser-interaction-idioms\.md/);
  assert.match(guide, /references\/troubleshooting\.md/);
});
