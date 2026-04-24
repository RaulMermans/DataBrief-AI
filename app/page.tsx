"use client";

import { FormEvent, useMemo, useState } from "react";

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
  dataset_type: "sales" | "generic";
  confidence: number;
  explanation: string;
};

type UploadResponse = {
  filename: string;
  profile: Profile;
  route: DatasetRoute;
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  const columns = useMemo(() => {
    if (!result?.profile.sample_rows.length) {
      return [];
    }
    return Object.keys(result.profile.sample_rows[0]);
  }, [result]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setResult(null);

    if (!file) {
      setError("Choose a CSV file before running the workflow.");
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
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail ?? "Upload failed.");
      }
      setResult(payload);
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
          <h1>CSV profile and routing workflow</h1>
          <p className="lede">
            Upload a CSV to validate the first deterministic slice: profile,
            route as sales or generic, and render a report shell.
          </p>
        </div>
      </section>

      <section className="panel">
        <form className="uploadForm" onSubmit={handleSubmit}>
          <label htmlFor="dataset">Dataset CSV</label>
          <div className="uploadRow">
            <input
              id="dataset"
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            <button type="submit" disabled={isUploading}>
              {isUploading ? "Profiling..." : "Run profile"}
            </button>
          </div>
        </form>

        {error ? <div className="error">{error}</div> : null}
      </section>

      {result ? (
        <section className="results">
          <div className="routeBanner">
            <div>
              <p className="eyebrow">Detected dataset type</p>
              <h2>{result.route.dataset_type}</h2>
            </div>
            <div className="confidence">
              {Math.round(result.route.confidence * 100)}%
            </div>
            <p>{result.route.explanation}</p>
          </div>

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
              <h2>Column profile</h2>
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
              <h2>Warnings</h2>
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

          <section className="panel tablePanel">
            <h2>Sample rows</h2>
            <div className="tableWrap">
              <table>
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
        </section>
      ) : null}
    </main>
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
