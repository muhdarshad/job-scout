import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';

test('Applications and Discover render jobs with missing company names', async () => {
  const server = await createServer({server:{middlewareMode:true}, appType:'custom'});
  try {
    const {App} = await server.ssrLoadModule('/src/App.jsx');
    const {RenderFailure} = await server.ssrLoadModule('/src/ErrorBoundary.jsx');
    const fallback = renderToStaticMarkup(React.createElement(RenderFailure,{message:'Test render error'}));
    assert.match(fallback,/Reload workspace/);
    assert.match(fallback,/Test render error/);
    const state = {jobs:[null,undefined,'','Airbus'].map((company,i) => ({key:String(i),version:1,title:'Engineer '+i,company,status:'New',first_seen:'2026-10-27T13:00:00Z'})),
      statuses:['New','Shortlisted','Applied','Not interested','Not fit'],runs:[],schedule:{enabled:false},title_exclusions:[]};
    for (const page of ['Applications','Discover','Sources']) {
      const html = renderToStaticMarkup(React.createElement(App,{initialData:state,initialPage:page}));
      assert.match(html,/Application Studio/);
      if(page === 'Discover') for(let i=0;i<4;i++) assert.ok(html.includes('Engineer '+i));
    }
    for (const job of state.jobs) job.status = 'Shortlisted';
    for (const page of ['Applications','Discover']) {
      const html = renderToStaticMarkup(React.createElement(App,{initialData:state,initialPage:page}));
      assert.match(html,/Application Studio/);
      if(page === 'Applications') assert.match(html,/Engineer 0/);
    }
  } finally {await server.close();}
});
