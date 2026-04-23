import { prisma } from '@/lib/prisma';
import { fail, ok } from '@/lib/helpers';

export async function GET() {
  return ok(await prisma.backupPolicy.findMany({ orderBy: { createdAt: 'desc' } }));
}

export async function POST(req) {
  try {
    const body = await req.json();
    const data = await prisma.backupPolicy.create({ data: body });
    return ok(data, 201);
  } catch {
    return fail('Không tạo được backup policy');
  }
}
