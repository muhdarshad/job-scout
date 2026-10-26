import test from 'node:test';
import assert from 'node:assert/strict';
import { createAlerts } from '../src/alerts.js';

test('alerts skip historical data, duplicate polls and zero-new-job runs', async () => {
  const storage = new Map();
  globalThis.localStorage = {getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value)};
  const messages = [], manager = createAlerts();
  const run = (id, added, status='Complete') => ({id,finished:'2026-10-26T11:00:00Z',status,details:{added}});
  await manager.process([run(1,5)],message=>messages.push(message));
  assert.deepEqual(messages,[]);
  await manager.process([run(2,3),run(1,5)],message=>messages.push(message));
  await manager.process([run(2,3),run(1,5)],message=>messages.push(message));
  assert.deepEqual(messages,['3 new jobs available']);
  await manager.process([run(3,0),run(2,3)],message=>messages.push(message));
  await manager.process([run(4,2,'Partial'),run(3,0)],message=>messages.push(message));
  assert.deepEqual(messages,['3 new jobs available','2 new jobs available']);
  const reopened = createAlerts();
  await reopened.process([run(4,2,'Partial')],message=>messages.push(message));
  assert.equal(messages.length,2);
});
test('two open tabs claim a completed run once', async () => {
  const storage = new Map();
  globalThis.localStorage = {getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value)};
  const first=createAlerts(), second=createAlerts(), messages=[];
  const run=id=>({id,finished:'yes',status:'Complete',details:{added:1}});
  await first.process([run(1)],messages.push.bind(messages));
  await second.process([run(1)],messages.push.bind(messages));
  await first.process([run(2)],messages.push.bind(messages));
  await second.process([run(2)],messages.push.bind(messages));
  assert.equal(messages.length,1);
});
