import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { ActivityDay } from '../types/api';

const axis = { fontSize: 11, fill: 'var(--muted)' };

export function ActivityChart({ data, height = 240 }: { data: ActivityDay[]; height?: number }) {
  const rows = data.map((d) => ({ ...d, label: d.date.slice(5) }));
  return (
    <div style={{ height }} role="img" aria-label="Runs per day, successful versus failed">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis dataKey="label" tick={axis} tickLine={false} axisLine={{ stroke: 'var(--border)' }} interval="preserveStartEnd" />
          <YAxis allowDecimals={false} tick={axis} tickLine={false} axisLine={false} />
          <Tooltip
            cursor={{ fill: 'var(--soft)' }}
            contentStyle={{ background: 'var(--card)', border: '1.5px solid var(--border-strong)', borderRadius: 6, fontSize: 12 }}
            labelStyle={{ color: 'var(--fg)', fontWeight: 600 }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="success" name="Success" stackId="runs" fill="var(--accent)" stroke="var(--border-strong)" strokeWidth={1} />
          <Bar dataKey="failed" name="Failed / timed out" stackId="runs" fill="var(--danger)" stroke="var(--border-strong)" strokeWidth={1} />
          <Bar dataKey="running" name="Running" stackId="runs" fill="var(--muted)" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
