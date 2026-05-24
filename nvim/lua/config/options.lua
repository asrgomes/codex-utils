local function has_clipboard_provider()
  local executables = {
    'pbcopy',
    'wl-copy',
    'xclip',
    'xsel',
    'win32yank.exe',
    'clip.exe',
    'termux-clipboard-set',
  }

  for _, executable in ipairs(executables) do
    if vim.fn.executable(executable) == 1 then
      return true
    end
  end

  return false
end

vim.o.number = true
vim.o.mouse = 'a'
vim.o.showmode = false

if has_clipboard_provider() then
  vim.schedule(function()
    vim.o.clipboard = 'unnamedplus'
  end)
end

vim.o.breakindent = true
vim.o.expandtab = true
vim.o.tabstop = 4
vim.o.softtabstop = 4
vim.o.shiftwidth = 4
vim.o.undofile = true
vim.o.ignorecase = true
vim.o.smartcase = true
vim.o.signcolumn = 'yes'
vim.o.updatetime = 250
vim.o.timeoutlen = 300
vim.o.splitright = true
vim.o.splitbelow = true
vim.o.list = true
vim.opt.listchars = { tab = '» ', trail = '·', nbsp = '␣' }
vim.o.inccommand = 'split'
vim.o.cursorline = true
vim.o.scrolloff = 10
vim.o.confirm = true
