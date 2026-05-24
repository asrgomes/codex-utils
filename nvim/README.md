# Neovim Config

Personal Neovim configuration built around `lazy.nvim` with a small bootstrap and modular Lua files.

## Layout

- `init.lua` - entrypoint; loads `lua/config`
- `lua/config/` - editor setup and startup wiring
- `lua/plugins/` - lazy plugin specs grouped by concern

## Config Modules

- `lua/config/globals.lua` - leader keys and global flags
- `lua/config/options.lua` - editor options
- `lua/config/keymaps.lua` - non-plugin keymaps
- `lua/config/autocmds.lua` - global autocommands
- `lua/config/lazy.lua` - `lazy.nvim` bootstrap and plugin import

## Plugin Groups

- `lua/plugins/ui.lua` - colorscheme, statusline, which-key, UI helpers
- `lua/plugins/navigation.lua` - Telescope and Neo-tree
- `lua/plugins/editor.lua` - formatting, linting, Treesitter, autopairs
- `lua/plugins/lsp.lua` - LSP, Mason, completion
- `lua/plugins/git.lua` - gitsigns, Neogit, Diffview
- `lua/plugins/debug.lua` - DAP debugging
- `lua/plugins/clojure.lua` - Clojure REPL workflow
- `lua/plugins/csv.lua` - CSV/TSV table view

## Requirements

- Neovim `0.11+`
- `git`, `make`, `unzip`, `rg`
- Bash support: `bash-language-server`, `shellcheck`, `shfmt`
- Clojure support: `clojure-lsp`, `cljfmt`
- optional clipboard provider such as `xclip`, `xsel`, `wl-copy`, or `pbcopy`
- a Nerd Font if `vim.g.have_nerd_font = true`

## Common Commands

```sh
nvim
nvim --headless "+quitall"
```

Inside Neovim:

- `:Lazy` - plugin status
- `:Mason` - LSP/tool management
- `:ConformInfo` - formatter status
- `:LspInfo` - active language servers

## Notes

- Plugin definitions are intentionally grouped by concern rather than by individual plugin.
- This repo tracks configuration only; external tools are installed separately or through Mason.
