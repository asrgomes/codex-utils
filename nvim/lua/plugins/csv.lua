return {
  {
    'hat0uma/csvview.nvim',
    ft = { 'csv', 'tsv' },
    cmd = { 'CsvViewEnable', 'CsvViewDisable', 'CsvViewToggle', 'CsvViewInfo' },
    opts = {
      view = {
        display_mode = 'border',
      },
    },
    config = function(_, opts)
      local csvview = require 'csvview'
      csvview.setup(opts)

      local csv_filetypes = {
        csv = true,
        tsv = true,
      }

      local function enable_csv_view(bufnr)
        if csvview.is_enabled(bufnr) then
          return
        end

        vim.api.nvim_buf_call(bufnr, function()
          vim.cmd.CsvViewEnable()
        end)
      end

      local group = vim.api.nvim_create_augroup('config-csvview', { clear = true })
      vim.api.nvim_create_autocmd('FileType', {
        group = group,
        pattern = { 'csv', 'tsv' },
        callback = function(event)
          enable_csv_view(event.buf)
        end,
      })

      local current_buf = vim.api.nvim_get_current_buf()
      if csv_filetypes[vim.bo[current_buf].filetype] then
        enable_csv_view(current_buf)
      end
    end,
  },
}
