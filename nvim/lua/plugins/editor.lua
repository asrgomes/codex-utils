local default_markdownlint_config = vim.fn.stdpath 'config' .. '/.markdownlint.json'
local default_prettier_config = vim.fn.stdpath 'config' .. '/.prettierrc.json'

local function find_upward(startpath, names)
  local found = vim.fs.find(names, {
    path = vim.fs.dirname(startpath),
    upward = true,
  })

  return found[1]
end

local function read_json(path)
  local file = io.open(path, 'r')
  if not file then
    return nil
  end

  local content = file:read '*a'
  file:close()

  local ok, decoded = pcall(vim.json.decode, content)
  if ok then
    return decoded
  end

  return nil
end

local function find_prettier_config(path)
  local names = {
    '.prettierrc',
    '.prettierrc.json',
    '.prettierrc.yml',
    '.prettierrc.yaml',
    '.prettierrc.json5',
    '.prettierrc.js',
    '.prettierrc.cjs',
    '.prettierrc.mjs',
    '.prettierrc.toml',
    'prettier.config.js',
    'prettier.config.cjs',
    'prettier.config.mjs',
  }

  local config = find_upward(path, names)
  if config then
    return config
  end

  local package_json = find_upward(path, { 'package.json' })
  if package_json then
    local package_data = read_json(package_json)
    if package_data and package_data.prettier then
      return package_json
    end
  end

  return default_prettier_config
end

local function find_markdownlint_config(path)
  local names = {
    '.markdownlint.json',
    '.markdownlint.jsonc',
    '.markdownlint.yaml',
    '.markdownlint.yml',
    '.markdownlint.cjs',
    '.markdownlint.mjs',
    '.markdownlint-cli2.jsonc',
    '.markdownlint-cli2.yaml',
    '.markdownlint-cli2.yml',
    '.markdownlint-cli2.cjs',
    '.markdownlint-cli2.mjs',
  }

  return find_upward(path, names) or default_markdownlint_config
end

local function get_first_treesitter_capture(match, capture_id)
  local nodes = match[capture_id]
  if type(nodes) == 'table' then
    return nodes[1]
  end
  return nodes
end

