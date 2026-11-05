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

import type { CellValue, ChartSpec } from "../api/client";
import { type ChartPoint, chartPoints, chartTitle, formatCompact, formatFull } from "./chartData";

interface ResultChartProps {
  chart: ChartSpec;
  columns: string[];
  rows: CellValue[][];
}

interface TooltipProps {
  active?: boolean;
  payload?: readonly { payload?: ChartPoint }[];
}

const AXIS_TICK = { fill: "var(--muted)", fontSize: 12 };
const BAR_ROW_HEIGHT = 30;
const MAX_LABEL_LENGTH = 24;
const MAX_POINTS_WITH_DOTS = 24;

function shortLabel(label: string): string {
  return label.length > MAX_LABEL_LENGTH ? `${label.slice(0, MAX_LABEL_LENGTH - 1)}…` : label;
}

function ChartTooltip({ active, payload }: TooltipProps) {
  const point = payload?.[0]?.payload;
  if (!active || !point) {
    return null;
  }
  return (
    <div className="chart-tooltip">
      <span className="muted">{point.label}</span>
      <strong>{point.value === null ? "NULL" : formatFull(point.value)}</strong>
    </div>
  );
}

function HorizontalBars({ points }: { points: ChartPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={points.length * BAR_ROW_HEIGHT + 40}>
      <BarChart data={points} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 4 }}>
        <CartesianGrid horizontal={false} stroke="var(--border)" />
        <XAxis
          type="number"
          axisLine={false}
          tickLine={false}
          tick={AXIS_TICK}
          tickFormatter={formatCompact}
        />
        <YAxis
          type="category"
          dataKey="label"
          width={170}
          interval={0}
          axisLine={false}
          tickLine={false}
          tick={AXIS_TICK}
          tickFormatter={shortLabel}
        />
        <Tooltip content={ChartTooltip} cursor={{ fill: "var(--surface-subtle)" }} />
        <Bar
          dataKey="value"
          fill="var(--chart-series)"
          radius={[0, 4, 4, 0]}
          maxBarSize={20}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

function TimeLine({ points }: { points: ChartPoint[] }) {
  const dot =
    points.length <= MAX_POINTS_WITH_DOTS
      ? { r: 4, fill: "var(--chart-series)", stroke: "var(--surface)", strokeWidth: 2 }
      : false;

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={points} margin={{ top: 8, right: 28, bottom: 4, left: 4 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis
          dataKey="label"
          axisLine={false}
          tickLine={false}
          tick={AXIS_TICK}
          minTickGap={24}
          tickMargin={8}
        />
        <YAxis
          width={52}
          axisLine={false}
          tickLine={false}
          tick={AXIS_TICK}
          tickFormatter={formatCompact}
        />
        <Tooltip content={ChartTooltip} cursor={{ stroke: "var(--muted)" }} />
        <Line
          type="linear"
          dataKey="value"
          stroke="var(--chart-series)"
          strokeWidth={2}
          dot={dot}
          activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2 }}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function ResultChart({ chart, columns, rows }: ResultChartProps) {
  const title = chartTitle(columns, chart);
  const points = chartPoints(rows, chart);

  return (
    <section className="chart" aria-label={`${title} chart`}>
      <h2>{title}</h2>
      {chart.type === "bar" ? <HorizontalBars points={points} /> : <TimeLine points={points} />}
    </section>
  );
}
