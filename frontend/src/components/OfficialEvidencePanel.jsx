
import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BookOpen,
  CalendarDays,
  CheckCircle2,
  Clock3,
  ExternalLink,
  FileText,
  MapPin,
  RefreshCw,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import { dashboardApi } from "../api/dashboardApi";

function formatDate(value) {
  if (!value) return "Not available";

  const date = new Date(value);

  return Number.isNaN(date.getTime())
    ? String(value)
    : date.toLocaleString();
}

function statusStyle(status) {
  const value = String(status || "").toLowerCase();

  if (
    value === "ok" ||
    value === "complete" ||
    value === "verified"
  ) {
    return "border-emerald-500/30 bg-emerald-500/10 text-emerald-300";
  }

  if (
    value.includes("partial") ||
    value.includes("no_independent_match") ||
    value.includes("not_verified")
  ) {
    return "border-amber-500/30 bg-amber-500/10 text-amber-300";
  }

  if (value.includes("error") || value.includes("unavailable")) {
    return "border-rose-500/30 bg-rose-500/10 text-rose-300";
  }

  return "border-slate-700 bg-slate-800/70 text-slate-300";
}

function formatStatus(value) {
  return String(value || "unknown")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function StatusBadge({ status }) {
  return (
    <span
      className={`inline-flex rounded-lg border px-2 py-1 text-[10px] font-medium ${statusStyle(
        status
      )}`}
    >
      {formatStatus(status)}
    </span>
  );
}

function Metric({ label, value, detail, icon: Icon }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-500">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>

      <div className="mt-2 text-lg font-semibold text-slate-100">
        {value}
      </div>

      <div className="mt-1 text-[10px] text-slate-500">{detail}</div>
    </div>
  );
}

