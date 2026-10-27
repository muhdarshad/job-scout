export const ARCHIVED_STATUSES = ['Not interested', 'Not fit'];
export function matchesExperience(job, value) {
  if (Array.isArray(value)) return !value.length || value.some(item => matchesExperience(job, item));
  if (!value) return true;
  const raw = job.experience_min_years;
  const numeric = raw !== null && raw !== undefined && raw !== '' && Number.isFinite(Number(raw));
  if (value === 'unknown') return !numeric;
  if (!numeric) return false;
  return value === '5+' ? Number(raw) >= 5 : Number(raw) === Number(value);
}
export function completedRunsAfter(runs, previous) {
  return runs.filter(run => run.finished && ['Complete', 'Partial'].includes(run.status) && run.id > previous)
    .sort((a, b) => a.id - b.id);
}
export function displayTime(value) {
  if (!value || !Number.isFinite(new Date(value).getTime())) return 'Not recorded';
  return new Date(value).toLocaleString(undefined, {dateStyle:'medium', timeStyle:'short'});
}

export function matchesSelected(value, selected) {
  return !selected.length || selected.includes(value || 'Not stated');
}
export function jobTimestamp(job) {
  for (const [label, raw] of [['Posted', job.posted_at], ['Posted', job.date_posted], ['Added', job.first_seen]]) {
    if (typeof raw !== 'string' || !/T\d{2}:\d{2}| \d{2}:\d{2}/.test(raw)) continue;
    const date = new Date(raw);
    if (Number.isFinite(date.getTime())) return {label, value:raw, text:displayTime(raw)};
  }
  return null;
}
export const experienceValue = job => String(job.experience_required || '').trim() || 'Not stated';
export function experienceOptions(jobs) {
  return [...new Set(jobs.map(experienceValue))].sort((a,b) => a.localeCompare(b, undefined, {numeric:true})).map(value => ({value,label:value}));
}
export function matchesVisibility(job, showExcluded, likelyOnly) {
  if (job.excluded_keyword) return showExcluded;
  return !likelyOnly || job.likely_interested;
}
export function exportFilename(date = new Date()) {
  const pad = value => String(value).padStart(2, '0');
  return 'jobscope_' + pad(date.getHours()) + pad(date.getMinutes()) + '_' + pad(date.getDate()) + pad(date.getMonth() + 1) + String(date.getFullYear()).slice(-2) + '.xlsx';
}
export function jobHighlights(job) {
  const parts = value => (Array.isArray(value) ? value : typeof value === 'string' ? value.split(/[,;|]/) : [])
    .filter(value => typeof value === 'string').map(value => value.trim()).filter(Boolean);
  const skills = [...new Map([...parts(job.matched_skills), ...parts(job.skills)].map(skill => [skill.toLowerCase(),skill])).values()];
  return {industry:parts(job.company_industry).join(' · '), skills};
}
