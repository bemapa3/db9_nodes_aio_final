import { ok } from '@/lib/helpers';

export async function POST(req) {
  const body = await req.json();
  const context = body.context || {};
  const topProject = (context.projects || [])[0];
  const overloadDays = context.overloadDays || [];
  const actions = [];
  let reply = 'Hôm nay mày nên kiểm tra deadline và payment trước.';

  if (body.message?.toLowerCase().includes('tối ưu') || body.message?.toLowerCase().includes('reschedule')) {
    if (topProject) {
      actions.push({
        type: 'reschedule_project',
        projectId: topProject.id,
        nextStartDate: topProject.startDate,
        nextEndDate: topProject.endDate,
      });
      reply = `Tao đã tạo preview tối ưu timeline. Project ưu tiên xem trước: ${topProject.name}.`;
    }
  } else if (overloadDays.length > 0) {
    reply = `Hôm nay mày nên xử lý việc gần deadline trước. Hiện có ${overloadDays.length} ngày quá tải cần chú ý.`;
  }

  return ok({ reply, actions });
}
