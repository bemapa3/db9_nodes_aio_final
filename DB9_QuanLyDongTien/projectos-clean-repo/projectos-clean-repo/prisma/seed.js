const { PrismaClient } = require('@prisma/client');
const prisma = new PrismaClient();

async function main() {
  await prisma.backupRun.deleteMany();
  await prisma.backupPolicy.deleteMany();
  await prisma.backupTarget.deleteMany();
  await prisma.scheduleSuggestion.deleteMany();
  await prisma.payment.deleteMany();
  await prisma.project.deleteMany();
  await prisma.engagement.deleteMany();
  await prisma.company.deleteMany();

  const abc = await prisma.company.create({ data: { companyName: 'Công ty ABC', legalName: 'ABC Co., Ltd', defaultCurrency: 'VND', paymentTermsDays: 30 } });
  const xyz = await prisma.company.create({ data: { companyName: 'Studio XYZ', legalName: 'XYZ Studio', defaultCurrency: 'USD', paymentTermsDays: 15 } });

  await prisma.engagement.createMany({ data: [
    { companyId: abc.id, engagementName: 'Thiết kế part-time 6 tháng', fixedAmount: 20000000, workloadPercent: 35, paymentCycle: 'monthly', startDate: new Date('2026-04-01'), endDate: new Date('2026-09-30') },
    { companyId: xyz.id, engagementName: 'Retainer nội dung', fixedAmount: 1200, workloadPercent: 20, paymentCycle: 'monthly', startDate: new Date('2026-04-01'), endDate: new Date('2026-08-31') }
  ]});

  const p1 = await prisma.project.create({ data: { companyId: abc.id, name: 'Landing page chiến dịch tháng 4', priority: 'urgent', startDate: new Date('2026-04-22'), endDate: new Date('2026-04-29'), contractValue: 15000000, billingMode: 'extra_project' } });
  const p2 = await prisma.project.create({ data: { companyId: abc.id, name: 'Banner social tuần lễ sale', priority: 'high', startDate: new Date('2026-04-24'), endDate: new Date('2026-05-02'), contractValue: 0, billingMode: 'included_in_retainer' } });
  const p3 = await prisma.project.create({ data: { companyId: xyz.id, name: 'Bộ bài viết SEO tháng 5', priority: 'medium', startDate: new Date('2026-04-28'), endDate: new Date('2026-05-12'), contractValue: 800, billingMode: 'extra_project' } });

  await prisma.payment.createMany({ data: [
    { sourceType: 'project', sourceId: p1.id, gross: 10500000, withheldTax: 1050000, userTax: 525000, companyTax: 525000, net: 9975000, date: new Date('2026-04-23') },
    { sourceType: 'engagement', sourceId: abc.id, gross: 20000000, withheldTax: 2000000, userTax: 1000000, companyTax: 1000000, net: 19000000, date: new Date('2026-04-05') }
  ]});

  const target = await prisma.backupTarget.create({ data: { targetName: 'Ổ D local', targetType: 'local', rootPath: 'D:/ProjectVault/Backups', isDefault: true } });
  await prisma.backupPolicy.create({ data: { backupTargetId: target.id, policyName: 'Backup weekly', frequency: 'weekly', keepLastN: 12 } });
  await prisma.backupRun.create({ data: { backupTargetId: target.id, runType: 'manual', status: 'success', backupLabel: 'Bản test đầu tiên', archivePath: 'D:/ProjectVault/Backups/backup-1.zip' } });
}

main().finally(() => prisma.$disconnect());
