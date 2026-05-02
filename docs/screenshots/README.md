# Screenshots

Portfolio screenshots of DataBrief AI using `examples/sample_ecommerce.csv`.

## Recommended captures

| Screen | What to show |
|---|---|
| `upload.png` | Upload dropzone with the ecommerce sample selected |
| `semantic-profile.png` | Dataset overview with detected column roles and confidence score |
| `report-header.png` | Report header with primary KPI cards (estimated spend, units, avg price) |
| `charts.png` | Spend-by-category bar chart and spend-over-time line chart |
| `export-buttons.png` | Export section showing Markdown report, JSON findings, and Python script download buttons |

## Guidelines

- Use `examples/sample_ecommerce.csv` as the demo dataset.
- The report must **not** show "Order count" or "Average order value" — the sample has no order ID column.
- The report **must** show "Purchase line count" and "Total estimated spend."
- Developer debug panels should be collapsed by default.
- No internal server paths or stack traces should be visible.
- No real customer data or personal information.
