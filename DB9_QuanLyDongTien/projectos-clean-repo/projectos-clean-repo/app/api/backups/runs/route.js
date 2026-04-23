import { prisma } from '@/lib/prisma';
import { ok } from '@/lib/helpers';

export async function GET() {
  return ok(await prisma.backupRun.findMany({ orderBy: { createdAt: 'desc' } }));
}
