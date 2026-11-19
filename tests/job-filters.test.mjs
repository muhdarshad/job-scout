import test from 'node:test';
import assert from 'node:assert/strict';
import { matchesExperience, completedRunsAfter, ARCHIVED_STATUSES, displayTime } from '../src/jobFilters.js';

test('minimum experience is an exact requirement bucket, with a 5+ bucket', () => {
  assert.equal(matchesExperience({experience_min_years:2}, '2'), true);
  assert.equal(matchesExperience({experience_min_years:1}, '2'), false);
  assert.equal(matchesExperience({experience_min_years:3}, '2'), false);
  assert.equal(matchesExperience({experience_min_years:7}, '5+'), true);
  assert.equal(matchesExperience({experience_min_years:4}, '5+'), false);
  assert.equal(matchesExperience({experience_min_years:0}, '0'), true);
});
test('unknown requirements are never treated as zero', () => {
  for (const value of [null, undefined, '', 'Not stated']) {
    assert.equal(matchesExperience({experience_min_years:value}, '0'), false);
    assert.equal(matchesExperience({experience_min_years:value}, 'unknown'), true);
  }
  assert.equal(matchesExperience({experience_min_years:2}, 'unknown'), false);
  assert.equal(matchesExperience({}, ''), true);
});
test('only completed successful or partial runs become notification candidates', () => {
  const runs = [
    {id:4,status:'Running'}, {id:3,status:'Failed',finished:'yes'},
    {id:2,status:'Partial',finished:'yes'}, {id:1,status:'Complete',finished:'yes'}
  ];
  assert.deepEqual(completedRunsAfter(runs,1).map(r=>r.id), [2]);
  assert.deepEqual(completedRunsAfter(runs,2), []);
});
test('both rejected categories share the archive, missing timestamps remain honest', () => {
  assert.deepEqual(ARCHIVED_STATUSES, ['Not interested','Not fit']);
  assert.equal(displayTime(null),'Not recorded');
  assert.equal(displayTime('invalid'),'Not recorded');
});

import {matchesSelected, jobTimestamp, jobHighlights} from '../src/jobFilters.js';
test('checkbox filters match any selected value and combine independently', () => {
  assert.equal(matchesSelected('BMW', ['BMW','Airbus']), true);
  assert.equal(matchesSelected('MTU', ['BMW','Airbus']), false);
  assert.equal(matchesSelected(null, ['Not stated']), true);
  assert.equal(matchesSelected('MTU', []), true);
  assert.equal(matchesExperience({experience_min_years:2}, ['1','2']), true);
  assert.equal(matchesExperience({experience_min_years:3}, ['1','2']), false);
  assert.equal(matchesExperience({}, ['unknown','0']), true);
  assert.equal(matchesExperience({}, []), true);
});
test('one timestamp prefers publication and falls back to first database entry', () => {
  const added = '2026-10-26T14:40:00Z';
  const posted = '2026-10-25T10:00:00Z';
  assert.equal(jobTimestamp({posted_at:posted,first_seen:added}).value, posted);
  const date = jobTimestamp({date_posted:'2026-10-25',first_seen:added});
  assert.equal(date.label, 'Added');
  assert.equal(date.text, displayTime(added));
  for (const value of ['',null,'Not recorded','Yesterday','invalid']) {
    assert.equal(jobTimestamp({posted_at:value,date_posted:value,first_seen:added}).label,'Added');
    assert.equal(jobTimestamp({posted_at:value,first_seen:added}).value,added);
  }
  assert.equal(jobTimestamp({}),null);
});
test('overview highlights source industry and deduplicated extracted skills', () => {
  assert.deepEqual(jobHighlights({company_industry:'Aviation',matched_skills:['SQL','Python'],skills:'SQL, Excel'}),{industry:'Aviation',skills:['SQL','Python','Excel']});
  assert.deepEqual(jobHighlights({}),{industry:'',skills:[]});
});

import {experienceValue, experienceOptions, matchesVisibility, exportFilename} from '../src/jobFilters.js';
test('experience filter uses exact extracted text including qualitative values', () => {
  const jobs = [{experience_required:'Mehrjährige Erfahrung'},{experience_required:'3+ years'}, {}, {experience_required:'Mehrjährige Erfahrung'}];
  assert.equal(experienceOptions(jobs).length,3);
  assert.equal(matchesSelected(experienceValue(jobs[0]),['Mehrjährige Erfahrung','3+ years']),true);
  assert.equal(matchesSelected(experienceValue(jobs[2]),['Mehrjährige Erfahrung']),false);
  assert.equal(experienceValue({experience_required:'  '}),'Not stated');
});
test('show excluded takes precedence over likely-only while normal jobs retain filtering', () => {
  assert.equal(matchesVisibility({excluded_keyword:'postbote'},true,true),true);
  assert.equal(matchesVisibility({excluded_keyword:'postbote'},false,false),false);
  assert.equal(matchesVisibility({likely_interested:false},true,true),false);
  assert.equal(matchesVisibility({likely_interested:true},false,true),true);
});
test('filename uses local HHmm and ddMMyy and publication requires a real time', () => {
  assert.equal(exportFilename(new Date(2026,9,27,13,45)),'jobscope_1345_271026.xlsx');
  assert.equal(jobTimestamp({posted_at:'2026-10-25',first_seen:'2026-10-26T14:40:00Z'}).label,'Added');
  assert.equal(jobTimestamp({posted_at:'bad',date_posted:'2026-10-25',first_seen:'2026-10-26T14:40:00Z'}).value,'2026-10-26T14:40:00Z');
});

