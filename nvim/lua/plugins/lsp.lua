local function lsp_map(event, keys, func, desc, mode)
  vim.keymap.set(mode or 'n', keys, func, { buffer = event.buf, desc = 'LSP: ' .. desc })
end

local function setup_diagnostics()
  vim.keymap.set('n', '[d', function()
    vim.diagnostic.jump { count = -1, float = true }
  end, { desc = 'Previous diagnostic' })
  vim.keymap.set('n', ']d', function()
    vim.diagnostic.jump { count = 1, float = true }
  end, { desc = 'Next diagnostic' })
  vim.keymap.set('n', '<leader>xd', function()
    vim.diagnostic.open_float(nil, { scope = 'line' })
  end, { desc = 'Line [D]iagnostics' })

  vim.diagnostic.config {
    severity_sort = true,
    update_in_insert = false,
    float = { border = 'rounded', focusable = false, source = 'if_many' },
    underline = { severity = vim.diagnostic.severity.ERROR },
    signs = vim.g.have_nerd_font and {
      text = {
        [vim.diagnostic.severity.ERROR] = '󰅚 ',
        [vim.diagnostic.severity.WARN] = '󰀪 ',
        [vim.diagnostic.severity.INFO] = '󰋽 ',
        [vim.diagnostic.severity.HINT] = '󰌶 ',
      },
    } or {},
    virtual_text = false,
  }
end

