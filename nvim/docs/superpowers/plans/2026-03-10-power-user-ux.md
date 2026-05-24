# Power User UX Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the current Neovim config into a more discoverable, workflow-oriented power-user setup without replacing the existing core.

**Architecture:** Keep the current modular layout and add a small number of high-impact workflow plugins in the existing plugin modules. Reconfigure current plugins first, then layer in diagnostics, symbols, notifications, git review, sessions, and working-set navigation where they fit naturally.

**Tech Stack:** `lazy.nvim`, `which-key.nvim`, `telescope.nvim`, `neo-tree.nvim`, `blink.cmp`, `nvim-lspconfig`, `conform.nvim`, `nvim-lint`, `gitsigns.nvim`, `nvim-dap`, plus focused additions like `trouble.nvim`, `aerial.nvim`, `nvim-notify`, `noice.nvim`, `persistence.nvim`, `harpoon`, `neogit`, `diffview.nvim`, and `nvim-dap-virtual-text`.

---

## Chunk 1: Discoverability And Navigation

### Task 1: Improve keymap discoverability and file/buffer navigation

**Files:**
- Modify: `lua/plugins/ui.lua`
- Modify: `lua/plugins/navigation.lua`

- [ ] Add richer `which-key` groups for files, buffers, git, diagnostics, LSP, debug, sessions, and tests.
- [ ] Add a clearer tree toggle mapping such as `<leader>e`, while keeping `\` reveal if useful.
- [ ] Improve Neo-tree behavior with current-file following and git/diagnostic visibility.
- [ ] Improve Telescope defaults for repeated navigation, including smarter path display and hidden-file aware pickers.
- [ ] Add a working-set workflow with a bookmark/jump tool.
- [ ] Verify keymaps load and help entries appear.

### Task 2: Add structural navigation and session flow

**Files:**
- Modify: `lua/plugins/navigation.lua`
- Modify: `lua/plugins/ui.lua`

- [ ] Add an outline/symbol navigation plugin for large files.
- [ ] Add session persistence so projects reopen with buffers and layout intact.
- [ ] Add keymaps that expose both features under the new leader groups.
- [ ] Verify startup and basic picker behavior headlessly.

## Chunk 2: Diagnostics, Messages, And Completion UX

### Task 3: Improve diagnostics and message handling

**Files:**
- Modify: `lua/plugins/lsp.lua`
- Modify: `lua/plugins/ui.lua`

- [ ] Add a dedicated diagnostics/problems view plugin.
- [ ] Add next/prev diagnostic keymaps and a direct diagnostic float mapping.
- [ ] Reduce editing noise from diagnostics while keeping fast access to detail.
- [ ] Add a persistent notification/message layer for formatter, LSP, and command feedback.
- [ ] Verify diagnostics still publish correctly and the UI loads.

### Task 4: Improve completion ergonomics

**Files:**
- Modify: `lua/plugins/lsp.lua`

- [ ] Add buffer completion source and slightly stronger completion discoverability.
- [ ] Improve docs/signature behavior and explicit completion trigger ergonomics.
- [ ] Keep the setup lightweight enough to avoid menu spam.
- [ ] Verify completion config loads without errors.

## Chunk 3: Git And Debug Workflow

### Task 5: Add repo-level git workflow UX

**Files:**
- Modify: `lua/plugins/git.lua`

- [ ] Keep gitsigns for hunk-level edits.
- [ ] Add a top-level git workflow namespace.
- [ ] Add repo-level status/review/history tools.
- [ ] Add keymaps for status, file history, diff review, and branch-oriented navigation.
- [ ] Verify git plugins lazy-load cleanly.

### Task 6: Add debugging quality-of-life features

**Files:**
- Modify: `lua/plugins/debug.lua`

- [ ] Add virtual text for live variable values.
- [ ] Expand DAP mappings to include restart/terminate/run-last/eval or hover actions.
- [ ] Keep Go debugging intact.
- [ ] Verify the DAP config loads without regressions.

## Chunk 4: Verification

### Task 7: Verify the full UX upgrade set

**Files:**
- Modify as needed: `lua/plugins/*.lua`

- [ ] Run `nvim --headless "+quitall"` in the worktree.
- [ ] Run `nvim --headless "+Lazy! sync" "+quitall"` if needed to validate plugin specs.
- [ ] Open representative headless checks for diagnostics, git plugin availability, and navigation plugin loading.
- [ ] Summarize what changed and note any optional future upgrades not included in this pass.
