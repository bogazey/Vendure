import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import ErrorBanner from "../../components/ErrorBanner";
import { ApiError, api } from "../../services/api";
import { statLabel, statTile, statValue } from "../../styles/ui";
import type {
  AnalyticsOverviewOut,
  AnalyticsRange,
  BreakdownRowOut,
  DevicesOut,
  DownloadsOut,
  FunnelOut,
  GeographyOut,
  PagesOut,
  RevenueOut,
  SourcesOut,
  TrafficOut,
} from "../../types/analytics";
import AdminLayout from "./AdminLayout";

const RANGES: AnalyticsRange[] = ["today", "7d", "30d", "90d"];

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className={statTile}>
      <span className={statLabel}>{label}</span>
      <span className={statValue}>{value}</span>
    </div>
  );
}

function pct(value: number) {
  return `${value.toFixed(1)}%`;
}

function BarRows({ rows, emptyLabel }: { rows: { key: string; count: number; pct: number }[]; emptyLabel: string }) {
  if (rows.length === 0) return <p className="text-sm text-slate-500">{emptyLabel}</p>;
  return (
    <ul className="flex flex-col gap-2.5">
      {rows.map((row) => (
        <li key={row.key} className="flex flex-col gap-1">
          <div className="flex items-center justify-between gap-3 text-sm text-slate-300">
            <span className="min-w-0 truncate">{row.key}</span>
            <span className="shrink-0 text-xs text-slate-500">
              {row.count.toLocaleString()} · {pct(row.pct)}
            </span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
            <div className="h-full rounded-full bg-brand-gradient" style={{ width: `${Math.max(2, Math.min(100, row.pct))}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function breakdownRows(rows: BreakdownRowOut[]): { key: string; count: number; pct: number }[] {
  return rows.map((r) => ({ key: r.key, count: r.count, pct: r.pct }));
}

function TrafficChart({ traffic }: { traffic: TrafficOut }) {
  const { t } = useTranslation();
  const points = traffic.points;
  if (points.length === 0) return <p className="text-sm text-slate-500">{t("admin.statistics.noData")}</p>;

  const width = 640;
  const height = 180;
  const padX = 4;
  const padY = 10;
  const maxValue = Math.max(1, ...points.map((p) => Math.max(p.visitors, p.page_views)));
  const stepX = points.length > 1 ? (width - padX * 2) / (points.length - 1) : 0;
  const toY = (v: number) => height - padY - (v / maxValue) * (height - padY * 2);
  const toX = (i: number) => padX + i * stepX;
  const path = (key: "visitors" | "page_views") =>
    points.map((p, i) => `${i === 0 ? "M" : "L"} ${toX(i).toFixed(1)} ${toY(p[key]).toFixed(1)}`).join(" ");

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-40 w-full" preserveAspectRatio="none" role="img" aria-label={t("admin.statistics.traffic")}>
        <defs>
          <linearGradient id="traffic-line" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#22D3EE" />
            <stop offset="55%" stopColor="#3B82F6" />
            <stop offset="100%" stopColor="#8B5CF6" />
          </linearGradient>
        </defs>
        <path d={path("page_views")} fill="none" stroke="rgba(148,163,184,0.45)" strokeWidth={2} />
        <path d={path("visitors")} fill="none" stroke="url(#traffic-line)" strokeWidth={2.5} />
      </svg>
      <div className="mt-2 flex flex-wrap gap-4 text-xs text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-brand-gradient" /> {t("admin.statistics.visitors")}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-slate-500" /> {t("admin.statistics.pageViews")}
        </span>
        <span className="ms-auto" dir="ltr">
          {points[0]?.date} &ndash; {points[points.length - 1]?.date}
        </span>
      </div>
    </div>
  );
}

function FunnelChart({ funnel }: { funnel: FunnelOut }) {
  const maxCount = Math.max(1, ...funnel.stages.map((s) => s.count));
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2.5">
        {funnel.stages.map((stage) => (
          <div key={stage.key} className="flex items-center gap-3">
            <span className="w-24 shrink-0 text-xs font-medium text-slate-400">{stage.label}</span>
            <div className="h-6 flex-1 overflow-hidden rounded-lg bg-white/[0.06]">
              <div
                className="flex h-full items-center rounded-lg bg-brand-gradient px-2 text-xs font-semibold text-white"
                style={{ width: `${Math.max(4, (stage.count / maxCount) * 100)}%` }}
              >
                {stage.count.toLocaleString()}
              </div>
            </div>
            <span className="w-14 shrink-0 text-end text-xs text-slate-500" dir="ltr">
              {stage.pct_of_previous !== null ? pct(stage.pct_of_previous) : "—"}
            </span>
          </div>
        ))}
      </div>
      <p className="text-xs text-slate-600">{funnel.methodology_note}</p>
    </div>
  );
}

export default function AdminStatistics() {
  const { t } = useTranslation();
  const [range, setRange] = useState<AnalyticsRange>("30d");
  const [overview, setOverview] = useState<AnalyticsOverviewOut | null>(null);
  const [traffic, setTraffic] = useState<TrafficOut | null>(null);
  const [pages, setPages] = useState<PagesOut | null>(null);
  const [sources, setSources] = useState<SourcesOut | null>(null);
  const [geography, setGeography] = useState<GeographyOut | null>(null);
  const [devices, setDevices] = useState<DevicesOut | null>(null);
  const [downloads, setDownloads] = useState<DownloadsOut | null>(null);
  const [funnel, setFunnel] = useState<FunnelOut | null>(null);
  const [revenue, setRevenue] = useState<RevenueOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      api.adminAnalyticsOverview(range),
      api.adminAnalyticsTraffic(range),
      api.adminAnalyticsPages(range),
      api.adminAnalyticsSources(range),
      api.adminAnalyticsGeography(range),
      api.adminAnalyticsDevices(range),
      api.adminAnalyticsDownloads(range),
      api.adminAnalyticsFunnel(range),
      api.adminAnalyticsRevenue(range),
    ])
      .then(([o, tr, pg, sr, geo, dv, dl, fn, rv]) => {
        if (cancelled) return;
        setOverview(o);
        setTraffic(tr);
        setPages(pg);
        setSources(sr);
        setGeography(geo);
        setDevices(dv);
        setDownloads(dl);
        setFunnel(fn);
        setRevenue(rv);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : t("admin.statistics.loadError"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [range, t]);

  return (
    <AdminLayout>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-lg font-semibold text-slate-100">{t("admin.statistics.title")}</h2>
        <div className="flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.03] p-1" role="group" aria-label={t("admin.statistics.rangeLabel")}>
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setRange(r)}
              aria-pressed={range === r}
              className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                range === r ? "bg-white/[0.08] text-slate-50" : "text-slate-400 hover:text-slate-100"
              }`}
            >
              {t(`admin.statistics.range.${r}`)}
            </button>
          ))}
        </div>
      </div>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {loading && !overview ? (
        <p className="text-sm text-slate-500">{t("app.loading")}</p>
      ) : overview ? (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <StatCard label={t("admin.statistics.visitors")} value={overview.visitors.toLocaleString()} />
            <StatCard label={t("admin.statistics.pageViews")} value={overview.page_views.toLocaleString()} />
            <StatCard label={t("admin.statistics.downloadsCompleted")} value={overview.downloads_completed.toLocaleString()} />
            <StatCard label={t("admin.statistics.newUsers")} value={overview.new_users.toLocaleString()} />
            <StatCard label={t("admin.statistics.paidConversions")} value={overview.paid_conversions.toLocaleString()} />
            <StatCard label={t("admin.statistics.activeNow")} value={overview.active_now.toLocaleString()} />
          </div>

          <section className="glass-panel flex flex-col gap-3 p-4">
            <h3 className="text-sm font-semibold text-slate-100">{t("admin.statistics.traffic")}</h3>
            {traffic && <TrafficChart traffic={traffic} />}
          </section>

          <section className="glass-panel flex flex-col gap-3 p-4">
            <h3 className="text-sm font-semibold text-slate-100">{t("admin.statistics.funnel")}</h3>
            {funnel && <FunnelChart funnel={funnel} />}
          </section>

          <div className="grid gap-3 lg:grid-cols-2">
            <section className="glass-panel flex flex-col gap-3 p-4">
              <h3 className="text-sm font-semibold text-slate-100">{t("admin.statistics.topPages")}</h3>
              <BarRows
                emptyLabel={t("admin.statistics.noData")}
                rows={pages?.pages.map((p) => ({ key: p.path, count: p.views, pct: p.pct_of_total })) ?? []}
              />
            </section>

            <section className="glass-panel flex flex-col gap-3 p-4">
              <h3 className="text-sm font-semibold text-slate-100">{t("admin.statistics.sources")}</h3>
              <BarRows
                emptyLabel={t("admin.statistics.noData")}
                rows={sources?.sources.map((s) => ({ key: s.source, count: s.visitors, pct: s.pct_of_total })) ?? []}
              />
            </section>
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <section className="glass-panel flex flex-col gap-3 p-4">
              <h3 className="text-sm font-semibold text-slate-100">{t("admin.statistics.countries")}</h3>
              {geography && !geography.available ? (
                <p className="text-sm text-slate-500">{t("admin.statistics.geographyUnavailable")}</p>
              ) : (
                <ul className="flex flex-col gap-2 text-sm">
                  {geography?.countries.map((c) => (
                    <li key={c.country_code} className="flex items-center justify-between border-t border-white/[0.06] pt-2 text-slate-300 first:border-0 first:pt-0">
                      <span dir="ltr">{c.country_code}</span>
                      <span className="text-xs text-slate-500" dir="ltr">
                        {c.visitors.toLocaleString()} {t("admin.statistics.visitors").toLowerCase()} · {c.downloads.toLocaleString()} {t("admin.statistics.downloadsCompleted").toLowerCase()}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="glass-panel flex flex-col gap-3 p-4">
              <h3 className="text-sm font-semibold text-slate-100">{t("admin.statistics.languages")}</h3>
              <BarRows emptyLabel={t("admin.statistics.noData")} rows={breakdownRows(devices?.languages ?? [])} />
            </section>
          </div>

          <div className="grid gap-3 lg:grid-cols-3">
            <section className="glass-panel flex flex-col gap-3 p-4">
              <h3 className="text-sm font-semibold text-slate-100">{t("admin.statistics.devices")}</h3>
              <BarRows emptyLabel={t("admin.statistics.noData")} rows={breakdownRows(devices?.devices ?? [])} />
            </section>
            <section className="glass-panel flex flex-col gap-3 p-4">
              <h3 className="text-sm font-semibold text-slate-100">{t("admin.statistics.browsers")}</h3>
              <BarRows emptyLabel={t("admin.statistics.noData")} rows={breakdownRows(devices?.browsers ?? [])} />
            </section>
            <section className="glass-panel flex flex-col gap-3 p-4">
              <h3 className="text-sm font-semibold text-slate-100">{t("admin.statistics.os")}</h3>
              <BarRows emptyLabel={t("admin.statistics.noData")} rows={breakdownRows(devices?.os ?? [])} />
            </section>
          </div>

          <section className="glass-panel flex flex-col gap-4 p-4">
            <h3 className="text-sm font-semibold text-slate-100">{t("admin.statistics.downloadPerformance")}</h3>
            {downloads && (
              <>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <StatCard label={t("admin.statistics.analysesStarted")} value={downloads.analyze.started.toLocaleString()} />
                  <StatCard label={t("admin.statistics.downloadsStarted")} value={downloads.downloads.started.toLocaleString()} />
                  <StatCard
                    label={t("admin.statistics.successRate")}
                    value={downloads.downloads.success_rate !== null ? pct(downloads.downloads.success_rate) : "—"}
                  />
                  <StatCard
                    label={t("admin.statistics.avgProcessingTime")}
                    value={downloads.downloads.avg_processing_seconds !== null ? `${downloads.downloads.avg_processing_seconds.toFixed(0)}s` : "—"}
                  />
                </div>
                <div className="grid gap-4 lg:grid-cols-2">
                  <div>
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{t("admin.statistics.platforms")}</h4>
                    {downloads.platforms.length === 0 ? (
                      <p className="text-sm text-slate-500">{t("admin.statistics.noData")}</p>
                    ) : (
                      <ul className="flex flex-col gap-2 text-sm">
                        {downloads.platforms.map((p) => (
                          <li key={p.platform} className="flex items-center justify-between border-t border-white/[0.06] pt-2 text-slate-300 first:border-0 first:pt-0">
                            <span className="capitalize">{p.platform}</span>
                            <span className="text-xs text-slate-500" dir="ltr">
                              {p.downloads.toLocaleString()} · {p.success_rate !== null ? pct(p.success_rate) : "—"}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <div>
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{t("admin.statistics.errors")}</h4>
                    {downloads.failures.length === 0 ? (
                      <p className="text-sm text-slate-500">{t("admin.statistics.noData")}</p>
                    ) : (
                      <ul className="flex flex-col gap-2 text-sm">
                        {downloads.failures.map((f) => (
                          <li key={f.category} className="flex items-center justify-between border-t border-white/[0.06] pt-2 text-slate-300 first:border-0 first:pt-0">
                            <span>{t(`admin.statistics.failureCategory.${f.category}`, f.category)}</span>
                            <span className="text-xs text-slate-500">{f.count.toLocaleString()}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </>
            )}
          </section>

          <section className="glass-panel flex flex-col gap-3 p-4">
            <h3 className="text-sm font-semibold text-slate-100">{t("admin.statistics.plansRevenue")}</h3>
            {revenue && (
              <>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  <StatCard label={t("admin.statistics.activePaidSubscribers")} value={revenue.active_paid_subscribers.toLocaleString()} />
                  <StatCard label={t("admin.statistics.newPaidSubscribers")} value={revenue.new_paid_subscribers.toLocaleString()} />
                  <StatCard label={t("admin.statistics.cancellations")} value={revenue.cancellations.toLocaleString()} />
                </div>
                {revenue.movements.length > 0 && (
                  <ul className="flex flex-col gap-2 text-sm">
                    {revenue.movements.map((m) => (
                      <li key={m.kind} className="flex items-center justify-between border-t border-white/[0.06] pt-2 text-slate-300 first:border-0 first:pt-0">
                        <span className="capitalize">{m.kind.replace(/_/g, " ")}</span>
                        <span className="text-xs text-slate-500">{m.count.toLocaleString()}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="text-xs text-slate-600">{revenue.mrr_note}</p>
              </>
            )}
          </section>
        </>
      ) : null}
    </AdminLayout>
  );
}
