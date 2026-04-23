import { prisma } from '@/lib/prisma';
import { ok } from '@/lib/helpers';

export async function GET() {
  const payments = await prisma.payment.findMany({ orderBy: { date: 'desc' } });
  const projectPayments = payments.filter((p) => p.sourceType === 'project');
  const engagementPayments = payments.filter((p) => p.sourceType === 'engagement');
  const summary = {
    totalProjectGross: projectPayments.reduce((s, p) => s + p.gross, 0),
    totalEngagementGross: engagementPayments.reduce((s, p) => s + p.gross, 0),
    totalWithheldTax: payments.reduce((s, p) => s + p.withheldTax, 0),
    totalNetReceived: payments.reduce((s, p) => s + p.net, 0),
    totalToolExpense: 0,
  };
  return ok({ summary, details: { projectPayments, engagementPayments } });
}