local function install_treesitter_query_compat()
  if vim.fn.has 'nvim-0.12' == 0 then
    return
  end

  local query = require 'vim.treesitter.query'
  local opts = { force = true }

  local html_script_type_languages = {
    ['application/ecmascript'] = 'javascript',
    importmap = 'json',
    module = 'javascript',
    ['text/ecmascript'] = 'javascript',
  }

  local non_filetype_match_injection_language_aliases = {
    ex = 'elixir',
    pl = 'perl',
    sh = 'bash',
    ts = 'typescript',
    uxn = 'uxntal',
  }

  local function get_parser_from_markdown_info_string(injection_alias)
    local match = vim.filetype.match { filename = 'a.' .. injection_alias }
    return match or non_filetype_match_injection_language_aliases[injection_alias] or injection_alias
  end

  local function valid_args(name, pred, count, strict_count)
    local arg_count = #pred - 1

    if strict_count then
      if arg_count ~= count then
        vim.api.nvim_err_writeln(string.format('%s must have exactly %d arguments', name, count))
        return false
      end
    elseif arg_count < count then
      vim.api.nvim_err_writeln(string.format('%s must have at least %d arguments', name, count))
      return false
    end

    return true
  end

  -- Neovim 0.12 passes capture lists to query handlers. Older nvim-treesitter
  -- handlers still expect one TSNode per capture, so keep their old behavior.
  query.add_predicate('nth?', function(match, _, _, pred)
    if not valid_args('nth?', pred, 2, true) then
      return
    end

    local node = get_first_treesitter_capture(match, pred[2])
    local n = tonumber(pred[3])
    if node and node:parent() and node:parent():named_child_count() > n then
      return node:parent():named_child(n) == node
    end

    return false
  end, opts)

  query.add_predicate('is?', function(match, _, bufnr, pred)
    if not valid_args('is?', pred, 2) then
      return
    end

    local node = get_first_treesitter_capture(match, pred[2])
    if not node then
      return true
    end

    local locals = require 'nvim-treesitter.locals'
    local types = { unpack(pred, 3) }
    local _, _, kind = locals.find_definition(node, bufnr)

    return vim.tbl_contains(types, kind)
  end, opts)

  query.add_predicate('kind-eq?', function(match, _, _, pred)
    if not valid_args(pred[1], pred, 2) then
      return
    end

    local node = get_first_treesitter_capture(match, pred[2])
    local types = { unpack(pred, 3) }

    if not node then
      return true
    end

    return vim.tbl_contains(types, node:type())
  end, opts)

  query.add_directive('set-lang-from-mimetype!', function(match, _, bufnr, pred, metadata)
    local node = get_first_treesitter_capture(match, pred[2])
    if not node then
      return
    end

    local type_attr_value = vim.treesitter.get_node_text(node, bufnr)
    local configured = html_script_type_languages[type_attr_value]
    if configured then
      metadata['injection.language'] = configured
    else
      local parts = vim.split(type_attr_value, '/', {})
      metadata['injection.language'] = parts[#parts]
    end
  end, opts)

  query.add_directive('set-lang-from-info-string!', function(match, _, bufnr, pred, metadata)
    local node = get_first_treesitter_capture(match, pred[2])
    if not node then
      return
    end

    local injection_alias = vim.treesitter.get_node_text(node, bufnr):lower()
    metadata['injection.language'] = get_parser_from_markdown_info_string(injection_alias)
  end, opts)

  query.add_directive('make-range!', function() end, opts)

  query.add_directive('downcase!', function(match, _, bufnr, pred, metadata)
    local id = pred[2]
    local node = get_first_treesitter_capture(match, id)
    if not node then
      return
    end

    metadata[id] = metadata[id] or {}
    local text = vim.treesitter.get_node_text(node, bufnr, { metadata = metadata[id] }) or ''
    metadata[id].text = string.lower(text)
  end, opts)
end

return {
  {
    'windwp/nvim-autopairs',
    event = 'InsertEnter',
    opts = {},
  },
  {
    'mfussenegger/nvim-lint',
    event = { 'BufReadPre', 'BufNewFile' },
    config = function()
      local lint = require 'lint'

      lint.linters_by_ft = {
        bash = { 'shellcheck' },
        sh = { 'shellcheck' },
        javascript = { 'eslint_d' },
        javascriptreact = { 'eslint_d' },
        typescript = { 'eslint_d' },
        typescriptreact = { 'eslint_d' },
        zsh = { 'shellcheck' },
      }

      if vim.fn.executable 'markdownlint' == 1 then
        lint.linters.markdownlint.args = {
          '--config',
          function()
            return find_markdownlint_config(vim.api.nvim_buf_get_name(0))
          end,
          '--stdin',
        }
        lint.linters_by_ft.markdown = { 'markdownlint' }
      end

      local group = vim.api.nvim_create_augroup('config-lint', { clear = true })
      vim.api.nvim_create_autocmd({ 'BufEnter', 'BufWritePost', 'InsertLeave' }, {
        group = group,
        callback = function()
          local filetype = vim.bo.filetype
          if vim.bo.buftype == '' and lint.linters_by_ft[filetype] then
            lint.try_lint()
          end
        end,
      })
    end,
  },
  {
    'stevearc/conform.nvim',
    event = { 'BufWritePre' },
    cmd = { 'ConformInfo' },
    keys = {
      {
        '<leader>f',
        function()
          require('conform').format { async = true, lsp_format = 'fallback' }
        end,
        mode = '',
        desc = '[F]ormat buffer',
      },
    },
    opts = {
      formatters = {
        markdownlint = {
          prepend_args = function(_, ctx)
            return {
              '--config',
              find_markdownlint_config(ctx.filename),
            }
          end,
        },
        prettier = {
          prepend_args = function(_, ctx)
            return {
              '--config',
              find_prettier_config(ctx.filename),
            }
          end,
        },
        prettierd = {
          prepend_args = function(_, ctx)
            return {
              '--config',
              find_prettier_config(ctx.filename),
            }
          end,
        },
        xmllint = {
          env = {
            XMLLINT_INDENT = '    ',
          },
        },
      },
      notify_on_error = false,
      format_on_save = function(bufnr)
        local disable_filetypes = { c = true, cpp = true }
        if disable_filetypes[vim.bo[bufnr].filetype] then
          return nil
        end

        return {
          timeout_ms = 500,
          lsp_format = 'fallback',
        }
      end,
      formatters_by_ft = {
        bash = { 'shfmt' },
        clojure = { 'cljfmt' },
        edn = { 'cljfmt' },
        javascript = { 'prettierd', 'prettier' },
        javascriptreact = { 'prettierd', 'prettier' },
        lua = { 'stylua' },
        markdown = { 'prettier', 'markdownlint' },
        sh = { 'shfmt' },
        typescript = { 'prettierd', 'prettier' },
        typescriptreact = { 'prettierd', 'prettier' },
        xml = { 'xmllint' },
        zsh = { 'shfmt' },
      },
    },
  },
  {
    'nvim-treesitter/nvim-treesitter',
    build = ':TSUpdate',
    event = { 'BufReadPost', 'BufNewFile' },
    main = 'nvim-treesitter.configs',
    config = function(_, opts)
      install_treesitter_query_compat()
      require('nvim-treesitter.configs').setup(opts)
    end,
    opts = {
      ensure_installed = {
        'bash',
        'c',
        'clojure',
        'diff',
        'html',
        'javascript',
        'jsdoc',
        'json',
        'jsonc',
        'lua',
        'luadoc',
        'markdown',
        'markdown_inline',
        'query',
        'tsx',
        'typescript',
        'vim',
        'vimdoc',
      },
      auto_install = true,
      highlight = {
        enable = true,
        additional_vim_regex_highlighting = { 'ruby' },
      },
      indent = { enable = true, disable = { 'ruby' } },
    },
  },
}
