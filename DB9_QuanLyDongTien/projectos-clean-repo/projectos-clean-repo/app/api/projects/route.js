import { prisma } from '@/lib/prisma';
import { ok } from '@/lib/helpers';

export async function GET() {
  const data = await prisma.project.findMany({ orderBy: { startDate: 'asc' } });
  return ok(data);
}
