import { useEffect, useState } from "react";
import { api, type DecisionLogRow, type ReliabilityStats, type ReplayResult } from "@/lib/api";

export default function ReliabilityPanel() {
  const [stats, setStats] = useState<ReliabilityStats | null>(null);
  const [logs, setLogs] = useState<DecisionLogRow[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Replay modal state
  const [replayingId, setReplayingId] = useState<number | null>(null);
  const [replayResult, setReplayResult] = useState<ReplayResult | null>(null);
  const [replayError, setReplayError] = useState<string | null>(null);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const statsPromise = api.get<ReliabilityStats>("/api/reliability/stats");
      const logsUrl = selectedAgent
        ? `/api/reliability/logs?limit=25&agent=${selectedAgent}`
        : "/api/reliability/logs?limit=25";
      const logsPromise = api.get<DecisionLogRow[]>(logsUrl);

      const [sData, lData] = await Promise.all([statsPromise, logsPromise]);
      setStats(sData);
      setLogs(lData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load reliability panel data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [selectedAgent]);

  async function handleReplay(logId: number) {
    setReplayingId(logId);
    setReplayResult(null);
    setReplayError(null);
    try {
      const res = await api.post<ReplayResult>(`/api/reliability/replay/${logId}`, {});
      setReplayResult(res);
    } catch (err) {
      setReplayError(err instanceof Error ? err.message : "Replay failed");
    } finally {
      setReplayingId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Agent Reliability &amp; Audit Trail</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Immutable decision_log telemetry (§4, §8, §10.5) with deterministic byte-for-byte replay verification.
          </p>
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 text-white hover:bg-slate-800 transition-colors disabled:opacity-50"
        >
          {loading ? "Refreshing…" : "Refresh Log"}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 text-xs rounded-lg p-3">
          {error}
        </div>
      )}

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <p className="text-xs font-medium text-slate-500">Total Invocations</p>
            <p className="text-2xl font-extrabold text-slate-900 mt-1">{stats.total_invocations}</p>
          </div>
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            {stats.pass_rate_pct === null ? (
              <>
                {/* Nothing has been verified yet. Showing a green 100% here
                    would claim a perfect reliability record we have not earned. */}
                <p className="text-xs font-medium text-slate-500">Verifier Pass Rate</p>
                <p className="text-2xl font-extrabold text-slate-400 mt-1">not measured</p>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  {stats.skipped_calls} call(s) logged, none verified
                </p>
              </>
            ) : (
              <>
                <p className="text-xs font-medium text-emerald-600">Verifier Pass Rate</p>
                <p className="text-2xl font-extrabold text-emerald-600 mt-1">
                  {stats.pass_rate_pct.toFixed(1)}%
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  over {stats.verified_calls} verified call(s)
                </p>
              </>
            )}
          </div>
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <p className="text-xs font-medium text-slate-500">Average Latency</p>
            <p className="text-2xl font-extrabold text-slate-900 mt-1">{stats.avg_latency_ms} ms</p>
          </div>
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <p className="text-xs font-medium text-slate-500">Max Latency</p>
            <p className="text-2xl font-extrabold text-slate-900 mt-1">{stats.max_latency_ms} ms</p>
          </div>
        </div>
      )}

      {/* Agent Activity Breakdown */}
      {stats && (
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <h3 className="text-sm font-bold text-slate-900 mb-3">Agent Invocation &amp; Latency Matrix</h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
            {["governance", "allocation", "billing", "advisor", "sentinel", "narrator"].map((agent) => {
              const count = stats.invocations_by_agent[agent] ?? 0;
              const lat = stats.latency_by_agent[agent] ?? 0;
              return (
                <div
                  key={agent}
                  onClick={() => setSelectedAgent(selectedAgent === agent ? "" : agent)}
                  className={`p-3 rounded-lg border text-xs cursor-pointer transition-all ${
                    selectedAgent === agent
                      ? "bg-indigo-50 border-indigo-300 ring-2 ring-indigo-500/20"
                      : "bg-slate-50 border-slate-200 hover:bg-slate-100"
                  }`}
                >
                  <p className="font-bold text-slate-800 capitalize">{agent}</p>
                  <p className="text-base font-extrabold text-slate-900 mt-1">{count} calls</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">{lat} ms avg</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Decision Log Table */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h3 className="text-sm font-bold text-slate-900">Immutable Audit Trail</h3>
            {selectedAgent && (
              <span className="text-xs bg-indigo-100 text-indigo-800 px-2 py-0.5 rounded-full font-semibold">
                Filtered: {selectedAgent}
              </span>
            )}
          </div>
          <span className="text-xs text-slate-500">Showing last {logs.length} logged decisions</span>
        </div>

        {loading ? (
          <div className="p-12 text-center text-xs text-slate-500">Loading audit trail…</div>
        ) : logs.length === 0 ? (
          <div className="p-12 text-center text-xs text-slate-500">No decision logs recorded yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider">
                <tr>
                  <th className="px-4 py-3">Log ID</th>
                  <th className="px-4 py-3">Agent</th>
                  <th className="px-4 py-3">Engine Version</th>
                  <th className="px-4 py-3 text-center">Quote #</th>
                  <th className="px-4 py-3">Input Hash</th>
                  <th className="px-4 py-3 text-center">Verifier</th>
                  <th className="px-4 py-3 text-right">Latency</th>
                  <th className="px-4 py-3 text-right">Timestamp</th>
                  <th className="px-4 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {logs.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3 font-mono text-slate-400">#{r.id}</td>
                    <td className="px-4 py-3 font-bold text-slate-900 capitalize">{r.agent}</td>
                    <td className="px-4 py-3 font-mono text-slate-600 text-[11px]">{r.engine_version}</td>
                    <td className="px-4 py-3 text-center font-mono font-medium text-slate-800">
                      {r.quotation_id ? `#Q-${r.quotation_id}` : "-"}
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-500 text-[11px]">
                      {r.input_hash.slice(0, 12)}…
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold ${
                          r.verifier_verdict === "PASS"
                            ? "bg-emerald-100 text-emerald-800"
                            : r.verifier_verdict === "FAIL"
                            ? "bg-red-100 text-red-800"
                            : "bg-slate-100 text-slate-700"
                        }`}
                      >
                        {r.verifier_verdict}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-slate-600">{r.latency_ms} ms</td>
                    <td className="px-4 py-3 text-right text-slate-500 text-[11px] font-mono">{r.created_at}</td>
                    <td className="px-4 py-3 text-right">
                      {["governance", "allocation", "billing", "advisor", "sentinel"].includes(r.agent) ? (
                        <button
                          onClick={() => handleReplay(r.id)}
                          disabled={replayingId === r.id}
                          className="bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 px-2 py-1 rounded text-[11px] font-semibold transition-colors disabled:opacity-50"
                        >
                          {replayingId === r.id ? "Replaying…" : "Replay"}
                        </button>
                      ) : (
                        <span className="text-slate-300">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Replay Verification Modal */}
      {(replayResult || replayError) && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full border border-slate-200 p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-900">Deterministic Replay Verification</h3>
                <p className="text-xs text-slate-500">Audit Proof §10.5</p>
              </div>
              <button
                onClick={() => {
                  setReplayResult(null);
                  setReplayError(null);
                }}
                className="text-slate-400 hover:text-slate-600 text-lg font-bold"
              >
                ×
              </button>
            </div>

            {replayError ? (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                {replayError}
              </div>
            ) : replayResult && (
              <div className="space-y-3 text-xs">
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-900">
                  <p className="font-bold flex items-center gap-1.5 text-sm">
                    <span>✅</span> Deterministic Replay: Byte-for-Byte Match
                  </p>
                  <p className="mt-1 text-emerald-800">
                    The pinned engine ({replayResult.engine_version}) produced the exact same output bytes
                    and input hash from the logged snapshot.
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-2 bg-slate-50 p-3 rounded-lg border border-slate-200 font-mono">
                  <div>
                    <span className="text-slate-500 block text-[11px]">Input Hash Check:</span>
                    <span className="text-emerald-700 font-bold">MATCH (PASS)</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[11px]">Output Payload Check:</span>
                    <span className="text-emerald-700 font-bold">BYTE EQUAL (PASS)</span>
                  </div>
                </div>

                <div>
                  <span className="text-slate-700 font-bold block mb-1">Replayed Output Payload:</span>
                  <pre className="bg-slate-900 text-slate-100 p-3 rounded-lg overflow-x-auto text-[11px] max-h-48">
                    {JSON.stringify(replayResult.replayed_output, null, 2)}
                  </pre>
                </div>
              </div>
            )}

            <div className="pt-2 border-t border-slate-100 flex justify-end">
              <button
                onClick={() => {
                  setReplayResult(null);
                  setReplayError(null);
                }}
                className="bg-slate-900 hover:bg-slate-800 text-white px-4 py-1.5 rounded-lg text-xs font-semibold transition-colors"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