return {
  {
    'folke/lazydev.nvim',
    ft = 'lua',
    opts = {
      library = {
        { path = '${3rd}/luv/library', words = { 'vim%.uv' } },
      },
    },
  },
  {
    'nvim-java/nvim-java',
    ft = 'java',
    dependencies = {
      'MunifTanjim/nui.nvim',
      'mfussenegger/nvim-dap',
      {
        'JavaHello/spring-boot.nvim',
        commit = '218c0c26c14d99feca778e4d13f5ec3e8b1b60f0',
      },
    },
    config = function()
      local java_21_home = vim.fn.expand '~/tools/jdk-21'
      local java_21_bin = java_21_home .. '/bin'

      require('java').setup {
        jdk = {
          auto_install = false,
          version = '21',
        },
        log = {
          use_console = false,
        },
      }

      vim.lsp.config('jdtls', {
        cmd_env = {
          JAVA_HOME = java_21_home,
          PATH = java_21_bin .. ':' .. vim.env.PATH,
          JAVA_TOOL_OPTIONS = '-Xmx4G',
        },
        settings = {
          java = {
            configuration = {
              runtimes = {
                {
                  name = 'JavaSE-21',
                  path = java_21_home,
                  default = true,
                },
              },
            },
          },
        },
      })

      vim.lsp.enable 'jdtls'
    end,
  },
  {
    'neovim/nvim-lspconfig',
    lazy = false,
    init = function()
      setup_diagnostics()
    end,
    dependencies = {
      { 'mason-org/mason.nvim', opts = {} },
      'mason-org/mason-lspconfig.nvim',
      'WhoIsSethDaniel/mason-tool-installer.nvim',
      { 'j-hui/fidget.nvim', opts = {} },
      'saghen/blink.cmp',
    },
    config = function()
      local lsp_attach_group = vim.api.nvim_create_augroup('config-lsp-attach', { clear = true })
      local lsp_highlight_group = vim.api.nvim_create_augroup('config-lsp-highlight', { clear = true })
      local lsp_detach_group = vim.api.nvim_create_augroup('config-lsp-detach', { clear = true })

      vim.api.nvim_create_autocmd('LspAttach', {
        group = lsp_attach_group,
        callback = function(event)
          lsp_map(event, 'grn', vim.lsp.buf.rename, '[R]e[n]ame')
          lsp_map(event, 'gra', vim.lsp.buf.code_action, '[G]oto Code [A]ction', { 'n', 'x' })
          lsp_map(event, 'grr', require('telescope.builtin').lsp_references, '[G]oto [R]eferences')
          lsp_map(event, 'gri', require('telescope.builtin').lsp_implementations, '[G]oto [I]mplementation')
          lsp_map(event, 'grd', require('telescope.builtin').lsp_definitions, '[G]oto [D]efinition')
          lsp_map(event, 'grD', vim.lsp.buf.declaration, '[G]oto [D]eclaration')
          lsp_map(event, 'gO', require('telescope.builtin').lsp_document_symbols, 'Open Document Symbols')
          lsp_map(event, 'gW', require('telescope.builtin').lsp_dynamic_workspace_symbols, 'Open Workspace Symbols')
          lsp_map(event, 'grt', require('telescope.builtin').lsp_type_definitions, '[G]oto [T]ype Definition')

          local client = vim.lsp.get_client_by_id(event.data.client_id)
          if not client then
            return
          end

          if client.name == 'jdtls' then
            lsp_map(event, '<leader>jr', '<cmd>JavaRunnerRunMain<CR>', '[J]ava [R]un Main')
            lsp_map(event, '<leader>js', '<cmd>JavaRunnerStopMain<CR>', '[J]ava [S]top Main')
            lsp_map(event, '<leader>jl', '<cmd>JavaRunnerToggleLogs<CR>', '[J]ava Toggle [L]ogs')
            lsp_map(event, '<leader>jc', '<cmd>JavaTestRunCurrentClass<CR>', '[J]ava Test [C]lass')
            lsp_map(event, '<leader>jm', '<cmd>JavaTestRunCurrentMethod<CR>', '[J]ava Test [M]ethod')
            lsp_map(event, '<leader>jv', '<cmd>JavaTestViewLastReport<CR>', '[J]ava Test [V]iew Report')
            lsp_map(event, '<leader>ja', '<cmd>JavaTestRunAllTests<CR>', '[J]ava Test [A]ll')
            lsp_map(event, '<leader>jd', '<cmd>JavaTestDebugCurrentClass<CR>', '[J]ava Test [D]ebug Class')
            lsp_map(event, '<leader>jp', '<cmd>JavaProfile<CR>', '[J]ava [P]rofile')
            lsp_map(event, '<leader>jR', '<cmd>JavaSettingsChangeRuntime<CR>', '[J]ava Change [R]untime')
          end

          if client:supports_method(vim.lsp.protocol.Methods.textDocument_documentHighlight, event.buf) then
            vim.api.nvim_create_autocmd({ 'CursorHold', 'CursorHoldI' }, {
              group = lsp_highlight_group,
              buffer = event.buf,
              callback = vim.lsp.buf.document_highlight,
            })

            vim.api.nvim_create_autocmd({ 'CursorMoved', 'CursorMovedI' }, {
              group = lsp_highlight_group,
              buffer = event.buf,
              callback = vim.lsp.buf.clear_references,
            })

            vim.api.nvim_create_autocmd('LspDetach', {
              group = lsp_detach_group,
              buffer = event.buf,
              once = true,
              callback = function(detach_event)
                vim.lsp.buf.clear_references()
                vim.api.nvim_clear_autocmds { group = lsp_highlight_group, buffer = detach_event.buf }
              end,
            })
          end

          if client:supports_method(vim.lsp.protocol.Methods.textDocument_inlayHint, event.buf) then
            lsp_map(event, '<leader>th', function()
              local enabled = vim.lsp.inlay_hint.is_enabled { bufnr = event.buf }
              vim.lsp.inlay_hint.enable(not enabled, { bufnr = event.buf })
            end, '[T]oggle Inlay [H]ints')
          end
        end,
      })

      local capabilities = require('blink.cmp').get_lsp_capabilities()
      local root_pattern = require('lspconfig.util').root_pattern
      local servers = {
        bashls = {
          filetypes = { 'bash', 'sh' },
          root_dir = function(bufnr, on_dir)
            local path = vim.api.nvim_buf_get_name(bufnr)
            on_dir(root_pattern '.git'(path) or vim.fs.dirname(path))
          end,
        },
        clojure_lsp = {
          filetypes = { 'clojure', 'clojurescript', 'edn' },
        },
        jsonls = {
          filetypes = { 'json', 'jsonc' },
        },
        lua_ls = {
          settings = {
            Lua = {
              completion = {
                callSnippet = 'Replace',
              },
            },
          },
        },
        ts_ls = {
          filetypes = { 'javascript', 'javascriptreact', 'typescript', 'typescriptreact' },
          init_options = {
            hostInfo = 'neovim',
          },
          settings = {
            javascript = {
              inlayHints = {
                includeInlayEnumMemberValueHints = true,
                includeInlayFunctionLikeReturnTypeHints = true,
                includeInlayFunctionParameterTypeHints = true,
                includeInlayParameterNameHints = 'all',
                includeInlayParameterNameHintsWhenArgumentMatchesName = false,
                includeInlayPropertyDeclarationTypeHints = true,
                includeInlayVariableTypeHints = false,
              },
            },
            typescript = {
              inlayHints = {
                includeInlayEnumMemberValueHints = true,
                includeInlayFunctionLikeReturnTypeHints = true,
                includeInlayFunctionParameterTypeHints = true,
                includeInlayParameterNameHints = 'all',
                includeInlayParameterNameHintsWhenArgumentMatchesName = false,
                includeInlayPropertyDeclarationTypeHints = true,
                includeInlayVariableTypeHints = false,
              },
            },
          },
        },
      }

      local ensure_installed = vim.tbl_keys(servers)
      vim.list_extend(ensure_installed, {
        'clojure-lsp',
        'cljfmt',
        'eslint_d',
        'shellcheck',
        'shfmt',
        'stylua',
        'prettierd',
        'typescript-language-server',
      })

      require('mason-tool-installer').setup {
        ensure_installed = ensure_installed,
        integrations = {
          ['mason-lspconfig'] = true,
          ['mason-nvim-dap'] = false,
          ['mason-null-ls'] = false,
        },
      }

      require('mason-lspconfig').setup {
        ensure_installed = {},
        automatic_installation = false,
        automatic_enable = false,
      }

      for server_name, server in pairs(servers) do
        server.capabilities = vim.tbl_deep_extend('force', {}, capabilities, server.capabilities or {})
        vim.lsp.config(server_name, server)
        vim.lsp.enable(server_name)
      end
    end,
  },
  {
    'saghen/blink.cmp',
    event = 'VimEnter',
    version = '1.*',
    dependencies = {
      {
        'L3MON4D3/LuaSnip',
        version = '2.*',
        build = (function()
          if vim.fn.has 'win32' == 1 or vim.fn.executable 'make' == 0 then
            return
          end

          return 'make install_jsregexp'
        end)(),
        opts = {},
      },
    },
    opts = {
      keymap = {
        preset = 'default',
        ['<CR>'] = { 'accept', 'fallback' },
        ['<C-Space>'] = { 'show', 'show_documentation', 'hide_documentation' },
      },
      appearance = {
        nerd_font_variant = 'mono',
      },
      completion = {
        documentation = { auto_show = true, auto_show_delay_ms = 300, update_delay_ms = 100 },
      },
      sources = {
        default = { 'lsp', 'path', 'snippets', 'buffer', 'lazydev' },
        providers = {
          buffer = {
            score_offset = -8,
            min_keyword_length = function(ctx)
              if ctx.trigger.initial_kind == 'manual' then
                return 0
              end

              return 4
            end,
            max_items = 5,
            opts = {
              get_bufnrs = function()
                local bufnrs = { vim.api.nvim_get_current_buf() }
                local seen = { [bufnrs[1]] = true }

                for _, winid in ipairs(vim.api.nvim_tabpage_list_wins(0)) do
                  local bufnr = vim.api.nvim_win_get_buf(winid)
                  if not seen[bufnr] and vim.bo[bufnr].buflisted and vim.bo[bufnr].buftype == '' then
                    table.insert(bufnrs, bufnr)
                    seen[bufnr] = true
                  end
                end

                return bufnrs
              end,
            },
          },
          lazydev = { module = 'lazydev.integrations.blink', score_offset = 100 },
        },
      },
      snippets = { preset = 'luasnip' },
      fuzzy = { implementation = 'lua' },
      signature = {
        enabled = true,
        trigger = {
          show_on_keyword = false,
          show_on_trigger_character = true,
          show_on_insert = false,
          show_on_insert_on_trigger_character = true,
        },
      },
    },
  },
}
