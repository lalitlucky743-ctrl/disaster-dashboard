import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  History,
  Play,
  RefreshCw,
  Server,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import { dashboardApi } from "../api/dashboardApi";

function formatDate(value) {
  if (!value) return "—";

  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? String(value)
    : date.toLocaleString();
}

function errorText(error) {
  return error?.message || String(error || "Unknown error");
}

function statusClass(status) {
  const value = String(status || "").toLowerCase();

  if (["ok", "complete", "verified", "running"].includes(value)) {
    return "border-emerald-500/30 bg-emerald-500/10 text-emerald-300";
  }

  if (["partial", "source_error", "error", "stopped"].includes(value)) {
    return "border-amber-500/30 bg-amber-500/10 text-amber-300";
  }

  if (["already_running"].includes(value)) {
    return "border-sky-500/30 bg-sky-500/10 text-sky-300";
  }

  return "border-slate-700 bg-slate-800/70 text-slate-300";
}

function riskClass(level) {
  const value = String(level || "").toUpperCase();

  if (value === "CRITICAL" || value === "HIGH") {
    return "text-rose-300";
  }
  if (value === "MEDIUM") {
    return "text-amber-300";
  }
  if (value === "LOW") {
    return "text-emerald-300";
  }

  return "text-slate-400";
}

function ModelCell({ model }) {
  if (model?.status !== "ok" || !model?.result) {
    return (
      <div>
        <div className="text-xs font-semibold text-rose-300">
          Prediction unavailable
        </div>
        <div className="mt-1 max-w-48 text-[10px] text-slate-500 break-words">
          {model?.error || "No successful result"}
        </div>
      </div>
    );
  }

  const level = model.result.risk_level || "Unknown";
  const score = Number(model.result.risk_score);

  return (
    <div>
      <div className={`text-xs font-bold ${riskClass(level)}`}>
        {String(level).toUpperCase()}
      </div>
      <div className="mt-1 text-[11px] text-slate-300">
        Score: {Number.isFinite(score) ? score.toFixed(1) : "—"} / 100
      </div>
      <div className="mt-1 max-w-44 break-words text-[9px] text-slate-500">
        {model.result.model_version || "Model version unavailable"}
      </div>
    </div>
  );
}

function Metric({ icon: Icon, label, value, detail }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-500">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div className="mt-2 text-sm font-semibold text-slate-100">{value}</div>
      <div className="mt-1 break-words text-[10px] text-slate-500">{detail}</div>
    </div>
  );
}

