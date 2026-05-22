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

function frontmatterName(skillMarkdown) {
  const match = skillMarkdown.match(/^---\n(?<frontmatter>[\s\S]*?)\n---/);
  assert.ok(match, 'SKILL.md should contain YAML frontmatter');
  const name = match.groups.frontmatter
    .split('\n')
    .find((line) => line.startsWith('name: '));
  assert.ok(name, 'SKILL.md frontmatter should contain name');
  return name.slice('name: '.length);
}

test('skill identity is playwright-wsl', () => {
  assert.equal(path.basename(skillDir), 'playwright-wsl');
  assert.equal(frontmatterName(readSkillFile('SKILL.md')), 'playwright-wsl');
});

test('skill trigger description is explicitly WSL-only', () => {
  const description = frontmatterDescription(readSkillFile('SKILL.md'));

  assert.match(description, /^Use only when /);
  assert.match(description, /\bWSL2?\b/);
  assert.match(description, /Do not use for native Windows, macOS, Linux desktop, containers, or remote browser services\./);
});

test('OpenAI skill metadata keeps the WSL-only prompt surface', () => {
  const metadata = readSkillFile('agents/openai.yaml');

  assert.match(metadata, /short_description: "WSL2-only Windows Chrome control"/);
  assert.match(metadata, /display_name: "Playwright WSL"/);
  assert.match(metadata, /default_prompt: "Use \$playwright-wsl only from WSL2/);
  assert.match(metadata, /persistent Playwright CLI session/);
  assert.doesNotMatch(metadata, /Playwright MCP/);
  assert.doesNotMatch(metadata, /wsl-playwright/);
  assert.doesNotMatch(metadata, /windows-chrome-playwright-cli/);
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
  assert.match(guide, /persistent Playwright CLI session/);
  assert.match(guide, /Do not detach or stop Chrome between ordinary page operations/);
  assert.match(guide, /automatically installs local Playwright CLI dependencies/);
  assert.match(guide, /%LOCALAPPDATA%\\Codex\\playwright-wsl\\profile/);
  assert.match(guide, /references\/browser-interaction-idioms\.md/);
  assert.match(guide, /references\/troubleshooting\.md/);
  assert.doesNotMatch(guide, /MCP server/);
  assert.doesNotMatch(guide, /playwright-mcp/);
  assert.doesNotMatch(guide, /wsl-playwright/);
  assert.doesNotMatch(guide, /windows-chrome-playwright-cli/);
});

test('doctor preflight installs Playwright CLI automatically', () => {
  const doctor = readSkillFile('scripts/doctor.mjs');

  assert.match(doctor, /ensure-playwright-cli\.mjs/);
  assert.match(doctor, /Playwright CLI installation failed/);
  assert.match(doctor, /mode !== '--chrome-only'/);
});
