"use client";

import { FormEvent, useMemo, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Profile = {
  row_count: number;
  column_count: number;
  inferred_types: Record<string, string>;
  missing_percent_by_column: Record<string, number>;
  duplicate_rows: number;
  sample_rows: Record<string, string>[];
  warnings: string[];
};

type DatasetRoute = {
  dataset_type: "sales" | "ecommerce" | "finance" | "generic";
  confidence: number;
  explanation: string;
};

type AnalysisPlan = {
  dataset_type: "sales" | "ecommerce" | "finance" | "generic";
  likely_kpis: string[];
  business_questions: string[];
  recommended_transformations: string[];
  recommended_charts: string[];
  anomaly_checks: string[];
};

type GeneratedCode = {
  code: string;
  allowed_imports: string[];
};

type ExecutionArtifact = {
  name: string;
  size_bytes: number;
  content_type: string;
  url: string;
};

type ExecutionResult = {
  run_id: string;
  status: "success" | "failed" | "timeout";
  exit_code: number | null;
  stdout: string;
  stderr: string;
  timed_out: boolean;
  duration_ms: number;
  artifacts: ExecutionArtifact[];
  error: string | null;
};

type EvaluationResult = {
  outcome: "success" | "recoverable" | "unrecoverable";
  note: string;
};

type RetryAttempt = {
  attempt: number;
  execution: ExecutionResult;
  evaluation: EvaluationResult;
  reason: string;
};

type RetryResult = {
  final_execution: ExecutionResult;
  final_evaluation: EvaluationResult;
  retry_count: number;
  retry_history: RetryAttempt[];
};

type KpiCard = {
  label: string;
  value: string | number;
  source: string;
};

type Finding = {
  description: string;
  source: string;
};

type AnomalyRow = {
  check: string;
  value: string | number;
  flag: "ok" | "warning" | "error";
};

type ReportPayload = {
  executive_summary: string;
  kpi_cards: KpiCard[];
  top_findings: Finding[];
  anomaly_table: AnomalyRow[];
  data_quality_warnings: string[];
  business_recommendations: string[];
  dataset_limitations: string[];
  confidence_note: string;
  is_partial: boolean;
  evaluator_note: string;
  chart_artifacts: string[];
  revised: boolean;
  revision_note: string;
};

type UploadResponse = {
  run_id: string;
  filename: string;
  profile: Profile;
  route: DatasetRoute;
  plan: AnalysisPlan;
  codegen: GeneratedCode;
  execution: ExecutionResult;
  retry: RetryResult;
  report: ReportPayload;
};

type ApiErrorPayload = {
  detail?: string;
  error?: {
    code?: string;
    message?: string;
    status?: number;
  };
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [showDebug, setShowDebug] = useState(false);

  const columns = useMemo(() => {
    if (!result?.profile.sample_rows.length) return [];
    return Object.keys(result.profile.sample_rows[0]);
  }, [result]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setResult(null);

    if (!file) {
      setError("Choose a CSV or XLSX file before running the workflow.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    setIsUploading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/api/upload`, {
        method: "POST",
        body: formData,
      });
      const payload = await readUploadResponse(response);
      if (!response.ok) {
        throw new Error(formatUploadError(response.status, payload as ApiErrorPayload));
      }
      setResult(payload as UploadResponse);
    } catch (uploadError) {
      setError(
        uploadError instanceof Error
          ? uploadError.message
          : "Upload failed. Check that the backend is running."
      );
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <main className="workspace">
      <section className="intro">
        <div>
          <p className="eyebrow">DataBrief AI</p>
          <h1>Dataset analysis workflow</h1>
          <p className="lede">
            Upload a CSV or XLSX to profile the data, route it by domain,
            generate a deterministic analysis plan, execute the
            analysis, and receive a grounded report.
          </p>
        </div>
      </section>

      <section className="panel">
        <form className="uploadForm" onSubmit={handleSubmit}>
          <label htmlFor="dataset">Dataset file</label>
          <div className="uploadRow">
            <input
              id="dataset"
              type="file"
              accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            <button type="submit" disabled={isUploading}>
              {isUploading ? "Analysing…" : "Run analysis"}
            </button>
          </div>
        </form>
        <p className="uploadHint">
          CSV/XLSX only. Demo uploads are capped by the backend configuration.
        </p>
        <div className="sampleButtons">
          <span className="sampleLabel">Demo datasets:</span>
          <a className="sampleLink" href="/examples/sample_ecommerce.csv" download>
            Ecommerce purchases
          </a>
          <a className="sampleLink" href="/examples/sample_performance.csv" download>
            Sales performance
          </a>
          <a className="sampleLink" href="/examples/sample_campaigns.csv" download>
            Marketing campaigns
          </a>
        </div>

        {isUploading ? <WorkflowProgress /> : null}
        {error ? <div className="error">{error}</div> : null}
      </section>

      {result ? (
        <section className="results">
          {/* ----------------------------------------------------------------
              Report and exports
          ---------------------------------------------------------------- */}
          <FinalReport
            report={result.report}
            route={result.route}
            runId={result.run_id}
            apiBase={API_BASE_URL}
          />

          {/* Dataset Overview */}
          <div className="cards">
            <MetricCard label="Rows" value={result.profile.row_count} />
            <MetricCard label="Columns" value={result.profile.column_count} />
            <MetricCard
              label="Duplicate rows"
              value={result.profile.duplicate_rows}
            />
            <MetricCard label="File" value={result.filename} />
          </div>

          <div className="gridTwo">
            <section className="panel">
              <h2>Dataset overview</h2>
              <div className="columnList">
                {Object.entries(result.profile.inferred_types).map(
                  ([column, type]) => (
                    <div className="columnItem" key={column}>
                      <div>
                        <strong>{column}</strong>
                        <span>{type}</span>
                      </div>
                      <span>
                        {result.profile.missing_percent_by_column[column]}%
                        missing
                      </span>
                    </div>
                  )
                )}
              </div>
            </section>

            <section className="panel">
              <h2>Data quality warnings</h2>
              {result.profile.warnings.length ? (
                <ul className="warnings">
                  {result.profile.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              ) : (
                <p className="muted">No data quality warnings detected.</p>
              )}
            </section>
          </div>

          <section className="panel">
            <h2>Analysis plan and KPI targets</h2>
            <div className="planGrid">
              <PlanList title="Likely KPIs" items={result.plan.likely_kpis} />
              <PlanList
                title="Business questions"
                items={result.plan.business_questions}
              />
              <PlanList
                title="Transformations"
                items={result.plan.recommended_transformations}
              />
              <PlanList title="Charts" items={result.plan.recommended_charts} />
              <PlanList
                title="Anomaly checks"
                items={result.plan.anomaly_checks}
              />
            </div>
          </section>

          <section className="panel tablePanel">
            <h2>Dataset preview</h2>
            <p className="muted tableHint">
              Showing the first {result.profile.sample_rows.length} profiled row(s).
            </p>
            <div className="tableWrap">
              <table className="sampleTable">
                <thead>
                  <tr>
                    {columns.map((column) => (
                      <th key={column}>{column}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.profile.sample_rows.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {columns.map((column) => (
                        <td key={column}>{row[column]}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* ----------------------------------------------------------------
              Developer debug (collapsible)
          ---------------------------------------------------------------- */}
          <section className="panel debugPanel">
            <div className="debugHeader">
              <h2>Developer debug</h2>
              <button
                id="toggle-debug"
                className="debugToggle"
                onClick={() => setShowDebug((v) => !v)}
              >
                {showDebug ? "Hide" : "Show"}
              </button>
            </div>

            {showDebug ? (
              <>
                <div className="debugMeta">
                  <span>Route: {result.route.dataset_type}</span>
                  <span>
                    Confidence: {Math.round(result.route.confidence * 100)}%
                  </span>
                  <span>
                    Final status: {result.retry.final_evaluation.outcome}
                  </span>
                  <span>Retries: {result.retry.retry_count}</span>
                  <span>{result.execution.duration_ms}ms</span>
                </div>

                {/* Retry history */}
                <RetryHistory retryResult={result.retry} />

                <div className="executionGrid">
                  <div>
                    <h3>Generated Python</h3>
                    <pre>{result.codegen.code}</pre>
                  </div>
                  <div>
                    <h3>Execution logs</h3>
                    <pre>
                      {JSON.stringify(
                        {
                          status: result.execution.status,
                          exit_code: result.execution.exit_code,
                          timed_out: result.execution.timed_out,
                          error: result.execution.error,
                          stdout: result.execution.stdout,
                          stderr: result.execution.stderr,
                        },
                        null,
                        2
                      )}
                    </pre>
                  </div>
                </div>

                <h3>Artifacts</h3>
                {result.execution.artifacts.length ? (
                  <div className="artifactGrid">
                    {result.execution.artifacts.map((artifact) => (
                      <div className="artifactItem" key={artifact.name}>
                        <div>
                          <strong>{artifact.name}</strong>
                          <span>{Math.ceil(artifact.size_bytes / 1024)} KB</span>
                        </div>
                        {artifact.content_type === "image/svg+xml" ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            alt={artifact.name}
                            src={`${API_BASE_URL}${artifact.url}`}
                          />
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="muted">No artifacts were saved.</p>
                )}
              </>
            ) : null}
          </section>
        </section>
      ) : null}
    </main>
  );
}

async function readUploadResponse(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json();
  }

  const text = await response.text();
  if (!response.ok) {
    return {
      detail: text.trim() || response.statusText || "Upload failed.",
      error: { code: "non_json_response", status: response.status },
    };
  }
  throw new Error("Backend returned an unexpected non-JSON response.");
}

function formatUploadError(status: number, payload: ApiErrorPayload): string {
  const code = payload.error?.code;
  const message = payload.error?.message ?? payload.detail;
  if (code === "file_too_large" || status === 413) {
    return message ?? "File is too large for this demo workflow.";
  }
  if (code === "execution_timeout") {
    return "Analysis timed out. Try a smaller file or fewer rows.";
  }
  if (code === "unsupported_file" || status === 400) {
    return message ?? "Upload a supported CSV or XLSX file.";
  }
  if (code === "non_json_response") {
    return "The backend or hosting layer rejected the request before DataBrief could process it. Check the upload size and try again.";
  }
  return message ?? "The backend failed while running the workflow.";
}

// ---------------------------------------------------------------------------
// Phase 5 — Report components
// ---------------------------------------------------------------------------

function outcomeClass(outcome: string) {
  if (outcome === "success") return "outcomeSuccess";
  if (outcome === "unrecoverable") return "outcomeError";
  return "outcomeWarn";
}

function flagClass(flag: string) {
  if (flag === "ok") return "flagOk";
  if (flag === "error") return "flagError";
  return "flagWarn";
}

function formatKpiValue(value: string | number) {
  return typeof value === "number" ? value.toLocaleString() : value;
}

function humanizeLabel(label: string) {
  return label.replace(/_/g, " ");
}

function humanizeSource(source: string) {
  return source.replace(/:/g, " / ");
}

function splitKpiCards(cards: KpiCard[]) {
  return cards.reduce(
    (groups, card) => {
      const label = card.label.toLowerCase();
      if (label === "rows" || label === "columns") {
        groups.structural.push(card);
      } else if (
        label.includes("duplicate") ||
        label.includes("missing") ||
        label.includes("warning") ||
        label.includes("error") ||
        label.includes("return/cancel")
      ) {
        groups.warning.push(card);
      } else {
        groups.primary.push(card);
      }
      return groups;
    },
    {
      primary: [] as KpiCard[],
      structural: [] as KpiCard[],
      warning: [] as KpiCard[],
    }
  );
}

function confidenceLabel(confidence: number): string {
  if (confidence >= 0.8) return "Data confidence: High";
  if (confidence >= 0.6) return "Data confidence: Medium";
  return "Data confidence: Low";
}

function FinalReport({
  report,
  route,
  runId,
  apiBase,
}: {
  report: ReportPayload;
  route: DatasetRoute;
  runId: string;
  apiBase: string;
}) {
  const kpis = splitKpiCards(report.kpi_cards);

  return (
    <section className="panel reportPanel">
      <div className="reportHeader">
        <div>
          <p className="eyebrow">Analysis report</p>
          <h2>{humanizeLabel(route.dataset_type)} dataset</h2>
        </div>
        <div className="reportHeaderBadges">
          <span className="confidence">
            {confidenceLabel(route.confidence)}
          </span>
          <span
            className={`outcomeBadge ${outcomeClass(
              report.is_partial ? "recoverable" : "success"
            )}`}
          >
            {report.is_partial ? "Partial results" : "Complete"}
          </span>
        </div>
      </div>

      <div className="reportStatusGrid">
        <div>
          <span>Dataset type</span>
          <strong>{humanizeLabel(route.dataset_type)}</strong>
          <p>{route.explanation}</p>
        </div>
        <div>
          <span>Execution status</span>
          <strong>{report.is_partial ? "Partial report" : "Complete report"}</strong>
          {report.evaluator_note ? <p>{report.evaluator_note}</p> : null}
        </div>
        <div>
          <span>Grounding</span>
          <strong>{report.revised ? "Revised after check" : "Supported claims"}</strong>
          <p>
            KPIs and findings are displayed with computed sources from the run
            profile or summary artifact.
          </p>
        </div>
      </div>

      {/* Groundedness revision notice */}
      {report.revised ? (
        <div className="revisionNotice">
          Report was revised: {report.revision_note}
        </div>
      ) : null}

      {/* Confidence note */}
      {report.confidence_note ? (
        <p className="confidenceNote topConfidenceNote">
          {report.confidence_note}
        </p>
      ) : null}

      {/* Executive summary */}
      {report.executive_summary ? (
        <div className="reportSection">
          <h3>Executive summary</h3>
          <p className="execSummary">{report.executive_summary}</p>
        </div>
      ) : null}

      {/* Primary Metrics (KPI cards) */}
      {report.kpi_cards.length > 0 ? (
        <div className="reportSection">
          <h3>Primary metrics</h3>
          {kpis.primary.length > 0 ? (
            <KpiGroup cards={kpis.primary} variant="primary" />
          ) : null}
          {kpis.warning.length > 0 ? (
            <>
              <h4 className="kpiGroupTitle">Data quality indicators</h4>
              <KpiGroup cards={kpis.warning} variant="warning" />
            </>
          ) : null}
          {kpis.structural.length > 0 ? (
            <>
              <h4 className="kpiGroupTitle">Dataset structure</h4>
              <KpiGroup cards={kpis.structural} variant="structural" />
            </>
          ) : null}
        </div>
      ) : null}

      {/* Top findings */}
      {report.top_findings.length > 0 ? (
        <div className="reportSection">
          <h3>Top findings</h3>
          <ol className="rankedList">
            {report.top_findings.map((f, i) => (
              <li key={i}>
                <span>{i + 1}</span>
                <div>
                  <p>{f.description}</p>
                  <small>Source: {humanizeSource(f.source)}</small>
                </div>
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      {/* Data quality warnings and anomaly checks */}
      {report.anomaly_table.length > 0 ||
      report.data_quality_warnings.length > 0 ? (
        <QualitySection report={report} />
      ) : null}

      {/* Business recommendations */}
      {report.business_recommendations.length > 0 ? (
        <div className="reportSection">
          <h3>Recommendations</h3>
          <ul className="recommendationList">
            {report.business_recommendations.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Charts */}
      {report.chart_artifacts.length > 0 ? (
        <div className="reportSection">
          <h3>Charts</h3>
          <div className="chartGrid">
            {report.chart_artifacts.map((url) => {
              const name = url.split("/").pop() ?? url;
              return (
                <ChartPreview key={url} name={name} src={`${apiBase}${url}`} />
              );
            })}
          </div>
        </div>
      ) : null}

      {/* Limitations */}
      {report.dataset_limitations.length > 0 ? (
        <div className="reportSection">
          <h3>Limitations</h3>
          <ul className="limitationList">
            {report.dataset_limitations.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Exports */}
      <div className="reportSection">
        <h3>Exports</h3>
        <div className="exportGrid">
          <ExportLink
            href={`${apiBase}/api/runs/${runId}/export/report.md`}
            filename="report.md"
            title="Report"
            detail="Markdown summary"
          />
          <ExportLink
            href={`${apiBase}/api/runs/${runId}/export/findings.json`}
            filename="findings.json"
            title="Findings"
            detail="Grounded JSON payload"
          />
          <ExportLink
            href={`${apiBase}/api/runs/${runId}/export/analysis.py`}
            filename="analysis.py"
            title="Analysis script"
            detail="Generated Python"
          />
        </div>
      </div>
    </section>
  );
}

function KpiGroup({
  cards,
  variant,
}: {
  cards: KpiCard[];
  variant: "primary" | "structural" | "warning";
}) {
  return (
    <div className={`kpiGrid kpiGrid-${variant}`}>
      {cards.map((card) => (
        <div className={`kpiCard kpiCard-${variant}`} key={card.label}>
          <span className="kpiLabel">{humanizeLabel(card.label)}</span>
          <strong className="kpiValue">{formatKpiValue(card.value)}</strong>
          <small>Source: {humanizeSource(card.source)}</small>
        </div>
      ))}
    </div>
  );
}

function WorkflowProgress() {
  const steps = [
    "Validate",
    "Profile",
    "Route",
    "Plan",
    "Execute",
    "Grounded report",
  ];

  return (
    <div className="workflowProgress" aria-live="polite">
      <div className="progressHeader">
        <strong>Workflow running</strong>
        <span>Controlled analysis in progress</span>
      </div>
      <div className="progressSteps">
        {steps.map((step) => (
          <span key={step}>{step}</span>
        ))}
      </div>
    </div>
  );
}

function ExportLink({
  href,
  filename,
  title,
  detail,
}: {
  href: string;
  filename: string;
  title: string;
  detail: string;
}) {
  return (
    <a className="exportLink" href={href} download={filename}>
      <strong>{title}</strong>
      <span>{detail}</span>
    </a>
  );
}

function QualitySection({ report }: { report: ReportPayload }) {
  return (
    <div className="reportSection qualitySection">
      <h3>Data quality checks</h3>
      {report.data_quality_warnings.length > 0 ? (
        <ul className="qualityWarnings">
          {report.data_quality_warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">No data quality warnings detected.</p>
      )}

      {report.anomaly_table.length > 0 ? (
        <div className="tableWrap qualityTableWrap">
          <table>
            <thead>
              <tr>
                <th>Check</th>
                <th>Value</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {report.anomaly_table.map((row, i) => (
                <tr key={i}>
                  <td>{row.check}</td>
                  <td>{String(row.value)}</td>
                  <td>
                    <span className={`flagBadge ${flagClass(row.flag)}`}>
                      {row.flag}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

function ChartPreview({ name, src }: { name: string; src: string }) {
  const [hasError, setHasError] = useState(false);

  return (
    <div className="chartItem">
      <div className="chartTitle">{humanizeLabel(name.replace(/\.svg$/i, ""))}</div>
      {hasError ? (
        <div className="chartFallback">
          Chart preview unavailable. Export artifacts are still available in
          developer debug.
        </div>
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img alt={name} src={src} onError={() => setHasError(true)} />
      )}
    </div>
  );
}

function RetryHistory({ retryResult }: { retryResult: RetryResult }) {
  if (retryResult.retry_history.length <= 1 && retryResult.retry_count === 0) {
    return (
      <p className="muted" style={{ marginBottom: "12px" }}>
        Succeeded on first attempt — no retries needed.
      </p>
    );
  }

  return (
    <div className="retryHistory">
      <h3>Retry history ({retryResult.retry_count} retry/retries)</h3>
      <div className="retryList">
        {retryResult.retry_history.map((attempt) => (
          <div className="retryAttempt" key={attempt.attempt}>
            <div className="retryMeta">
              <span className="retryNum">Attempt {attempt.attempt}</span>
              <span
                className={`outcomeBadge ${outcomeClass(attempt.evaluation.outcome)}`}
              >
                {attempt.evaluation.outcome}
              </span>
              <span className="retryReason">{attempt.reason}</span>
            </div>
            <p className="retryNote">{attempt.evaluation.note}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared components (unchanged from Phase 4)
// ---------------------------------------------------------------------------

function PlanList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="planList">
      <h3>{title}</h3>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function MetricCard({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="metricCard">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
