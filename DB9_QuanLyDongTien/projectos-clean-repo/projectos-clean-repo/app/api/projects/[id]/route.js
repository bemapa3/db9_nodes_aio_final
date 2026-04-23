import { prisma } from '@/lib/prisma';
import { fail, ok } from '@/lib/helpers';

export async function PATCH(req, { params }) {
  try {
    const body = await req.json();
    const data = await prisma.project.update({
      where: { id: params.id },
      data: {
        startDate: body.startDate ? new Date(body.startDate) : undefined,
        endDate: body.endDate ? new Date(body.endDate) : undefined,
      },
    });
    return ok(data);
  } catch {
    return fail('Không cập nhật được dự án');
  }
}
