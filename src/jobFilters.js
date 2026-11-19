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

// ---- Grouped filter values -------------------------------------------------------------------
// Raw extracted strings are free text and produce dozens of near-duplicates, so the filters group
// them into a few stable bins. Unknown stays separate from "none required".
export const EXPERIENCE_BINS = ['Not stated', 'Optional / qualitative only', 'Up to 1 year', '2 years', '3 years', '4 years', '5+ years'];
export const GERMAN_BINS = ['Not stated', 'Not required', 'Preferred only', 'Level unspecified', 'Basic (A1–A2)', 'Intermediate (B1–B2 / good)', 'Advanced (C1+ / fluent)'];
export const SOURCE_BINS = ['CS', 'LS'];
export const SOURCE_LABELS = {CS: 'Company sites (CS)', LS: 'Job boards (LS)'};

const isMissing = value => !String(value ?? '').trim() || String(value).trim().toLowerCase() === 'not stated';

export function experienceBin(job) {
  const raw = job.experience_min_years;
  const years = raw === null || raw === undefined || raw === '' ? NaN : Number(raw);
  if (Number.isFinite(years)) return years >= 5 ? '5+ years' : years >= 4 ? '4 years' : years >= 3 ? '3 years' : years >= 2 ? '2 years' : 'Up to 1 year';
  return isMissing(job.experience_required) ? 'Not stated' : 'Optional / qualitative only';
}

const GERMAN_LEVELS = [
  [/\b(?:c1|c2|native|muttersprach|business fluent|fluent|very good)\b/i, 'Advanced (C1+ / fluent)'],
  [/\b(?:b1|b2|good|proficient|conversational)\b/i, 'Intermediate (B1–B2 / good)'],
  [/\b(?:a1|a2|basic)\b/i, 'Basic (A1–A2)'],
];
export function germanBin(job) {
  const level = String(job.german_required ?? ''), statuses = String(job.german_requirement ?? '').toLowerCase().split('|').map(part => part.trim()).filter(Boolean);
  if (isMissing(level)) return 'Not stated';
  const found = GERMAN_LEVELS.find(([pattern]) => pattern.test(level));
  if (statuses.length && statuses.every(status => status === 'not required')) return 'Not required';
  if (statuses.length && statuses.every(status => status === 'preferred')) return 'Preferred only';
  return found ? found[1] : 'Level unspecified';
}

export function sourceType(job) {
  const site = String(job.source_site ?? '').trim().toUpperCase();
  if (site.startsWith('LS')) return 'LS';
  if (site.startsWith('CS')) return 'CS';
  return ['CS', 'LS'].includes(String(job.source ?? '').toUpperCase()) ? String(job.source).toUpperCase() : 'CS';
}

// Options come only from the jobs in `scope` (the jobs visible on the current page), in a fixed order, with counts.
export function binOptions(scope, bin, order, labels = {}) {
  const counts = new Map();
  for (const job of scope) counts.set(bin(job), (counts.get(bin(job)) || 0) + 1);
  return order.filter(value => counts.has(value)).map(value => ({value, label: (labels[value] || value) + ' · ' + counts.get(value)}));
}

export function applyFilters(jobs, {query = '', company = [], german = [], years = [], source = [], showExcluded = false, likelyOnly = false} = {}) {
  const needle = query.toLowerCase();
  return jobs.filter(job => (!needle || [job.title, job.company, job.location, job.notes].join(' ').toLowerCase().includes(needle))
    && matchesSelected(job.company, company) && (!german.length || german.includes(germanBin(job)))
    && (!years.length || years.includes(experienceBin(job))) && (!source.length || source.includes(sourceType(job)))
    && matchesVisibility(job, showExcluded, likelyOnly));
}