function Signal({ label, matched }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[10px] ${
        matched
          ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-300"
          : "border-slate-700 bg-slate-800/40 text-slate-400"
      }`}
    >
      {matched ? (
        <CheckCircle2 className="h-3 w-3" />
      ) : (
        <XCircle className="h-3 w-3" />
      )}
      {label}
    </span>
  );
}

function SourceCard({ source }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs font-semibold text-slate-200">
            {source.source_name || source.source_id}
          </div>

          <div className="mt-1 text-[10px] text-slate-500">
            {source.publisher || "Publisher unavailable"}
          </div>
        </div>

        <StatusBadge status={source.status} />
      </div>

      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-slate-500">
        <span>
          Published: {source.publication_date || "Not available"}
        </span>

        <span>
          Type: {String(source.kind || "unknown").toUpperCase()}
        </span>

        {source.pages_total != null && (
          <span>
            Pages processed: {source.pages_processed ?? 0}/
            {source.pages_total}
          </span>
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-3">
        <StatusBadge status={source.evidence_role} />

        {source.url && (
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-[10px] text-sky-300 hover:text-sky-200"
          >
            Open official source
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>
    </div>
  );
}

function CandidateCard({ candidate }) {
  const signals =
    candidate.evidence_records?.[0]?.matching_signals || {};

  return (
    <article className="rounded-xl border border-slate-800 bg-slate-950/40 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-slate-100">
            {candidate.event_name || candidate.candidate_id}
          </h3>

          <div className="mt-2 flex flex-wrap gap-3 text-[10px] text-slate-400">
            <span className="inline-flex items-center gap-1">
              <CalendarDays className="h-3 w-3" />
              {candidate.event_date_start || "Unknown date"}
              {candidate.event_date_end &&
                candidate.event_date_end !== candidate.event_date_start &&
                ` to ${candidate.event_date_end}`}
            </span>

            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3 w-3" />
              {candidate.place_name || "Unknown location"}
              {candidate.district ? `, ${candidate.district}` : ""}
              {candidate.state ? `, ${candidate.state}` : ""}
            </span>
          </div>
        </div>

        <StatusBadge status={candidate.corroboration_status} />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Metric
          label="Official matches"
          value={candidate.matching_official_source_count ?? 0}
          detail="Matching sources"
          icon={FileText}
        />

        <Metric
          label="Claim checks"
          value={candidate.matching_claim_check_source_count ?? 0}
          detail="Claim-check sources"
          icon={BookOpen}
        />

        <Metric
          label="Context only"
          value={candidate.matching_context_only_source_count ?? 0}
          detail="Context sources"
          icon={Activity}
        />

        <Metric
          label="Specific claims"
          value={candidate.matching_specific_claim_source_count ?? 0}
          detail="Complete matches"
          icon={ShieldAlert}
        />
      </div>

      <div className="mt-4">
        <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          Evidence matching signals
        </div>

        <div className="flex flex-wrap gap-2">
          <Signal label="Place" matched={signals.place_match} />
          <Signal label="Date" matched={signals.date_match} />
          <Signal label="District" matched={signals.district_match} />
          <Signal
            label="Event context"
            matched={signals.event_context_match}
          />
          <Signal
            label="Specific claim complete"
            matched={signals.specific_claim_complete}
          />
        </div>
      </div>

      {candidate.evidence_excerpt && (
        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-900/50 p-3">
          <div className="text-[10px] font-semibold text-slate-400">
            Original historical record excerpt
          </div>

          <p className="mt-2 text-[11px] leading-relaxed text-slate-300">
            {candidate.evidence_excerpt}
          </p>

          <div className="mt-2 text-[10px] text-slate-500">
            Atlas page: {candidate.pdf_page_number ?? "N/A"}
            {candidate.figure_number != null &&
              ` · Figure ${candidate.figure_number}`}
          </div>
        </div>
      )}

      {candidate.evidence_records?.length > 0 && (
        <div className="mt-4">
          <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Corroborating source records
          </div>

          <div className="space-y-3">
            {candidate.evidence_records.map((record, index) => (
              <div
                key={`${record.source_id || "source"}-${index}`}
                className="rounded-lg border border-slate-800 p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-[11px] font-semibold text-slate-300">
                    {record.source_name || record.source_id}
                  </div>

                  <StatusBadge status={record.match_status} />
                </div>

                <div className="mt-1 text-[10px] text-slate-500">
                  {record.publisher || "Publisher unavailable"} ·{" "}
                  {record.evidence_role || "Role unavailable"}
                </div>

                {record.url && (
                  <a
                    href={record.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-flex items-center gap-1 text-[10px] text-sky-300 hover:text-sky-200"
                  >
                    View source
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}

                {record.evidence_excerpts?.map((excerpt, excerptIndex) => (
                  <p
                    key={excerptIndex}
                    className="mt-2 text-[10px] leading-relaxed text-slate-400"
                  >
                    {excerpt}
                  </p>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <StatusBadge status={candidate.verification_status} />
        <StatusBadge status={candidate.review_status} />

        <span className="text-[10px] text-slate-500">
          Model validation:{" "}
          {candidate.may_be_used_for_model_validation
            ? "Eligible"
            : "Not eligible"}
        </span>
      </div>

      {candidate.decision_note && (
        <p className="mt-3 text-[10px] leading-relaxed text-slate-500">
          {candidate.decision_note}
        </p>
      )}
    </article>
  );
}

export default function OfficialEvidencePanel() {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const loadEvidence = useCallback(async (silent = false) => {
    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      const result = await dashboardApi.getLatestEvidence();

      if (!result?.available) {
        throw new Error("Evidence report is not available.");
      }

      setReport(result);
      setError("");
    } catch (err) {
      setError(err?.message || "Unable to load official evidence.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadEvidence();
  }, [loadEvidence]);

  const sources = Array.isArray(report?.sources)
    ? report.sources
    : [];

  const candidates = Array.isArray(report?.candidates)
    ? report.candidates
    : [];

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4 shadow-xl">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <BookOpen className="h-5 w-5 text-sky-400" />
            <h2 className="text-sm font-semibold text-slate-100">
              Official Evidence & Historical Events
            </h2>
          </div>

          <p className="mt-1 text-[11px] text-slate-500">
            NRSC historical event references checked against allowlisted
            official sources
          </p>
        </div>

        <button
          type="button"
          onClick={() => void loadEvidence(true)}
          disabled={loading || refreshing}
          className="flex items-center justify-center gap-2 rounded-xl border border-slate-700 px-3 py-2 text-[10px] text-slate-300 transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${
              refreshing ? "animate-spin" : ""
            }`}
          />
          Refresh report
        </button>
      </div>

      {error && (
        <div className="mt-4 flex gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-[11px] text-rose-200">
          <XCircle className="h-4 w-4 shrink-0" />
          <div className="break-words">{error}</div>
        </div>
      )}

      {loading && !report ? (
        <div className="mt-5 flex items-center gap-2 text-xs text-slate-400">
          <RefreshCw className="h-4 w-4 animate-spin" />
          Loading saved evidence report...
        </div>
      ) : report ? (
        <>
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Metric
              icon={FileText}
              label="Official sources"
              value={report.source_count ?? sources.length}
              detail="Configured source records"
            />

            <Metric
              icon={Activity}
              label="Historical candidates"
              value={report.candidate_count ?? candidates.length}
              detail="Extracted event references"
            />

            <Metric
              icon={ShieldAlert}
              label="Verification"
              value={formatStatus(report.verification_status)}
              detail="Overall report status"
            />

            <Metric
              icon={Clock3}
              label="Last report"
              value={formatDate(report.generated_at)}
              detail="Saved report generation time"
            />
          </div>

          <div className="mt-4 rounded-xl border border-amber-500/20 bg-amber-500/5 p-3">
            <div className="flex items-center gap-2 text-xs font-semibold text-amber-200">
              <AlertTriangle className="h-4 w-4" />
              Evidence review and ML eligibility
            </div>

            <p className="mt-2 text-[11px] leading-relaxed text-slate-300">
              Human review required:{" "}
              <strong>
                {report.human_review_required ? "Yes" : "No"}
              </strong>
              {" · "}
              Model accuracy:{" "}
              <strong>{report.model_accuracy || "Not evaluated"}</strong>
              {" · "}
              Training/model validation:{" "}
              <strong>
                {report.eligible_for_training_or_model_validation
                  ? "Eligible"
                  : "Not eligible"}
              </strong>
            </p>

            <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
              A source match is documentary evidence, not automatic ground
              truth. Historical candidates remain separate from validated
              ML labels until human review and independent verification.
            </p>
          </div>

          <div className="mt-5">
            <h3 className="mb-3 text-xs font-semibold text-slate-200">
              Historical event candidates
            </h3>

            {candidates.length > 0 ? (
              <div className="space-y-3">
                {candidates.map((candidate, index) => (
                  <CandidateCard
                    key={candidate.candidate_id || index}
                    candidate={candidate}
                  />
                ))}
              </div>
            ) : (
              <p className="rounded-xl border border-dashed border-slate-700 p-5 text-center text-[11px] text-slate-500">
                No historical event candidates are available.
              </p>
            )}
          </div>

          <div className="mt-5">
            <h3 className="mb-3 text-xs font-semibold text-slate-200">
              Official source registry results
            </h3>

            {sources.length > 0 ? (
              <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                {sources.map((source, index) => (
                  <SourceCard
                    key={source.source_id || index}
                    source={source}
                  />
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-slate-500">
                No source records are available.
              </p>
            )}
          </div>

          {report.limitations?.length > 0 && (
            <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/30 p-3">
              <div className="text-[10px] font-semibold text-slate-400">
                Report limitations
              </div>

              <ul className="mt-2 list-disc space-y-1 pl-4 text-[10px] leading-relaxed text-slate-500">
                {report.limitations.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
            <Clock3 className="h-3.5 w-3.5" />
            This panel displays the last saved report. Refreshing this
            panel reads the report again; it does not download sources
            or run a new corroboration audit.
          </div>
        </>
      ) : !error ? (
        <div className="mt-5 text-xs text-slate-500">
          No evidence report is available yet.
        </div>
      ) : null}
    </section>
  );
}
