export function selectedLinks(jobs, checked) {
  const seen = new Set();
  return jobs.filter(job => checked[job.key]).flatMap(job => {
    try {
      const url = new URL(job.job_url);
      if (!['http:','https:'].includes(url.protocol) || seen.has(url.href)) return [];
      seen.add(url.href);
      return [{url:url.href,title:job.title || 'Original job posting'}];
    } catch {return [];}
  });
}
