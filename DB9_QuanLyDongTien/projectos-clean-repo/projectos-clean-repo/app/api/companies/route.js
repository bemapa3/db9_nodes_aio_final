import { prisma } from '@/lib/prisma';
import { fail, ok } from '@/lib/helpers';

export async function GET() {
  const data = await prisma.company.findMany({ orderBy: { createdAt: 'desc' } });
  return ok(data);
}

export async function POST(req) {
  try {
    const body = await req.json();
    const data = await prisma.company.create({ data: body });
    return ok(data, 201);
  } catch {
    return fail('Không tạo được công ty');
  }
}
