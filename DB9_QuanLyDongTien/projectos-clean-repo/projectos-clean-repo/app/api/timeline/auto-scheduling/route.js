import { prisma } from '@/lib/prisma';
import { addDays, diffDays, ok, onlyDate } from '@/lib/helpers';

export async function POST(req) {
  const body = await req.json();
  const threshold = body.dailyThreshold || 85;
  const projects = await prisma.project.findMany({ orderBy: { startDate: 'asc' } });
  const suggestions = [];
  for (const p of projects) {
    const start = p.startDate;
    const end = p.endDate || p.startDate;
    const duration = Math.max(1, diffDays(start, end) + 1);
    if (p.priority === 'urgent') continue;
    const nextStart = addDays(start, 2);
    const nextEnd = addDays(nextStart, duration - 1);
    suggestions.push({
      id: `sg-${p.id}`,
      projectId: p.id,
      reason: `Dời ${p.name} để giảm quá tải (ngưỡng ${threshold}%)`,
      currentStartDate: onlyDate(start.toISOString()),
      currentEndDate: onlyDate(end.toISOString()),
      suggestedStartDate: onlyDate(nextStart.toISOString()),
      suggestedEndDate: onlyDate(nextEnd.toISOString()),
      confidenceScore: 82,
      impactScore: 74,
      status: 'proposed'
    });
  }
  return ok({ suggestions });
}
