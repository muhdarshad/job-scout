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
  assert.equal(date.label, 'Posted');
  assert.equal(date.text, new Date('2026-10-25T12:00:00').toLocaleDateString(undefined,{dateStyle:'medium'}));
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
