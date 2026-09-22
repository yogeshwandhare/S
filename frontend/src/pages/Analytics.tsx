import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PageHeader } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAnalyticsSummary } from "@/hooks/useAnalytics";

const WINDOW_OPTIONS = [7, 30, 90];

const CHART_COLORS = {
  grid: "#223140",
  axis: "#7c8b9a",
  bar: "#2dd4bf",
  line: "#38bdf8",
};

function formatSeconds(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

export function AnalyticsPage() {
  const [days, setDays] = useState(30);
  const { data, isLoading } = useAnalyticsSummary(days);

  const categoryData = data
    ? Object.entries(data.by_category).map(([name, count]) => ({
        name: name.replace("_", " "),
        count,
      }))
    : [];
  const cameraData = data
    ? Object.entries(data.by_camera).map(([name, count]) => ({ name, count }))
    : [];
  const trendData = data?.daily_trend.map((d) => ({ ...d, label: d.date.slice(5) })) ?? [];

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Analytics"
        description="Incident trends, categories, and response times from real database records."
        actions={
          <div className="flex gap-1">
            {WINDOW_OPTIONS.map((w) => (
              <button
                key={w}
                onClick={() => setDays(w)}
                className={`rounded-full border px-3 py-1 text-xs ${
                  days === w
                    ? "border-cyan/40 bg-cyan/10 text-cyan"
                    : "border-border-strong text-text-muted hover:text-text"
                }`}
              >
                {w}d
              </button>
            ))}
          </div>
        }
      />

      <div className="flex-1 space-y-4 p-6">
        {isLoading && <p className="text-sm text-text-muted">Loading…</p>}

        {data && (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Card>
                <CardContent className="py-3">
                  <p className="text-xs text-text-muted">Total incidents</p>
                  <p className="mt-1 text-2xl font-semibold text-text">{data.total_incidents}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="py-3">
                  <p className="text-xs text-text-muted">Resolved</p>
                  <p className="mt-1 text-2xl font-semibold text-text">{data.resolved_count}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="py-3">
                  <p className="text-xs text-text-muted">False positives</p>
                  <p className="mt-1 text-2xl font-semibold text-text">
                    {data.false_positive_count}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="py-3">
                  <p className="text-xs text-text-muted">Avg. time to acknowledge</p>
                  <p className="mt-1 text-2xl font-semibold text-text">
                    {formatSeconds(data.avg_response_time_seconds)}
                  </p>
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle>Incidents per day</CardTitle>
              </CardHeader>
              <CardContent className="h-64">
                {data.total_incidents === 0 ? (
                  <p className="text-sm text-text-muted">No incidents in this window yet.</p>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={trendData}>
                      <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" />
                      <XAxis dataKey="label" stroke={CHART_COLORS.axis} fontSize={11} />
                      <YAxis stroke={CHART_COLORS.axis} fontSize={11} allowDecimals={false} />
                      <Tooltip
                        contentStyle={{
                          background: "#101720",
                          border: "1px solid #223140",
                          borderRadius: 8,
                          fontSize: 12,
                        }}
                      />
                      <Line
                        type="monotone"
                        dataKey="count"
                        stroke={CHART_COLORS.line}
                        strokeWidth={2}
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle>By category</CardTitle>
                </CardHeader>
                <CardContent className="h-56">
                  {categoryData.length === 0 ? (
                    <p className="text-sm text-text-muted">No data yet.</p>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={categoryData}>
                        <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" />
                        <XAxis dataKey="name" stroke={CHART_COLORS.axis} fontSize={11} />
                        <YAxis stroke={CHART_COLORS.axis} fontSize={11} allowDecimals={false} />
                        <Tooltip
                          contentStyle={{
                            background: "#101720",
                            border: "1px solid #223140",
                            borderRadius: 8,
                            fontSize: 12,
                          }}
                        />
                        <Bar dataKey="count" fill={CHART_COLORS.bar} radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>By camera</CardTitle>
                </CardHeader>
                <CardContent className="h-56">
                  {cameraData.length === 0 ? (
                    <p className="text-sm text-text-muted">No data yet.</p>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={cameraData}>
                        <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" />
                        <XAxis dataKey="name" stroke={CHART_COLORS.axis} fontSize={11} />
                        <YAxis stroke={CHART_COLORS.axis} fontSize={11} allowDecimals={false} />
                        <Tooltip
                          contentStyle={{
                            background: "#101720",
                            border: "1px solid #223140",
                            borderRadius: 8,
                            fontSize: 12,
                          }}
                        />
                        <Bar dataKey="count" fill={CHART_COLORS.line} radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </CardContent>
              </Card>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
