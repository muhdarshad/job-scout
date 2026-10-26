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
