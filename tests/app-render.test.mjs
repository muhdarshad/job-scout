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
      preferences:{enabled_sites:['site-a'],job_boards:['linkedin'],search_terms:['Engineer'],skills:['Python'],cleanup_archived:true,exclude_linkedin_reposts:true},sites:[{id:'site-a',name:'Example'}],
      statuses:['New','Shortlisted','Applied','Not interested','Not fit'],runs:[],schedule:{enabled:false},title_exclusions:[],
      builtin_filters:{excluded_titles:['custom title'],excluded_seniority:[],not_interested_titles:[],interested_titles:[],excluded_requirements:[],full_time_only:true},
      builtin_filter_defaults:{excluded_titles:['default title'],excluded_seniority:[],not_interested_titles:[],interested_titles:[],excluded_requirements:[],full_time_only:true}};
    for (const page of ['Applications','Discover','Sources','Settings']) {
      const html = renderToStaticMarkup(React.createElement(App,{initialData:state,initialPage:page}));
      assert.match(html,/Application Studio/);
      if(page === 'Settings') {assert.match(html,/Built-in scraper filters/);assert.match(html,/customised/);assert.match(html,/Reset to defaults/);assert.match(html,/Save settings/);assert.match(html,/Customize statuses/);assert.match(html,/Title exclusions/);}
      if(page === 'Applications') assert.ok(!html.includes('Customize statuses'));
      if(page === 'Discover') for(let i=0;i<4;i++) assert.ok(html.includes('Engineer '+i));
    }
    const landing = renderToStaticMarkup(React.createElement(App,{initialData:state}));
    assert.match(landing,/Discover opportunities/);
    assert.match(landing,/Source/);
    for (const job of state.jobs) job.status = 'Shortlisted';
    for (const page of ['Applications','Discover']) {
      const html = renderToStaticMarkup(React.createElement(App,{initialData:state,initialPage:page}));
      assert.match(html,/Application Studio/);
      if(page === 'Applications') assert.match(html,/Engineer 0/);
    }
  } finally {await server.close();}
});
