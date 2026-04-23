import { prisma } from '@/lib/prisma';
import { fail, ok } from '@/lib/helpers';

export async function POST(req) {
  try {
    const body = await req.json();
    const data = await prisma.backupRun.create({
      data: {
        backupTargetId: body.backupTargetId,
        runType: body.runType || 'manual',
        status: 'success',
        backupLabel: body.backupLabel || null,
        archivePath: `mock://${Date.now()}.zip`
      }
    });
    return ok(data, 201);
  } catch {
    return fail('Không chạy được backup');
  }
}
