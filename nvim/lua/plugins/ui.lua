local indent_highlights = {
  'RainbowRed',
  'RainbowYellow',
  'RainbowBlue',
  'RainbowOrange',
  'RainbowGreen',
  'RainbowViolet',
  'RainbowCyan',
}

local function set_indent_highlights()
  vim.api.nvim_set_hl(0, 'RainbowRed', { fg = '#E06C75' })
  vim.api.nvim_set_hl(0, 'RainbowYellow', { fg = '#E5C07B' })
  vim.api.nvim_set_hl(0, 'RainbowBlue', { fg = '#61AFEF' })
  vim.api.nvim_set_hl(0, 'RainbowOrange', { fg = '#D19A66' })
  vim.api.nvim_set_hl(0, 'RainbowGreen', { fg = '#98C379' })
  vim.api.nvim_set_hl(0, 'RainbowViolet', { fg = '#C678DD' })
  vim.api.nvim_set_hl(0, 'RainbowCyan', { fg = '#56B6C2' })
end

return {
  {
    'folke/which-key.nvim',
    event = 'VeryLazy',
    opts = {
      delay = 0,
      icons = {
        mappings = vim.g.have_nerd_font,
        keys = vim.g.have_nerd_font and {} or {
          Up = '<Up> ',
          Down = '<Down> ',
          Left = '<Left> ',
          Right = '<Right> ',
          C = '<C-...> ',
          M = '<M-...> ',
          D = '<D-...> ',
          S = '<S-...> ',
          CR = '<CR> ',
          Esc = '<Esc> ',
          ScrollWheelDown = '<ScrollWheelDown> ',
          ScrollWheelUp = '<ScrollWheelUp> ',
          NL = '<NL> ',
          BS = '<BS> ',
          Space = '<Space> ',
          Tab = '<Tab> ',
          F1 = '<F1>',
          F2 = '<F2>',
          F3 = '<F3>',
          F4 = '<F4>',
          F5 = '<F5>',
          F6 = '<F6>',
          F7 = '<F7>',
          F8 = '<F8>',
          F9 = '<F9>',
          F10 = '<F10>',
          F11 = '<F11>',
          F12 = '<F12>',
        },
      },
      spec = {
        { '<leader>F', group = '[F]iles' },
        { '<leader><tab>', group = '[B]uffers' },
        { '<leader>d', group = '[D]ebug' },
        { '<leader>g', group = '[G]it' },
        { '<leader>j', group = '[J]ava' },
        { '<leader>x', group = 'Diagnostics' },
        { '<leader>l', group = '[L]SP' },
        { '<leader>o', group = '[O]utline' },
        { '<leader>S', group = '[S]essions' },
        { '<leader>T', group = '[T]ests' },
        { '<leader>w', group = '[W]orking set' },
        { '<leader>s', group = '[S]earch' },
        { '<leader>t', group = '[T]oggle' },
        { '<leader>h', group = 'Git [H]unk', mode = { 'n', 'v' } },
      },
    },
  },
  {
    'folke/trouble.nvim',
    cmd = 'Trouble',
    keys = {
      {
        '<leader>xp',
        function()
          require('trouble').toggle 'diagnostics'
        end,
        desc = 'Workspace [P]roblems',
      },
      {
        '<leader>xb',
        function()
          require('trouble').toggle {
            mode = 'diagnostics',
            filter = { buf = 0 },
          }
        end,
        desc = '[B]uffer Diagnostics',
      },
    },
    opts = {
      auto_close = true,
      auto_preview = false,
      focus = true,
    },
  },
  {
    'rcarriga/nvim-notify',
    opts = {
      background_colour = '#1a1b26',
      render = 'wrapped-compact',
      stages = 'fade_in_slide_out',
      timeout = 3000,
      top_down = false,
    },
  },
  {
    'folke/noice.nvim',
    event = 'VimEnter',
    dependencies = {
      'MunifTanjim/nui.nvim',
      'rcarriga/nvim-notify',
    },
    opts = {
      cmdline = {
        enabled = true,
        view = 'cmdline_popup',
      },
      lsp = {
        progress = {
          enabled = false,
        },
        override = {
          ['vim.lsp.util.convert_input_to_markdown_lines'] = true,
          ['vim.lsp.util.stylize_markdown'] = true,
        },
      },
      messages = {
        enabled = true,
        view = 'notify',
        view_error = 'notify',
        view_warn = 'notify',
        view_history = 'messages',
        view_search = false,
      },
      notify = {
        enabled = true,
        view = 'notify',
      },
      popupmenu = {
        enabled = false,
      },
      presets = {
        bottom_search = true,
        command_palette = true,
        inc_rename = true,
        long_message_to_split = true,
      },
    },
  },
  {
    'folke/tokyonight.nvim',
    lazy = false,
    priority = 1000,
    opts = {
      styles = {
        comments = { italic = false },
      },
    },
    config = function(_, opts)
      require('tokyonight').setup(opts)
      vim.cmd.colorscheme 'tokyonight-night'
    end,
  },
  {
    'folke/todo-comments.nvim',
    event = 'VimEnter',
    dependencies = { 'nvim-lua/plenary.nvim' },
    opts = { signs = false },
  },
  {
    'echasnovski/mini.nvim',
    config = function()
      require('mini.ai').setup { n_lines = 500 }
      require('mini.surround').setup()

      local statusline = require 'mini.statusline'
      statusline.setup { use_icons = vim.g.have_nerd_font }
      statusline.section_location = function()
        return '%2l:%-2v'
      end
    end,
  },
  {
    'lukas-reineke/indent-blankline.nvim',
    event = { 'BufReadPost', 'BufNewFile' },
    main = 'ibl',
    init = function()
      local group = vim.api.nvim_create_augroup('config-ibl-highlights', { clear = true })
      vim.api.nvim_create_autocmd('ColorScheme', {
        group = group,
        callback = set_indent_highlights,
      })
      set_indent_highlights()
    end,
    opts = {
      scope = { enabled = true },
      indent = { char = '⁞', highlight = indent_highlights },
    },
  },
}