export default function AutomaticModelMonitoring() {
  const [status, setStatus] = useState(null);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [runLoading, setRunLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [actionMessage, setActionMessage] = useState("");

  const requestInFlight = useRef(false);
  const runInFlight = useRef(false);

  const loadMonitoringData = useCallback(async ({ silent = false } = {}) => {
    if (requestInFlight.current || runInFlight.current) return;

    requestInFlight.current = true;

    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      const [statusResult, historyResult] = await Promise.allSettled([
        dashboardApi.getAutomaticMonitoringStatus(),
        dashboardApi.getAutomaticMonitoringHistory(10),
      ]);

      const errors = [];

      if (statusResult.status === "fulfilled") {
        setStatus(statusResult.value);
      } else {
        errors.push(`Status: ${errorText(statusResult.reason)}`);
      }

      if (historyResult.status === "fulfilled") {
        const history = historyResult.value?.runs;
        setRuns(Array.isArray(history) ? history : []);
      } else {
        errors.push(`History: ${errorText(historyResult.reason)}`);
      }

      setLoadError(errors.join(" | "));
    } finally {
      requestInFlight.current = false;
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadMonitoringData();

    const timer = window.setInterval(() => {
      void loadMonitoringData({ silent: true });
    }, 30000);

    return () => window.clearInterval(timer);
  }, [loadMonitoringData]);

  const runOnce = async () => {
    if (runInFlight.current) return;

    runInFlight.current = true;
    setRunLoading(true);
    setActionMessage("");

    try {
      const result = await dashboardApi.runAutomaticMonitoringOnce();

      if (result?.status === "already_running") {
        setActionMessage(
          result.message || "A monitoring cycle is already in progress."
        );
      } else {
        const entry = {
          run_id: result?.run_id,
          started_at: result?.started_at,
          finished_at: result?.finished_at,
          status: result?.status || "unknown",
          error: null,
          results: result,
        };

        setRuns((previous) =>
          [
            entry,
            ...previous.filter((item) => item.run_id !== entry.run_id),
          ].slice(0, 10)
        );

        setActionMessage(
          `Monitoring run ${result?.run_id ?? ""} finished with status: ${
            result?.status || "unknown"
          }.`
        );
      }
    } catch (error) {
      setActionMessage(`Run Now failed: ${errorText(error)}`);
    } finally {
      runInFlight.current = false;
      setRunLoading(false);
      await loadMonitoringData({ silent: true });
    }
  };

  const lastRun = status?.last_run || runs[0] || null;
  const latestPayload = lastRun?.results || null;
  const districtRows = Array.isArray(latestPayload?.results)
    ? latestPayload.results
    : [];
      // Build the model comparison chart only from successful predictions.
  const readChartScore = (model) => {
    if (model?.status !== "ok") return null;

    const score = Number(model?.result?.risk_score);

    return Number.isFinite(score) && score >= 0 && score <= 100
      ? score
      : null;
  };

  const chartRows = districtRows.map((row, index) => ({
    district: row.district,
    index,
    production: readChartScore(row.production),
    candidate: readChartScore(row.candidate_v5),
  }));

  const chartWidth = 960;
  const chartHeight = 350;
  const chartLeft = 62;
  const chartRight = 930;
  const chartTop = 24;
  const chartBottom = 228;

  const chartX = (index) =>
    chartRows.length <= 1
      ? (chartLeft + chartRight) / 2
      : chartLeft +
        (index / (chartRows.length - 1)) * (chartRight - chartLeft);

  const chartY = (score) =>
    chartBottom - (score / 100) * (chartBottom - chartTop);

  // Break the line whenever a district has no valid model result.
  // This avoids connecting across unavailable predictions.
  const buildChartPaths = (key) => {
    const paths = [];
    let currentSegment = [];

    chartRows.forEach((point) => {
      const score = point[key];

      if (score === null) {
        if (currentSegment.length) {
          paths.push(currentSegment.join(" "));
          currentSegment = [];
        }
        return;
      }

      const command = `${
        currentSegment.length ? "L" : "M"
      } ${chartX(point.index).toFixed(1)} ${chartY(score).toFixed(1)}`;

      currentSegment.push(command);
    });

    if (currentSegment.length) {
      paths.push(currentSegment.join(" "));
    }

    return paths;
  };

  const productionChartPaths = buildChartPaths("production");
  const candidateChartPaths = buildChartPaths("candidate");

  const chartHasData = chartRows.some(
    (point) => point.production !== null || point.candidate !== null
  );

  const chartBothModelCount = chartRows.filter(
    (point) => point.production !== null && point.candidate !== null
  ).length;

  const chartTicks = [0, 25, 50, 75, 100];

  const modelSuccessCount = districtRows.filter(
    (row) =>
      row.production?.status === "ok" &&
      row.candidate_v5?.status === "ok"
  ).length;

  const sourceStatuses =
    districtRows[0]?.official_verification?.sources || {};

  const sourceErrors = Array.isArray(latestPayload?.source_errors)
    ? latestPayload.source_errors
    : [];

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4 shadow-xl">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-sky-400" />
            <h2 className="text-sm font-semibold text-slate-100">
              Automatic Model Monitoring
            </h2>
          </div>
          <p className="mt-1 text-[11px] text-slate-500">
            Production landslide model vs Candidate V5 · Read-only comparison
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void loadMonitoringData()}
            disabled={loading || refreshing || runLoading}
            className="flex items-center gap-2 rounded-xl border border-slate-700 px-3 py-2 text-[10px] text-slate-300 transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${
                refreshing ? "animate-spin" : ""
              }`}
            />
            Refresh
          </button>

          <button
            type="button"
            onClick={() => void runOnce()}
            disabled={runLoading}
            className="flex items-center gap-2 rounded-xl border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-[10px] font-semibold text-sky-300 transition hover:bg-sky-500/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {runLoading ? (
              <RefreshCw className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            {runLoading ? "Running cycle..." : "Run Now"}
          </button>
        </div>
      </div>

      {loadError && (
        <div className="mt-4 flex gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-[11px] text-rose-200">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <div className="break-words">
            <div className="font-semibold">Monitoring data could not fully load</div>
            <div className="mt-1">{loadError}</div>
          </div>
        </div>
      )}

      {actionMessage && (
        <div className="mt-4 flex gap-2 rounded-xl border border-sky-500/20 bg-sky-500/5 p-3 text-[11px] text-sky-200">
          <Activity className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="break-words">{actionMessage}</span>
        </div>
      )}

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          icon={Server}
          label="Scheduler"
          value={
            status?.scheduler_running === true
              ? "Running"
              : status?.scheduler_running === false
                ? "Stopped"
                : loading
                  ? "Loading..."
                  : "Unknown"
          }
          detail={`Configured interval: ${Math.round(
            Number(status?.interval_seconds || 300) / 60
          )} minutes`}
        />

        <Metric
          icon={Clock3}
          label="Last completed run"
          value={formatDate(lastRun?.finished_at || lastRun?.started_at)}
          detail={
            lastRun?.run_id != null
              ? `Run #${lastRun.run_id} · ${lastRun.status || "unknown"}`
              : "No saved monitoring run"
          }
        />

        <Metric
          icon={CheckCircle2}
          label="Both models succeeded"
          value={`${modelSuccessCount}/13`}
          detail={
            districtRows.length
              ? `${districtRows.length} districts in latest run`
              : "Waiting for the first stored run"
          }
        />

        <Metric
          icon={ShieldAlert}
          label="Official verification"
          value={
            sourceStatuses.IMD === "ok" && sourceStatuses.SACHET === "ok"
              ? "Sources accessible"
              : "Source issue"
          }
          detail={`IMD: ${sourceStatuses.IMD || "unknown"} · SACHET: ${
            sourceStatuses.SACHET || "unknown"
          }`}
        />
      </div>

      <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/30 p-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-200">
          {sourceErrors.length ? (
            <AlertTriangle className="h-4 w-4 text-amber-300" />
          ) : (
            <CheckCircle2 className="h-4 w-4 text-emerald-300" />
          )}
          Official source status
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {Object.entries(sourceStatuses).length ? (
            Object.entries(sourceStatuses).map(([name, sourceStatus]) => (
              <span
                key={name}
                className={`rounded-lg border px-2 py-1 text-[10px] ${statusClass(
                  sourceStatus
                )}`}
              >
                {name}: {sourceStatus}
              </span>
            ))
          ) : (
            <span className="text-[10px] text-slate-500">
              No source status recorded in the latest run.
            </span>
          )}
        </div>

        {sourceErrors.length > 0 && (
          <div className="mt-3 space-y-2">
            {sourceErrors.map((item, index) => (
              <div
                key={`${item.source || "source"}-${index}`}
                className="break-words text-[10px] text-amber-200/90"
              >
                <span className="font-semibold">{item.source || "Source"}:</span>{" "}
                {item.error || "Source returned an error"}
              </div>
            ))}
          </div>
        )}

        <p className="mt-3 text-[10px] leading-relaxed text-slate-500">
          An unavailable official source means verification is inconclusive.
          It does not mean that no official alert exists. Model agreement also
          does not by itself establish which model is more accurate.
        </p>
      </div>

      <div className="mt-5">
        <div className="mb-3 flex items-center gap-2">
          <Activity className="h-4 w-4 text-sky-400" />
          <h3 className="text-xs font-semibold text-slate-200">
            District model comparison
          </h3>
                {/* Production vs Candidate V5 comparison chart */}
      <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/30 p-3 sm:p-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-xs font-semibold text-slate-200">
              Landslide Model Score Comparison
            </h3>
            <p className="mt-1 text-[10px] text-slate-500">
              District-wise comparison using the latest monitoring run
            </p>
          </div>

          <span className="text-[10px] text-slate-400">
            Both models available: {chartBothModelCount}/13 districts
          </span>
        </div>

        {chartHasData ? (
          <>
            <div className="mt-4 overflow-x-auto">
              <svg
                viewBox={`0 0 ${chartWidth} ${chartHeight}`}
                className="h-auto w-full min-w-[780px]"
                role="img"
                aria-label="Production and Candidate V5 landslide risk score comparison across Uttarakhand districts"
              >
                {/* Horizontal score grid */}
                {chartTicks.map((tick) => {
                  const y = chartY(tick);

                  return (
                    <g key={`tick-${tick}`}>
                      <line
                        x1={chartLeft}
                        y1={y}
                        x2={chartRight}
                        y2={y}
                        stroke="#334155"
                        strokeWidth="1"
                        strokeDasharray="4 5"
                      />

                      <text
                        x={chartLeft - 12}
                        y={y + 3}
                        fontSize="10"
                        fill="#94a3b8"
                        textAnchor="end"
                      >
                        {tick}
                      </text>
                    </g>
                  );
                })}

                {/* Chart axes */}
                <line
                  x1={chartLeft}
                  y1={chartTop}
                  x2={chartLeft}
                  y2={chartBottom}
                  stroke="#64748b"
                  strokeWidth="1"
                />

                <line
                  x1={chartLeft}
                  y1={chartBottom}
                  x2={chartRight}
                  y2={chartBottom}
                  stroke="#64748b"
                  strokeWidth="1"
                />

                {/* Production model line */}
                {productionChartPaths.map((path, index) => (
                  <path
                    key={`production-path-${index}`}
                    d={path}
                    fill="none"
                    stroke="#38bdf8"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                ))}

                {/* Candidate V5 model line */}
                {candidateChartPaths.map((path, index) => (
                  <path
                    key={`candidate-path-${index}`}
                    d={path}
                    fill="none"
                    stroke="#a78bfa"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                ))}

                {/* Production score points */}
                {chartRows.map((point) =>
                  point.production === null ? null : (
                    <circle
                      key={`production-point-${point.district}`}
                      cx={chartX(point.index)}
                      cy={chartY(point.production)}
                      r="4.5"
                      fill="#38bdf8"
                      stroke="#0f172a"
                      strokeWidth="2"
                    >
                      <title>
                        {`${point.district} · Production: ${point.production}/100`}
                      </title>
                    </circle>
                  )
                )}

                {/* Candidate score points */}
                {chartRows.map((point) =>
                  point.candidate === null ? null : (
                    <circle
                      key={`candidate-point-${point.district}`}
                      cx={chartX(point.index)}
                      cy={chartY(point.candidate)}
                      r="4.5"
                      fill="#a78bfa"
                      stroke="#0f172a"
                      strokeWidth="2"
                    >
                      <title>
                        {`${point.district} · Candidate V5: ${point.candidate}/100`}
                      </title>
                    </circle>
                  )
                )}

                {/* District labels */}
                {chartRows.map((point) => {
                  const x = chartX(point.index);

                  return (
                    <text
                      key={`district-label-${point.district}`}
                      x={x}
                      y="250"
                      transform={`rotate(38 ${x} 250)`}
                      fontSize="10"
                      fill="#cbd5e1"
                      textAnchor="start"
                    >
                      {point.district}
                    </text>
                  );
                })}
              </svg>
            </div>

            {/* Legend */}
            <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-sky-400" />
                <span className="text-[10px] text-slate-300">
                  Production Model
                </span>
              </div>

              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-violet-400" />
                <span className="text-[10px] text-slate-300">
                  Candidate V5
                </span>
              </div>
            </div>

            <p className="mt-3 text-[10px] leading-relaxed text-slate-500">
              Scores are model-estimated landslide susceptibility scores.
              Missing results are left as gaps; they are not treated as zero.
              A higher score does not establish better model accuracy.
            </p>
          </>
        ) : (
          <div className="mt-4 rounded-xl border border-dashed border-slate-800 p-5 text-center text-[11px] text-slate-500">
            No valid model scores are available for the comparison graph yet.
            Complete a monitoring cycle to populate it.
          </div>
        )}
      </div>
          <span className="text-[10px] text-slate-500">
            {districtRows.length}/13 records
          </span>
        </div>

        {districtRows.length > 0 ? (
          <div className="max-h-[480px] overflow-auto rounded-xl border border-slate-800">
            <table className="min-w-[850px] w-full border-collapse text-left">
              <thead className="sticky top-0 z-10 bg-slate-950">
                <tr className="border-b border-slate-800 text-[9px] uppercase tracking-wider text-slate-500">
                  <th className="px-3 py-3">District</th>
                  <th className="px-3 py-3">Production</th>
                  <th className="px-3 py-3">Candidate V5</th>
                  <th className="px-3 py-3">Score difference</th>
                  <th className="px-3 py-3">Level agreement</th>
                  <th className="px-3 py-3">Official check</th>
                </tr>
              </thead>
              <tbody>
                {districtRows.map((row) => {
                  const difference =
                    row.comparison?.absolute_score_difference;
                  const officialStatus =
                    row.official_verification?.status || "unavailable";

                  return (
                    <tr
                      key={row.district}
                      className="border-b border-slate-800/70 align-top last:border-0 hover:bg-slate-800/20"
                    >
                      <td className="px-3 py-3 text-xs font-semibold text-slate-200">
                        {row.district}
                      </td>

                      <td className="px-3 py-3">
                        <ModelCell model={row.production} />
                      </td>

                      <td className="px-3 py-3">
                        <ModelCell model={row.candidate_v5} />
                      </td>

                      <td className="px-3 py-3 text-xs text-slate-300">
                        {difference == null
                          ? "—"
                          : `${Number(difference).toFixed(1)} pts`}
                      </td>

                      <td className="px-3 py-3">
                        <span
                          className={`rounded-lg border px-2 py-1 text-[10px] ${statusClass(
                            row.comparison?.risk_levels_agree === true
                              ? "ok"
                              : row.comparison?.risk_levels_agree === false
                                ? "partial"
                                : "unknown"
                          )}`}
                        >
                          {row.comparison?.risk_levels_agree === true
                            ? "Same level"
                            : row.comparison?.risk_levels_agree === false
                              ? "Different"
                              : "Unavailable"}
                        </span>
                      </td>

                      <td className="px-3 py-3">
                        <span
                          className={`rounded-lg border px-2 py-1 text-[10px] ${statusClass(
                            officialStatus
                          )}`}
                        >
                          {officialStatus === "verified"
                            ? "Alert matched"
                            : officialStatus === "not_matched"
                              ? "No district match"
                              : officialStatus === "source_error"
                                ? "Source error"
                                : officialStatus}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-slate-800 p-6 text-center">
            <Activity className="mx-auto h-5 w-5 text-slate-600" />
            <p className="mt-2 text-xs text-slate-400">
              {loading
                ? "Loading monitoring history..."
                : "No monitoring run is available yet."}
            </p>
            <p className="mt-1 text-[10px] text-slate-600">
              Existing saved data will appear here after a monitoring cycle
              has completed.
            </p>
          </div>
        )}
      </div>

      <div className="mt-5">
        <div className="mb-3 flex items-center gap-2">
          <History className="h-4 w-4 text-slate-400" />
          <h3 className="text-xs font-semibold text-slate-200">
            Recent run history
          </h3>
        </div>

        {runs.length > 0 ? (
          <div className="space-y-2">
            {runs.slice(0, 5).map((run, index) => (
              <div
                key={run.run_id ?? `${run.started_at}-${index}`}
                className="flex flex-col gap-2 rounded-xl border border-slate-800 bg-slate-950/30 p-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <div className="text-[11px] font-semibold text-slate-300">
                    Run #{run.run_id ?? "—"}
                  </div>
                  <div className="mt-1 text-[10px] text-slate-500">
                    Started: {formatDate(run.started_at)}
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-lg border px-2 py-1 text-[10px] ${statusClass(
                      run.status
                    )}`}
                  >
                    {run.status || "unknown"}
                  </span>
                  <span className="text-[10px] text-slate-500">
                    {formatDate(run.finished_at)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-[10px] text-slate-500">
            No historical runs have been returned by the backend.
          </p>
        )}
      </div>

      <div className="mt-4 flex items-start gap-2 text-[10px] leading-relaxed text-slate-500">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <p>
          Candidate V5 is experimental. This panel compares model outputs; it
          does not promote the candidate, change production predictions, or
          establish predictive accuracy without verified labelled events.
        </p>
      </div>
    </section>
  );
}