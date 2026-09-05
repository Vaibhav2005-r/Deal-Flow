import { useEffect, useState } from "react";
import { api, type Quote } from "@/lib/api";
import { RiskBadge, StateBadge } from "./components";

export default function QuoteList() {
  const [quotes, setQuotes] = useState<Quote[]>([]);

  useEffect(() => {
    api.get<Quote[]>("/api/quotes").then(setQuotes).catch(() => setQuotes([]));
  }, []);

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-slate-900">Quotations</h2>
      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th className="px-4 py-2 font-medium">#</th>
              <th className="px-4 py-2 font-medium">Customer</th>
              <th className="px-4 py-2 font-medium">State</th>
              <th className="px-4 py-2 font-medium">Risk</th>
              <th className="px-4 py-2 font-medium text-right">Lines</th>
              <th className="px-4 py-2 font-medium text-right">Net</th>
            </tr>
          </thead>
          <tbody>
            {quotes.slice(0, 40).map((q) => (
              <tr key={q.id} className="border-t border-slate-100">
                <td className="px-4 py-2 text-slate-500">{q.id}</td>
                <td className="px-4 py-2">{q.customer_name}</td>
                <td className="px-4 py-2"><StateBadge state={q.state} /></td>
                <td className="px-4 py-2">
                  <RiskBadge score={q.risk_score ? Number(q.risk_score) : null} />
                </td>
                <td className="px-4 py-2 text-right">{q.totals.line_count}</td>
                <td className="px-4 py-2 text-right tabular-nums">
                  {new Intl.NumberFormat("en-IN").format(Number(q.totals.net_total))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
