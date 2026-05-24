return {
  {
    'Olical/conjure',
    ft = { 'clojure', 'clojurescript', 'edn', 'fennel', 'scheme' },
    init = function()
      -- Keep K available for normal LSP hover/documentation behavior.
      vim.g['conjure#mapping#doc_word'] = false
    end,
    config = function()
      local clojure_filetypes = {
        clojure = true,
        clojurescript = true,
        edn = true,
      }

      local function set_clojure_keymaps(bufnr)
        local opts = { buffer = bufnr, silent = true }

        vim.keymap.set(
          'n',
          '<leader>cc',
          '<cmd>ConjureConnect<CR>',
          vim.tbl_extend('force', opts, {
            desc = '[C]lojure [C]onnect REPL',
          })
        )
        vim.keymap.set(
          'n',
          '<leader>ce',
          '<cmd>ConjureEvalCurrentForm<CR>',
          vim.tbl_extend('force', opts, {
            desc = '[C]lojure [E]val form',
          })
        )
        vim.keymap.set(
          'n',
          '<leader>cE',
          '<cmd>ConjureEvalRootForm<CR>',
          vim.tbl_extend('force', opts, {
            desc = '[C]lojure Eval root form',
          })
        )
        vim.keymap.set(
          'n',
          '<leader>cb',
          '<cmd>ConjureEvalBuf<CR>',
          vim.tbl_extend('force', opts, {
            desc = '[C]lojure Eval [B]uffer',
          })
        )
        vim.keymap.set(
          'n',
          '<leader>cf',
          '<cmd>ConjureEvalFile<CR>',
          vim.tbl_extend('force', opts, {
            desc = '[C]lojure Eval [F]ile',
          })
        )
        vim.keymap.set(
          'n',
          '<leader>cl',
          '<cmd>ConjureLogToggle<CR>',
          vim.tbl_extend('force', opts, {
            desc = '[C]lojure [L]og',
          })
        )
        vim.keymap.set(
          'v',
          '<leader>ce',
          '<cmd>ConjureEvalVisual<CR>',
          vim.tbl_extend('force', opts, {
            desc = '[C]lojure [E]val selection',
          })
        )
      end

      local group = vim.api.nvim_create_augroup('config-clojure-conjure', { clear = true })

      vim.api.nvim_create_autocmd('FileType', {
        group = group,
        pattern = { 'clojure', 'clojurescript', 'edn' },
        callback = function(event)
          set_clojure_keymaps(event.buf)
        end,
      })

      local current_buf = vim.api.nvim_get_current_buf()
      if clojure_filetypes[vim.bo[current_buf].filetype] then
        set_clojure_keymaps(current_buf)
      end

      local ok, wk = pcall(require, 'which-key')
      if ok then
        wk.add {
          { '<leader>c', group = '[C]lojure' },
        }
      end
    end,
  },
}
