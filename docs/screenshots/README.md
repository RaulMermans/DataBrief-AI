# Screenshots

Portfolio screenshots of DataBrief AI using `examples/sample_ecommerce.csv`.

## Recommended files

| Filename | What to capture |
|---|---|
| `01-upload.png` | Upload dropzone with the ecommerce sample selected |
| `02-dataset-profile.png` | Dataset overview with detected column roles and confidence score |
| `03-analysis-plan.png` | Analysis plan: KPI targets, business questions, recommended charts |
| `04-report-metrics.png` | Report header with primary KPI cards (purchase line count, estimated spend, avg price) |
| `05-charts-and-recommendations.png` | Spend-by-category bar chart, spend-over-time line chart, and recommendations |
| `06-exports.png` | Export section showing Markdown report, JSON findings, and Python script download buttons |

## Guidelines

- Use `examples/sample_ecommerce.csv` as the demo dataset.
- Screenshots must **not** show:
  - "Order count" or "Average order value" — the sample has no order ID column
  - Return or cancel rate as 0% when the metric is unsupported
  - Date columns summarized as numeric totals
  - Expanded developer debug panels
  - Internal server paths or stack traces
  - Real customer data or personal information
- Screenshots **must** show:
  - "Purchase line count" and "Total estimated spend" as primary KPIs
  - Developer debug panels collapsed by default
