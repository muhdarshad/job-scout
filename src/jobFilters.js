export const ARCHIVED_STATUSES = ['Not interested', 'Not fit'];
export function matchesExperience(job, value) {
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
