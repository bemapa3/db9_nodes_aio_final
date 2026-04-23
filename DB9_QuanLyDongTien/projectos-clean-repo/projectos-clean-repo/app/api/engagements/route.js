import { prisma } from '@/lib/prisma';
import { ok } from '@/lib/helpers';

export async function GET() {
  const data = await prisma.engagement.findMany({ orderBy: { startDate: 'asc' } });
  return ok(data);
}