import {experienceBin, germanBin, sourceType, binOptions, applyFilters, EXPERIENCE_BINS, GERMAN_BINS, SOURCE_BINS, SOURCE_LABELS} from '../src/jobFilters.js';
test('experience values collapse into a few bins and unknown is never zero', () => {
  assert.equal(experienceBin({}), 'Not stated');
  assert.equal(experienceBin({experience_required:'not stated', experience_min_years:null}), 'Not stated');
  assert.equal(experienceBin({experience_required:'Mehrjährige Erfahrung', experience_min_years:null}), 'Optional / qualitative only');
  assert.equal(experienceBin({experience_min_years:0}), 'Up to 1 year');
  assert.equal(experienceBin({experience_min_years:1}), 'Up to 1 year');
  assert.equal(experienceBin({experience_min_years:3}), '3 years');
  assert.equal(experienceBin({experience_min_years:12}), '5+ years');
});
test('German values group by level; preferred and not-required stay separate', () => {
  assert.equal(germanBin({}), 'Not stated');
  assert.equal(germanBin({german_required:'not stated'}), 'Not stated');
  assert.equal(germanBin({german_required:'fluent', german_requirement:'required'}), 'Advanced (C1+ / fluent)');
  assert.equal(germanBin({german_required:'B2 | C1', german_requirement:'required | required'}), 'Advanced (C1+ / fluent)');
  assert.equal(germanBin({german_required:'B2', german_requirement:'stated'}), 'Intermediate (B1–B2 / good)');
  assert.equal(germanBin({german_required:'A2', german_requirement:'required'}), 'Basic (A1–A2)');
  assert.equal(germanBin({german_required:'fluent', german_requirement:'preferred'}), 'Preferred only');
  assert.equal(germanBin({german_required:'unspecified', german_requirement:'not required'}), 'Not required');
  assert.equal(germanBin({german_required:'unspecified', german_requirement:'required'}), 'Level unspecified');
});
test('source type comes from the CS / LS prefix and falls back to the source column', () => {
  assert.equal(sourceType({source_site:'CS / Airbus'}), 'CS');
  assert.equal(sourceType({source_site:'LS / linkedin'}), 'LS');
  assert.equal(sourceType({source:'LS'}), 'LS');
  assert.equal(sourceType({}), 'CS');
});
test('options are built only from the supplied scope, in fixed order, with counts', () => {
  const scope = [{experience_min_years:3},{experience_min_years:3},{}];
  assert.deepEqual(binOptions(scope, experienceBin, EXPERIENCE_BINS), [{value:'Not stated',label:'Not stated · 1'},{value:'3 years',label:'3 years · 2'}]);
  assert.deepEqual(binOptions([{source_site:'LS / indeed'}], sourceType, SOURCE_BINS, SOURCE_LABELS), [{value:'LS',label:'Job boards (LS) · 1'}]);
  assert.ok(GERMAN_BINS.includes('Not stated'));
});
test('applyFilters combines source, German, experience and visibility filters', () => {
  const jobs = [
    {title:'A',company:'Airbus',source_site:'CS / Airbus',german_required:'B2',german_requirement:'required',experience_min_years:2},
    {title:'B',company:'Acme',source_site:'LS / linkedin',german_required:'not stated',experience_min_years:null},
    {title:'Postbote',company:'Post',source_site:'CS / Post',excluded_keyword:'postbote'}];
  const names = filters => applyFilters(jobs, filters).map(job => job.title);
  assert.deepEqual(names({}), ['A','B']);
  assert.deepEqual(names({source:['CS']}), ['A']);
  assert.deepEqual(names({source:['LS']}), ['B']);
  assert.deepEqual(names({source:['CS'], showExcluded:true}), ['A','Postbote']);
  assert.deepEqual(names({german:['Intermediate (B1–B2 / good)']}), ['A']);
  assert.deepEqual(names({years:['Not stated']}), ['B']);
  assert.deepEqual(names({query:'acme', source:['CS']}), []);
});
