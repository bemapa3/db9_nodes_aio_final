export function ok(data, status = 200) {
  return Response.json({ success: true, data }, { status });
}

export function fail(message, status = 400) {
  return Response.json({ success: false, error: { message } }, { status });
}

export function onlyDate(value) {
  return value ? String(value).slice(0, 10) : '';
}

export function addDays(date, days) {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

export function diffDays(a, b) {
  return Math.round((b.getTime() - a.getTime()) / 86400000);
}
