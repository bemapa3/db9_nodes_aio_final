import { prisma } from '@/lib/prisma';
import { addDays, diffDays, ok, onlyDate } from '@/lib/helpers';

export async function GET(req) {
  const { searchParams } = new URL(req.url);
  const startDate = new Date(searchParams.get('startDate'));
  const endDate = new Date(searchParams.get('endDate'));
  const projects = await prisma.project.findMany({ orderBy: { startDate: 'asc' } });
  const engagements = await prisma.engagement.findMany({ orderBy: { startDate: 'asc' } });

  const totalDays = Math.max(1, diffDays(startDate, endDate) + 1);
  const dailySeries = [];
  for (let i = 0; i < totalDays; i++) {
    const day = addDays(startDate, i);
    const key = onlyDate(day.toISOString());
    let load = 0;
    for (const e of engagements) {
      if (key >= onlyDate(e.startDate.toISOString()) && key <= onlyDate((e.endDate || e.startDate).toISOString())) load += e.workloadPercent;
    }
    for (const p of projects) {
      const pStart = onlyDate(p.startDate.toISOString());
      const pEnd = onlyDate((p.endDate || p.startDate).toISOString());
      if (key >= pStart && key <= pEnd) {
        const weight = p.priority === 'urgent' ? 40 : p.priority === 'high' ? 30 : p.priority === 'medium' ? 20 : 10;
        const span = Math.max(1, diffDays(new Date(`${pStart}T00:00:00`), new Date(`${pEnd}T00:00:00`)) + 1);
        load += weight / span;
      }
    }
    dailySeries.push({ date: key, load: Math.round(load * 100) / 100, status: load >= 100 ? 'critical' : load >= 75 ? 'warning' : load <= 20 ? 'low' : 'normal', isToday: false });
  }

  const conflicts = dailySeries.filter((d) => d.status === 'critical').map((d) => ({ summary: `Quá tải ngày ${d.date}`, details: 'Tổng tải vượt ngưỡng an toàn', severity: 'high' }));
  return ok({ dailySeries, projects, engagements, conflicts });
}
