import React, { useEffect, useRef, useState } from 'react';
import { MagnifyingGlass, Briefcase, MapPin, Translate, Note, DotsThree, SlidersHorizontal, X, ArrowSquareOut, DownloadSimple, ArrowsClockwise, Clock, CaretRight, Buildings, Circle, Check, WarningCircle } from '@phosphor-icons/react';

import { ARCHIVED_STATUSES, experienceValue, experienceOptions, matchesVisibility, exportFilename, matchesSelected, jobTimestamp, jobHighlights, displayTime } from './jobFilters.js';
import { createAlerts } from './alerts.js';

const logo = company => Object.entries({'BMW':'bmw','Airbus':'airbus','MTU':'mtu','Lufthansa':'lufthansa','N3':'n3'}).find(([name]) => (typeof company === 'string' ? company : '').includes(name))?.[1];
async function api(path, method = 'GET', body) {
  const response = await fetch('/api/' + path, { method, headers: { 'Content-Type': 'application/json' }, ...(body && {body: JSON.stringify(body)}) });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Please check your input.');
  return data;
}
function Brand({company}) { const name = logo(company); return name ? <img className="brand-logo" src={'/logos/' + name + '.png'} alt=""/> : <Buildings size={30}/>; }
function Modal({title, close, error, children}) {
  const ref = useRef();
  useEffect(() => { ref.current.showModal(); }, []);
  return <dialog ref={ref} onCancel={close} onClick={e => {if(e.target === e.currentTarget) close();}}><div className="modal-header"><h2>{title}</h2><button className="icon-button" aria-label="Close dialog" onClick={close}><X size={22}/></button></div>{error && <div className="error" role="alert">{error}</div>}{children}</dialog>;
}
function MultiSelect({label, options, value, onChange}) {
  const ref = useRef();
  useEffect(() => {
    const close = event => {if (!ref.current.contains(event.target)) ref.current.open = false;};
    document.addEventListener('pointerdown', close);
    return () => document.removeEventListener('pointerdown', close);
  }, []);
  return <details className="multi-filter" ref={ref} onKeyDown={event => {if(event.key === 'Escape') {ref.current.open = false;ref.current.querySelector('summary').focus();}}}>
    <summary>{label}<span>{value.length ? value.length + ' selected' : 'All'}</span></summary>
    <div className="multi-options"><button type="button" onClick={() => onChange([])}>Clear filter</button><fieldset><legend>{label}</legend>{options.map(option => <label key={option.value}><input type="checkbox" checked={value.includes(option.value)} onChange={event => onChange(event.target.checked ? [...value, option.value] : value.filter(item => item !== option.value))}/>{option.label}</label>)}</fieldset></div>
  </details>;
}
function JobTimes({job}) {
  const stamp = jobTimestamp(job);
  return <div className="job-times"><Clock size={15}/>{stamp ? <span>{stamp.label} <time dateTime={stamp.value}>{stamp.text}</time></span> : <span>Date/time unavailable</span>}</div>;
}
function JobHighlights({job}) {
  const {industry, skills} = jobHighlights(job);
  return <div className="job-highlights"><span className="industry-badge">Industry: {industry || 'Not stated'}</span>{skills.length ? skills.map(skill => <span className="skill-badge" key={skill}>{skill}</span>) : <span className="muted">Skills not stated</span>}</div>;
}
export function App({initialData = null, initialPage = 'Applications'} = {}) {
  const [data, setData] = useState(initialData), [page, setPage] = useState(initialPage), [query, setQuery] = useState(''), [company, setCompany] = useState([]), [german, setGerman] = useState([]), [years, setYears] = useState([]);
  const [selected, setSelected] = useState(null), [draft, setDraft] = useState({}), [modal, setModal] = useState(''), [error, setError] = useState(''), [toast, setToast] = useState(''), [busy, setBusy] = useState(false);
  const [statusName, setStatusName] = useState(''), [rename, setRename] = useState(''), [schedule, setSchedule] = useState({});
  const [likelyOnly, setLikelyOnly] = useState(false), [showExcluded, setShowExcluded] = useState(false);
  const [checked, setChecked] = useState({}), [bulkStatus, setBulkStatus] = useState('Not interested'), [keywords, setKeywords] = useState('');
  const alerts = useRef(null), loading = useRef(false);
  if (!alerts.current) alerts.current = createAlerts();
  const [alertSettings, setAlertSettings] = useState(() => alerts.current.settings());
  async function reload() {
    if (loading.current) return;
    loading.current = true;
    try {
      const next = await api('state');
      setData(next);
      await alerts.current.process(next.runs, setToast);
    } catch(e) {setError(e.message);}
    finally {loading.current = false;}
  }
  useEffect(() => {setChecked({});}, [page, query, company, german, years, likelyOnly, showExcluded]);
  function toggleJob(job) {
    setChecked(previous => {
      const next = {...previous};
      if (next[job.key]) delete next[job.key]; else next[job.key] = {key:job.key, version:job.version};
      return next;
    });
  }
  useEffect(() => {reload(); const timer = setInterval(reload, 15000); return () => clearInterval(timer);}, []);
  useEffect(() => { if(toast) {const timer = setTimeout(() => setToast(''), 3500); return () => clearTimeout(timer);} }, [toast]);
  async function action(fn, message) {setBusy(true); setError(''); try {await fn(); await reload(); setToast(message);} catch(e) {setError(e.message);} finally {setBusy(false);} }
  function open(job) {setSelected(job); setDraft({status:job.status, notes:job.notes, version:job.version});}
  function navigate(value) {setPage(value); setQuery(''); setCompany([]); setGerman([]); setYears([]);}
  if (!data) return <div className="loading"><ArrowsClockwise size={32}/><h2>{error || 'Opening your workspace…'}</h2><button onClick={reload}>Retry</button></div>;
  const jobs = data.jobs, fresh = jobs.filter(j => j.status === 'New' && !j.excluded_keyword).length;
  const filtered = jobs.filter(j => (!query || [j.title,j.company,j.location,j.notes].join(' ').toLowerCase().includes(query.toLowerCase())) && matchesSelected(j.company, company) && matchesSelected(j.german_required, german) && matchesSelected(experienceValue(j), years) && matchesVisibility(j, showExcluded, likelyOnly)).sort((a,b) => b.total_score - a.total_score);
  const boardStatuses = data.statuses.filter(s => s !== 'New' && !ARCHIVED_STATUSES.includes(s));
  const shown = filtered.filter(job => page === 'Discover' ? job.status === 'New' : boardStatuses.includes(job.status));
  const excludedCount = jobs.filter(job => job.excluded_keyword).length;
  const archived = jobs.filter(job => ARCHIVED_STATUSES.includes(job.status));
  function checkBox(job) {return <input type="checkbox" className="job-select" aria-label={'Select ' + job.title + ' at ' + job.company} checked={Boolean(checked[job.key])} onChange={() => toggleJob(job)}/>;}
  function tags(job) {return <div className="job-tags">{job.likely_interested && <span className="interest-badge">Likely interested</span>}{job.excluded_keyword && <span className="exclusion-badge">Excluded: {job.excluded_keyword}</span>}</div>;}
  async function applyBulk() {
    await action(async () => {
      await api('jobs/bulk-status', 'POST', {jobs:Object.values(checked), status:bulkStatus});
      setChecked({});
    }, 'Selected jobs moved to ' + bulkStatus);
  }
  async function exportSelected() {
    const response = await fetch('/api/export', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({keys:Object.keys(checked), filename:exportFilename()})});
    if (!response.ok) {const result = await response.json();throw new Error(typeof result.detail === 'string' ? result.detail : 'Export failed. Check your selection.');}
    const url = URL.createObjectURL(await response.blob()), link = document.createElement('a');
    link.href = url; link.download = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] || exportFilename();
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const last = data.runs[0];
  function card(job) {return <article className={'job-card ' + (job.likely_interested ? 'likely-interest' : '')} key={job.key} draggable onDragStart={e => e.dataTransfer.setData('text/plain', job.key)}>
    <div className="card-selection">{checkBox(job)}{tags(job)}</div><div className="card-top"><div className="company"><Brand company={job.company}/><span>{job.company}</span></div><button className="icon-button card-menu" aria-label={'Edit ' + job.title + ' at ' + job.company} onClick={() => open(job)}><DotsThree size={24}/></button></div>
    <div className="score">{Math.round(job.total_score || 0)} <small>/ 80</small></div>
    <button className="job-title" onClick={() => open(job)}>{job.title}</button>
    <div className="metadata"><span><MapPin size={16}/>{job.location}</span><span><Briefcase size={16}/>{job.experience_required || 'Not stated'}</span><span><Translate size={17}/>{job.german_required || 'Not stated'} German</span></div>
    <div className="card-note"><Note size={17}/><span>{job.notes || 'Add a note or review the requirements.'}</span></div>
    <JobHighlights job={job}/><JobTimes job={job}/>
  </article>;}
  return <div className="shell">
    <aside><div className="wordmark">Application Studio</div><div className="submark">Job Scout</div><nav>{['Discover','Applications','Sources'].map((name,i) => <button key={name} className={page === name ? 'active' : ''} onClick={() => navigate(name)}>{i === 0 ? <MagnifyingGlass size={21}/> : i === 1 ? <Briefcase size={21}/> : <ArrowsClockwise size={21}/>} {name}{name === 'Discover' && <span className="nav-count">{fresh}</span>}</button>)}</nav>
      <div className="sync"><div><Circle size={10} weight="fill" className={last?.status === 'Failed' ? 'warning' : ''}/>{data.demo ? 'Demo workspace' : last ? last.status : 'Waiting for first scrape'}</div><p>{data.demo ? 'Sample jobs · changes are saved' : last?.finished ? 'Checked ' + displayTime(last.finished) : 'No completed run yet'}</p><button onClick={() => {setSchedule(data.schedule);setModal('schedule');}}><Clock size={14}/>{data.schedule.enabled ? 'Every ' + data.schedule.interval_minutes + ' min' : 'Schedule paused'}<CaretRight size={14}/></button></div>
    </aside>
    <main><header><div className="tabs">{['Discover','Applications'].map(name => <button className={page === name ? 'active' : ''} onClick={() => navigate(name)} key={name}>{name}</button>)}</div><button className="alerts-button" onClick={() => setModal('alerts')}>Result alerts</button><div className="date">{new Date().toLocaleDateString('en-US', {weekday:'long',month:'long',day:'numeric',year:'numeric'})}{data.demo && <span className="demo">Demo data</span>}</div></header>
    <div className="content"><div className="page-heading"><div><h1>{page === 'Applications' ? 'My applications' : page === 'Discover' ? 'Discover opportunities' : 'Your sources'}</h1><p>{page === 'Applications' ? 'Track and manage your engineering job applications.' : page === 'Discover' ? 'Find the right role. Keep the opportunities that matter.' : 'Keep track of collection runs and scheduling.'}</p></div><div className="heading-actions">{page === 'Applications' ? <><button className="primary" onClick={() => navigate('Discover')}><MagnifyingGlass size={19}/>Review new jobs · {fresh}</button><button onClick={() => {setRename('');setStatusName('');setModal('statuses');}}><SlidersHorizontal size={19}/>Customize statuses</button></> : <><button className="primary" disabled={busy || data.requested} onClick={() => action(() => api('scrape','POST'), 'Scrape queued')}><ArrowsClockwise size={18}/>{data.requested ? 'Scrape queued' : 'Check for jobs'}</button></>}</div></div>
    {error && <div className="error" role="alert"><WarningCircle size={20}/>{error}<button aria-label="Dismiss error" className="icon-button" onClick={() => setError('')}><X/></button></div>}
    {page !== 'Sources' ? <><div className="filters"><label className="search"><MagnifyingGlass size={22}/><input aria-label="Search jobs" placeholder="Search jobs, companies or notes..." value={query} onChange={e => setQuery(e.target.value)}/></label><MultiSelect label="Company" value={company} onChange={setCompany} options={[...new Set(jobs.map(j => j.company).filter(Boolean))].sort().map(value => ({value,label:value}))}/><MultiSelect label="German requirement" value={german} onChange={setGerman} options={[...new Set(jobs.map(j => j.german_required || 'Not stated'))].sort().map(value => ({value,label:value}))}/><MultiSelect label="Experience required" value={years} onChange={setYears} options={experienceOptions(jobs)}/></div>
      <div className="filter-options">
        <label><input type="checkbox" checked={likelyOnly} onChange={e => setLikelyOnly(e.target.checked)}/>Likely interested only</label>
        <label><input type="checkbox" checked={showExcluded} onChange={e => setShowExcluded(e.target.checked)}/>Show keyword-excluded jobs ({excludedCount} saved)</label>
        <button onClick={() => {setKeywords(data.title_exclusions.join('\n'));setModal('keywords');}}>Title exclusions</button>
      </div>
      <p className="filter-hint">Experience options use the extracted “Experience required” text exactly. Check any values you want to include.</p>
      {showExcluded && <p className="filter-hint" role="status">{shown.filter(job => job.excluded_keyword).length} keyword-excluded jobs shown on this page; {excludedCount} saved in total. Other search filters and job statuses still apply. Jobs skipped during scraping were not saved and cannot be revealed here.</p>}
      <div className="bulk-toolbar">
        <label><input type="checkbox" aria-label="Select all shown jobs" checked={shown.length > 0 && shown.every(job => checked[job.key])} onChange={e => setChecked(e.target.checked ? Object.fromEntries(shown.slice(0,1000).map(job => [job.key,{key:job.key,version:job.version}])) : {})}/>Select all shown{shown.length > 1000 ? ' (first 1,000)' : ''}</label>
        <span>{Object.keys(checked).length} selected</span>
        <button disabled={busy || !Object.keys(checked).length || Object.keys(checked).length > 1000} onClick={() => action(exportSelected, 'Selected jobs exported')}><DownloadSimple size={18}/>Export selected ({Object.keys(checked).length})</button>
        <select aria-label="Bulk status" value={bulkStatus} onChange={e => setBulkStatus(e.target.value)}>{data.statuses.map(status => <option key={status}>{status}</option>)}</select>
        <button disabled={busy || !Object.keys(checked).length || Object.keys(checked).length > 1000} onClick={applyBulk}>Assign status</button>
        {Object.keys(checked).length > 0 && <button onClick={() => setChecked({})}>Clear selection</button>}
      </div>
      {page === 'Applications' ? <div className="board">{boardStatuses.map((status,i) => <section className="column" key={status} onDragOver={e => e.preventDefault()} onDrop={e => {e.preventDefault();const job = jobs.find(j => j.key === e.dataTransfer.getData('text/plain'));if(job) action(() => api('jobs/'+job.key,'PATCH',{status,notes:job.notes,version:job.version}), 'Moved to '+status);}}><div className={'column-heading color-' + i%3}><h2><Circle size={14} weight="fill"/>{status}<span>{filtered.filter(j => j.status === status).length}</span></h2><p>{i === 0 ? 'Interesting opportunities to consider' : i === 1 ? 'Applications submitted' : i === 2 ? 'Ongoing interview process' : 'Your custom stage'}</p></div>{filtered.filter(j => j.status === status).map(card)}{!filtered.some(j => j.status === status) && <div className="empty-column">No jobs here yet.<br/>Move a job here to get started.</div>}</section>)}</div> : <><div className="discovery-summary"><span>{filtered.filter(j=>j.status==='New').length} new opportunities</span><small>Scores use your existing 0–80 ranking. Unknown requirements are not assumed to be a match.</small></div><div className="discover-list">{filtered.filter(j=>j.status==='New').map(job => <div className={'discover-row ' + (job.likely_interested ? 'likely-interest' : '')} key={job.key}>{checkBox(job)}<Brand company={job.company}/><div><button className="job-title" onClick={() => open(job)}>{job.title}</button><p>{job.company} · {job.location}</p>{tags(job)}<small>{job.experience_required || 'Not stated'} experience · {job.german_required || 'Not stated'} German</small><JobHighlights job={job}/><JobTimes job={job}/></div><strong>{Math.round(job.total_score || 0)} <small>/80</small></strong><button onClick={() => open(job)}>Review<CaretRight size={16}/></button></div>)}{!filtered.some(j=>j.status==='New') && <div className="empty-column">No new jobs match these filters.</div>}</div></>}
      <details className="archive"><summary>Not interested &amp; Not fit ({archived.length})</summary><p className="filter-hint">All archived jobs, independent of the filters above. Open a job to restore it to any active status.</p>{archived.map(job => <div className="archive-row" key={job.key}>{checkBox(job)}<button onClick={() => open(job)}>{job.title} · {job.company}</button><span>{job.status}</span><JobTimes job={job}/></div>)}</details>
    </> : <div className="sources"><div className="source-toolbar"><p>{data.demo ? 'Live scraping is disabled in this demo. Docker runs your real scraper locally.' : 'Company adapters retain their source-specific delays. LinkedIn / Indeed are optional.'}</p><button onClick={()=>{setSchedule(data.schedule);setModal('schedule');}}><Clock size={18}/>Schedule settings</button></div>{data.runs.length ? data.runs.map(r=><section className="run" key={r.id}><h3>{r.status} <small>{new Date(r.started).toLocaleString()}</small></h3><p>{r.details.added ?? 0} new jobs · {r.details.total ?? 0} retained</p>{r.details.error && <p className="warning">{r.details.error}</p>}{r.details.sites?.map(s=><div className="site-row" key={s.source_site}><span>{s.source_site}</span><span>{s.status}</span><span>{s.after_titles} jobs</span>{s.errors?.length>0 && <small>{s.errors.join('; ')}</small>}</div>)}</section>) : <div className="empty-column"><ArrowsClockwise size={32}/><h3>No collection runs yet</h3><p>Your run history will appear here when the worker starts.</p></div>}</div>}
    <footer><span>{filtered.length} jobs in your workspace</span><span>Changes saved to your database</span></footer></div></main>
    {selected && <Modal error={error} title="Job details" close={()=>setSelected(null)}><div className="detail-company"><Brand company={selected.company}/>{selected.company}<span>{Math.round(selected.total_score || 0)} / 80</span></div><h2 className="detail-title">{selected.title}</h2><p className="muted">{selected.location} · {selected.source_site}</p>{tags(selected)}<JobHighlights job={selected}/><JobTimes job={selected}/><div className="requirements"><div><small>Experience</small><strong>{selected.experience_required || 'Not stated'}</strong><p>{selected.experience_evidence || 'No matching evidence extracted.'}</p></div><div><small>German</small><strong>{selected.german_required || 'Not stated'}</strong><p>{selected.german_evidence || 'No matching evidence extracted.'}</p></div></div><details><summary>Full job description</summary><div className="description">{selected.description_blocks?.length ? selected.description_blocks.map((block,i) => block.kind === 'heading' ? <h3 key={i}>{block.text}</h3> : block.kind === 'list' ? <ul key={i}>{block.items.map((text,j) => <li key={j}>{text}</li>)}</ul> : <p key={i}>{block.text}</p>) : <p>{selected.description || 'No description available.'}</p>}</div></details><label className="field">Application status<select value={draft.status} onChange={e=>setDraft({...draft,status:e.target.value})}>{data.statuses.map(s=><option key={s}>{s}</option>)}</select></label><label className="field">Your notes<textarea rows={4} value={draft.notes} onChange={e=>setDraft({...draft,notes:e.target.value})} placeholder="Next steps, interview details, questions…"/></label><div className="modal-actions">{/^https?:\/\//i.test(selected.job_url || '') && <a className="button" href={selected.job_url} target="_blank" rel="noreferrer">Original posting<ArrowSquareOut size={18}/></a>}<button className="primary" disabled={busy} onClick={()=>action(async()=>{await api('jobs/'+selected.key,'PATCH',draft);setSelected(null);},'Changes saved')}><Check size={18}/>Save changes</button></div></Modal>}
    {modal === 'statuses' && <Modal error={error} title="Customize statuses" close={()=>setModal('')}><p className="muted">Add a stage, or rename one. Existing jobs move with the renamed stage.</p><div className="status-list">{data.statuses.map(s=><div key={s}><span>{s}</span>{!['New','Not interested','Not fit'].includes(s) && <button onClick={()=>{setRename(s);setStatusName(s);}}>Rename</button>}</div>)}</div><form onSubmit={e=>{e.preventDefault();action(async()=>{await api('statuses','POST',{name:statusName,old:rename||null});setStatusName('');setRename('');},'Statuses updated');}}><label className="field">{rename ? 'Rename '+rename : 'New status'}<input required maxLength={80} value={statusName} onChange={e=>setStatusName(e.target.value)} placeholder="e.g. Offer received"/></label><div className="modal-actions">{rename && <button type="button" onClick={()=>{setRename('');setStatusName('');}}>Cancel rename</button>}<button disabled={busy} className="primary">{rename ? 'Save name' : 'Add status'}</button></div></form></Modal>}
    {modal === 'schedule' && <Modal error={error} title="Scraping schedule" close={()=>setModal('')}><form onSubmit={e=>{e.preventDefault();action(async()=>{await api('schedule','PUT',schedule);setModal('');},'Schedule saved');}}><label className="check-field"><input type="checkbox" checked={schedule.enabled} onChange={e=>setSchedule({...schedule,enabled:e.target.checked})}/>Enable scheduled scraping</label><label className="field">Interval (minutes)<input type="number" min="30" max="1440" required value={schedule.interval_minutes} onChange={e=>setSchedule({...schedule,interval_minutes:Number(e.target.value)})}/></label><label className="check-field"><input type="checkbox" checked={schedule.include_ls} onChange={e=>setSchedule({...schedule,include_ls:e.target.checked})}/>Include LinkedIn / Indeed searches</label><p className="muted">Your computer must be awake with Docker running. New runs wait for the previous one to finish. Job boards retain their existing pacing.</p><button disabled={busy} className="primary">Save schedule</button></form></Modal>}
    {modal === 'keywords' && <Modal error={error} title="Title exclusions" close={() => setModal('')}><p className="muted">One literal keyword or phrase per line. Matches are case-insensitive and limited to titles. Existing jobs are hidden, not deleted; remove a keyword to show them again. New matching jobs are skipped during collection.</p><form onSubmit={e => {e.preventDefault();action(async () => {await api('title-exclusions','PUT',{keywords:keywords.split('\n').map(word => word.trim()).filter(Boolean)});setModal('');},'Title exclusions saved');}}><label className="field">Excluded title keywords<textarea rows={12} value={keywords} onChange={e => setKeywords(e.target.value)}/></label><button className="primary" disabled={busy}>Save exclusions</button></form></Modal>}
    {modal === 'alerts' && <Modal error={error} title="Result alerts" close={() => setModal('')}><p className="muted">Get an alert when a completed scrape adds new jobs. Keep Job Scout open in a browser tab. Notifications and audio depend on browser and OS permissions.</p><label className="check-field"><input type="checkbox" checked={alertSettings.sound} onChange={e => {const enabled=e.target.checked;action(async () => setAlertSettings(await alerts.current.enableSound(enabled)),enabled ? 'Sound enabled' : 'Sound disabled');}}/>Beep on new results</label><button onClick={() => action(async () => setAlertSettings(await alerts.current.enableSound(true)), 'Sound enabled for this tab')}>Enable / test sound</button><p className="filter-hint">After reopening the page, click this button once to enable audio for this tab.</p><label className="check-field"><input type="checkbox" checked={alertSettings.desktop} onChange={e => {const enabled=e.target.checked;action(async () => setAlertSettings(await alerts.current.enableDesktop(enabled)),enabled ? 'Desktop notifications enabled' : 'Desktop notifications disabled');}}/>Desktop notifications</label><p className="filter-hint">No alerts for old results on page load or runs with no new jobs. With Web Locks support, only one open tab alerts per run.</p></Modal>}
    {toast && <div className="toast" role="status"><Check size={18}/>{toast}</div>}
  </div>;
}
