import test from 'node:test';
import assert from 'node:assert/strict';
import {selectedLinks} from '../src/selectedLinks.js';
test('selected links are valid HTTP(S), unique and selected only', () => {
  const jobs = [{key:'a',job_url:'https://example.com/job',title:'A'},{key:'b',job_url:'https://example.com/job'},{key:'c',job_url:'javascript:alert(1)'},{key:'d',job_url:'https://example.com/other'},{key:'e',job_url:null}];
  assert.deepEqual(selectedLinks(jobs,{a:true,b:true,c:true,e:true}),[{url:'https://example.com/job',title:'A'}]);
});
