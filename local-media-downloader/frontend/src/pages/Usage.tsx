import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

function ProgressBar({ used, total }: { used: number; total: number }) {
  const pct = total > 0 ? Math.min(100, (used / total) * 100) : 0;
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-surface">
      <div
        className={`h-full rounded-full ${pct >= 90 ? "bg-amber-400" : "bg-indigo-500"}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export default function Usage() {
  const { account } = useAuth();
  if (!account) return null;
  const { usage, features } = account;

  const isFree = usage.plan === "free";
  const used = isFree ? usage.daily_free_downloads_used ?? 0 : usage.credits_used;
  const total = isFree
    ? (usage.daily_free_downloads_used ?? 0) + (usage.daily_free_downloads_remaining ?? 0)
    : usage.credits_included ?? 0;
  const remaining = isFree ? usage.daily_free_downloads_remaining ?? 0 : usage.credits_remaining ?? 0;

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-6 py-10">
      <h1 className="text-xl font-bold text-slate-50">Usage</h1>

      <section className="flex flex-col gap-4 rounded-xl border border-surface-border bg-surface-raised p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
            {isFree ? "Free downloads today" : "Credits this period"}
          </h2>
          <span className="text-sm text-slate-300">
            {used} / {total}
          </span>
        </div>
        <ProgressBar used={used} total={total} />
        <p className="text-xs text-slate-500">
          {remaining} {isFree ? "download(s)" : "credit(s)"} remaining ·{" "}
          {isFree ? "resets daily at midnight UTC" : `renews ${new Date(usage.period_end).toLocaleDateString()}`}
        </p>
      </section>

      <section className="flex flex-col gap-3 rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Plan limits</h2>
        <div className="grid grid-cols-2 gap-y-2 text-sm text-slate-400">
          <span>Max resolution</span>
          <span className="text-slate-200">{features.max_resolution_height ? `${features.max_resolution_height}p` : "Best available"}</span>
          <span>4K downloads</span>
          <span className="text-slate-200">{features.can_use_4k ? "Included" : "Not included"}</span>
          <span>Batch downloads</span>
          <span className="text-slate-200">{features.can_use_batch ? "Included" : "Not included"}</span>
          <span>Advanced formats</span>
          <span className="text-slate-200">{features.can_use_advanced_formats ? "Included" : "Not included"}</span>
          <span>Clip range</span>
          <span className="text-slate-200">{features.can_use_clip_range ? "Included" : "Not included"}</span>
          <span>Browser cookies</span>
          <span className="text-slate-200">{features.can_use_browser_cookies ? "Included" : "Not included"}</span>
          <span>Queue priority</span>
          <span className="text-slate-200">{features.queue_priority}</span>
        </div>
      </section>

      {isFree && (
        <Link
          to="/pricing"
          className="self-start rounded-md bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-400"
        >
          Upgrade for more
        </Link>
      )}
    </div>
  );
}
