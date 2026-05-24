local function with_dapui(callback)
  local ok, dapui = pcall(require, 'dapui')
  if not ok then
    vim.notify('nvim-dap-ui is unavailable: ' .. dapui, vim.log.levels.ERROR)
    return
  end

  callback(dapui)
end

return {
  {
    'rcarriga/nvim-dap-ui',
    lazy = true,
    dependencies = {
      'mfussenegger/nvim-dap',
      'nvim-neotest/nvim-nio',
    },
    opts = {
      icons = { expanded = '▾', collapsed = '▸', current_frame = '*' },
      controls = {
        icons = {
          pause = '⏸',
          play = '▶',
          step_into = '⏎',
          step_over = '⏭',
          step_out = '⏮',
          step_back = 'b',
          run_last = '▶▶',
          terminate = '⏹',
          disconnect = '⏏',
        },
      },
    },
  },
  {
    'mfussenegger/nvim-dap',
    dependencies = {
      'mason-org/mason.nvim',
      'jay-babu/mason-nvim-dap.nvim',
      'leoluz/nvim-dap-go',
      {
        'theHamsta/nvim-dap-virtual-text',
        config = function()
          require('nvim-dap-virtual-text').setup {}
        end,
      },
    },
    keys = {
      {
        '<F5>',
        function()
          require('dap').continue()
        end,
        desc = 'Debug: Start/Continue',
      },
      {
        '<F1>',
        function()
          require('dap').step_into()
        end,
        desc = 'Debug: Step Into',
      },
      {
        '<F2>',
        function()
          require('dap').step_over()
        end,
        desc = 'Debug: Step Over',
      },
      {
        '<F3>',
        function()
          require('dap').step_out()
        end,
        desc = 'Debug: Step Out',
      },
      {
        '<leader>b',
        function()
          require('dap').toggle_breakpoint()
        end,
        desc = 'Debug: Toggle Breakpoint',
      },
      {
        '<leader>B',
        function()
          require('dap').set_breakpoint(vim.fn.input 'Breakpoint condition: ')
        end,
        desc = 'Debug: Set Breakpoint',
      },
      {
        '<leader>dr',
        function()
          require('dap').restart()
        end,
        desc = 'Debug: Restart',
      },
      {
        '<leader>dt',
        function()
          require('dap').terminate()
        end,
        desc = 'Debug: Terminate',
      },
      {
        '<leader>dl',
        function()
          require('dap').run_last()
        end,
        desc = 'Debug: Run Last',
      },
      {
        '<leader>de',
        function()
          with_dapui(function(dapui)
            dapui.eval()
          end)
        end,
        desc = 'Debug: Eval',
        mode = { 'n', 'v' },
      },
      {
        '<leader>dh',
        function()
          require('dap.ui.widgets').hover()
        end,
        desc = 'Debug: Hover',
      },
      {
        '<F7>',
        function()
          with_dapui(function(dapui)
            dapui.toggle()
          end)
        end,
        desc = 'Debug: Toggle debug UI',
      },
    },
    config = function()
      local dap = require 'dap'

      local function executable_path(name)
        local path = vim.fn.exepath(name)
        if path ~= '' then
          return path
        end

        local mason_path = vim.fn.stdpath 'data' .. '/mason/bin/' .. name
        if vim.fn.executable(mason_path) == 1 then
          return mason_path
        end

        return name
      end

      require('mason-nvim-dap').setup {
        automatic_installation = true,
        handlers = {},
        ensure_installed = {
          'js',
          'delve',
        },
      }

      dap.listeners.after.event_initialized.dapui_config = function()
        with_dapui(function(dapui)
          dapui.open()
        end)
      end
      dap.listeners.before.event_terminated.dapui_config = function()
        with_dapui(function(dapui)
          dapui.close()
        end)
      end
      dap.listeners.before.event_exited.dapui_config = function()
        with_dapui(function(dapui)
          dapui.close()
        end)
      end

      require('dap-go').setup {
        delve = {
          detached = vim.fn.has 'win32' == 0,
        },
      }

      dap.adapters['pwa-node'] = {
        type = 'server',
        host = 'localhost',
        port = '${port}',
        executable = {
          command = executable_path 'js-debug-adapter',
          args = { '${port}' },
        },
      }

      for _, language in ipairs { 'typescript', 'javascript' } do
        dap.configurations[language] = {
          {
            type = 'pwa-node',
            request = 'launch',
            name = 'Launch current file',
            program = '${file}',
            cwd = '${workspaceFolder}',
          },
          {
            type = 'pwa-node',
            request = 'attach',
            name = 'Attach to process',
            processId = require('dap.utils').pick_process,
            cwd = '${workspaceFolder}',
          },
        }
      end
    end,
  },
}
