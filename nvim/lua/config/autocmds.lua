vim.api.nvim_create_autocmd('TextYankPost', {
  desc = 'Highlight when yanking text',
  group = vim.api.nvim_create_augroup('config-highlight-yank', { clear = true }),
  callback = function()
    vim.hl.on_yank()
  end,
})

vim.api.nvim_create_autocmd('FileType', {
  desc = 'Use 2-space indentation for shell scripts',
  group = vim.api.nvim_create_augroup('config-shell-indent', { clear = true }),
  pattern = { 'bash', 'sh', 'zsh' },
  callback = function(args)
    vim.bo[args.buf].tabstop = 2
    vim.bo[args.buf].softtabstop = 2
    vim.bo[args.buf].shiftwidth = 2
  end,
})
