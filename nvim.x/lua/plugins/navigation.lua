return {
  {
    'nvim-telescope/telescope.nvim',
    event = 'VimEnter',
    dependencies = {
      'nvim-lua/plenary.nvim',
      {
        'nvim-telescope/telescope-fzf-native.nvim',
        build = 'make',
        cond = function()
          return vim.fn.executable 'make' == 1
        end,
      },
      'nvim-telescope/telescope-ui-select.nvim',
      { 'nvim-tree/nvim-web-devicons', enabled = vim.g.have_nerd_font },
    },
    config = function()
      local actions = require 'telescope.actions'
      local builtin = require 'telescope.builtin'

      local function project_find_command()
        if vim.fn.executable 'rg' == 1 then
          return {
            'rg',
            '--files',
            '--hidden',
            '--glob',
            '!.git',
            '--glob',
            '!.git/*',
          }
        end

        return nil
      end

      local function find_project_files(opts)
        opts = opts or {}
        opts.hidden = true
        opts.find_command = project_find_command()
        builtin.find_files(opts)
      end

      local function live_grep_project(opts)
        opts = opts or {}
        local caller_additional_args = opts.additional_args
        opts.additional_args = function(_, grep_opts)
          local args = { '--hidden', '--glob', '!.git', '--glob', '!.git/*' }
          if caller_additional_args then
            vim.list_extend(args, caller_additional_args(_, grep_opts))
          end
          return args
        end

        builtin.live_grep(opts)
      end

      require('telescope').setup {
        defaults = {
          layout_strategy = 'horizontal',
          sorting_strategy = 'ascending',
          layout_config = {
            prompt_position = 'top',
            height = 0.85,
            width = 0.95,
            preview_width = 0.55,
          },
          path_display = function(_, path)
            local tail = vim.fs.basename(path)
            local parent = vim.fs.dirname(path)

            if parent == '.' then
              return tail
            end

            return string.format('%s  (%s)', tail, parent)
          end,
          mappings = {
            i = {
              ['<C-j>'] = actions.move_selection_next,
              ['<C-k>'] = actions.move_selection_previous,
              ['<C-n>'] = actions.cycle_history_next,
              ['<C-p>'] = actions.cycle_history_prev,
            },
            n = {
              ['j'] = actions.move_selection_next,
              ['k'] = actions.move_selection_previous,
            },
          },
        },
        pickers = {
          buffers = {
            sort_mru = true,
            ignore_current_buffer = true,
            previewer = false,
          },
          find_files = {
            hidden = true,
            find_command = project_find_command(),
          },
          oldfiles = {
            only_cwd = true,
          },
        },
        extensions = {
          ['ui-select'] = {
            require('telescope.themes').get_dropdown(),
          },
        },
      }

      pcall(require('telescope').load_extension, 'fzf')
      pcall(require('telescope').load_extension, 'ui-select')

      vim.keymap.set('n', '<leader>sh', builtin.help_tags, { desc = '[S]earch [H]elp' })
      vim.keymap.set('n', '<leader>sk', builtin.keymaps, { desc = '[S]earch [K]eymaps' })
      vim.keymap.set('n', '<leader>sf', find_project_files, { desc = '[S]earch [F]iles' })
      vim.keymap.set('n', '<leader>ss', builtin.builtin, { desc = '[S]earch [S]elect Telescope' })
      vim.keymap.set('n', '<leader>sw', builtin.grep_string, { desc = '[S]earch current [W]ord' })
      vim.keymap.set('n', '<leader>sg', live_grep_project, { desc = '[S]earch by [G]rep' })
      vim.keymap.set('n', '<leader>sd', builtin.diagnostics, { desc = '[S]earch [D]iagnostics' })
      vim.keymap.set('n', '<leader>sr', builtin.resume, { desc = '[S]earch [R]esume' })
      vim.keymap.set('n', '<leader>s.', builtin.oldfiles, { desc = '[S]earch Recent Files ("." for repeat)' })
      vim.keymap.set('n', '<leader><leader>', builtin.buffers, { desc = '[ ] Find existing buffers' })
      vim.keymap.set('n', '<leader>Ff', find_project_files, { desc = '[F]ind [F]iles' })
      vim.keymap.set('n', '<leader>Fr', builtin.oldfiles, { desc = '[F]ile [R]ecents' })
      vim.keymap.set('n', '<leader>Fg', live_grep_project, { desc = '[F]ind by [G]rep' })
      vim.keymap.set('n', '<leader>Fn', function()
        find_project_files { cwd = vim.fn.stdpath 'config' }
      end, { desc = '[F]ind [N]eovim files' })
      vim.keymap.set('n', '<leader><tab><tab>', builtin.buffers, { desc = '[B]rowse [B]uffers' })
      vim.keymap.set('n', '<leader><tab>d', function()
        builtin.diagnostics { bufnr = 0 }
      end, { desc = '[B]uffer [D]iagnostics' })
      vim.keymap.set('n', '<leader>gs', builtin.git_status, { desc = '[G]it [S]tatus' })
      vim.keymap.set('n', '<leader>gf', builtin.git_files, { desc = '[G]it [F]iles' })
      vim.keymap.set('n', '<leader>gb', builtin.git_branches, { desc = '[G]it [B]ranches' })
      vim.keymap.set('n', '<leader>gc', builtin.git_commits, { desc = '[G]it [C]ommits' })
      vim.keymap.set('n', '<leader>xx', builtin.diagnostics, { desc = 'Diagnostics' })
      vim.keymap.set('n', '<leader>xs', builtin.lsp_document_symbols, { desc = 'Document [S]ymbols' })
      vim.keymap.set('n', '<leader>lS', builtin.lsp_dynamic_workspace_symbols, { desc = '[L]SP Workspace [S]ymbols' })
      vim.keymap.set('n', '<leader>lr', builtin.lsp_references, { desc = '[L]SP [R]eferences' })
      vim.keymap.set('n', '<leader>ld', builtin.lsp_definitions, { desc = '[L]SP [D]efinitions' })
      vim.keymap.set('n', '<leader>li', builtin.lsp_implementations, { desc = '[L]SP [I]mplementations' })
      vim.keymap.set('n', '<leader>lt', builtin.lsp_type_definitions, { desc = '[L]SP [T]ype definitions' })
      vim.keymap.set('n', '<leader>/', function()
        builtin.current_buffer_fuzzy_find(require('telescope.themes').get_dropdown {
          winblend = 10,
          previewer = false,
        })
      end, { desc = '[/] Fuzzily search in current buffer' })
      vim.keymap.set('n', '<leader>s/', function()
        live_grep_project {
          grep_open_files = true,
          prompt_title = 'Live Grep in Open Files',
        }
      end, { desc = '[S]earch [/] in Open Files' })
      vim.keymap.set('n', '<leader>sn', function()
        find_project_files { cwd = vim.fn.stdpath 'config' }
      end, { desc = '[S]earch [N]eovim files' })
    end,
  },
  {
    'stevearc/aerial.nvim',
    dependencies = {
      'nvim-telescope/telescope.nvim',
    },
    keys = {
      { '<leader>oo', '<cmd>AerialToggle!<cr>', desc = '[O]utline t[o]ggle' },
      { '<leader>os', '<cmd>Telescope aerial<cr>', desc = '[O]utline [S]ymbols' },
      { '<leader>on', '<cmd>AerialNavToggle<cr>', desc = '[O]utline [N]av' },
      { '<leader>ls', '<cmd>Telescope aerial<cr>', desc = '[L]SP Document [S]ymbols' },
    },
    opts = {
      backends = { 'treesitter', 'lsp', 'markdown', 'man' },
      layout = {
        min_width = 28,
        default_direction = 'prefer_right',
        resize_to_content = false,
      },
      show_guides = true,
      filter_kind = false,
      close_automatic_events = { 'unfocus', 'switch_buffer' },
      attach_mode = 'window',
      guides = {
        mid_item = '├─',
        last_item = '└─',
        nested_top = '│ ',
        whitespace = '  ',
      },
    },
    config = function(_, opts)
      require('aerial').setup(opts)
      require('telescope').load_extension 'aerial'
    end,
  },
  {
    'nvim-neo-tree/neo-tree.nvim',
    cmd = 'Neotree',
    keys = {
      { '<leader>e', '<cmd>Neotree toggle filesystem reveal left<cr>', desc = 'Explorer toggle', silent = true },
      { '\\', '<cmd>Neotree reveal<cr>', desc = 'NeoTree reveal', silent = true },
    },
    dependencies = {
      'nvim-lua/plenary.nvim',
      'nvim-tree/nvim-web-devicons',
      'MunifTanjim/nui.nvim',
    },
    opts = {
      close_if_last_window = true,
      enable_git_status = true,
      enable_diagnostics = true,
      filesystem = {
        follow_current_file = {
          enabled = true,
          leave_dirs_open = true,
        },
        filtered_items = {
          hide_dotfiles = false,
          hide_gitignored = false,
        },
        window = {
          mappings = {
            ['\\'] = 'close_window',
          },
        },
      },
    },
  },
  {
    'ThePrimeagen/harpoon',
    branch = 'harpoon2',
    dependencies = { 'nvim-lua/plenary.nvim' },
    keys = {
      {
        '<leader>wa',
        function()
          require('harpoon'):list():add()
        end,
        desc = '[W]orking set [A]dd file',
      },
      {
        '<leader>we',
        function()
          local harpoon = require 'harpoon'
          harpoon.ui:toggle_quick_menu(harpoon:list())
        end,
        desc = '[W]orking set [E]dit',
      },
      {
        '<leader>wn',
        function()
          require('harpoon'):list():next()
        end,
        desc = '[W]orking set [N]ext',
      },
      {
        '<leader>wp',
        function()
          require('harpoon'):list():prev()
        end,
        desc = '[W]orking set [P]revious',
      },
    },
    config = function()
      require('harpoon'):setup()
    end,
  },
  {
    'folke/persistence.nvim',
    event = 'BufReadPre',
    opts = {
      branch = true,
      need = 1,
    },
    keys = {
      {
        '<leader>Ss',
        function()
          require('persistence').load()
        end,
        desc = '[S]ession re[s]tore',
      },
      {
        '<leader>Sl',
        function()
          require('persistence').load { last = true }
        end,
        desc = '[S]ession [L]ast',
      },
      {
        '<leader>Sd',
        function()
          require('persistence').stop()
        end,
        desc = '[S]ession [D]isable',
      },
    },
  },
}
