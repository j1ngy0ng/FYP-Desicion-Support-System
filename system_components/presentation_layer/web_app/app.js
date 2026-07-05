const state = {
  loggedIn: sessionStorage.getItem('ms-auth') === '1',
  user: { name: 'Jing Yong', role: 'Marketing Manager', email: 'jingyong@example.com' },
  campaigns: [
    { id: 'CMP-1048', name: 'Mid-Year Growth Push', type: 'Social Media', intent: 'Growth', channel: 'Instagram, Facebook', status: 'Active', roi: 4.51, conversion: 16.9, budget: 18500 },
    { id: 'CMP-1042', name: 'Premium Member Renewal', type: 'Email', intent: 'Retention', channel: 'Email, WhatsApp', status: 'Active', roi: 2.64, conversion: 23.5, budget: 9200 },
    { id: 'CMP-1039', name: 'Cashflow Recovery', type: 'Paid Ads', intent: 'Survival', channel: 'Google, Facebook', status: 'Review', roi: -0.20, conversion: 20.6, budget: 6300 },
    { id: 'CMP-1031', name: 'Youth Brand Awareness', type: 'Influencer', intent: 'Growth', channel: 'YouTube, Instagram', status: 'Completed', roi: 5.73, conversion: 14.8, budget: 22750 },
    { id: 'CMP-1026', name: 'Loyalty Re-engagement', type: 'Email', intent: 'Retention', channel: 'Email', status: 'Completed', roi: 1.58, conversion: 6.5, budget: 4800 },
  ],
  rules: [
    { id: 'R-01', name: 'Negative ROI protection', category: 'Performance', weight: 0.95, active: true, condition: 'Increase is blocked when ROI < 0' },
    { id: 'R-02', name: 'Growth intent safeguard', category: 'Intent', weight: 0.90, active: true, condition: 'Growth campaigns must not receive Reduce' },
    { id: 'R-03', name: 'Low conversion protection', category: 'Performance', weight: 0.80, active: true, condition: 'Increase is blocked when conversion < 8%' },
    { id: 'R-04', name: 'Evidence sufficiency', category: 'Evidence', weight: 0.75, active: true, condition: 'Decisive action requires 500 clicks and 50 conversions' },
    { id: 'R-05', name: 'Strong signal protection', category: 'Performance', weight: 0.85, active: true, condition: 'Reduce is penalised when 2+ signals are strong' },
  ],
  recommendations: [
    { id: 'REC-2081', campaign: 'Mid-Year Growth Push', action: 'Increase', confidence: 88, intent: 'Growth', date: '28 Jun 2026', status: 'Accepted' },
    { id: 'REC-2079', campaign: 'Premium Member Renewal', action: 'Maintain', confidence: 82, intent: 'Retention', date: '26 Jun 2026', status: 'Accepted' },
    { id: 'REC-2075', campaign: 'Cashflow Recovery', action: 'Reduce', confidence: 76, intent: 'Survival', date: '22 Jun 2026', status: 'Pending' },
    { id: 'REC-2068', campaign: 'Youth Brand Awareness', action: 'Increase', confidence: 91, intent: 'Growth', date: '18 Jun 2026', status: 'Rejected' },
  ],
};

const routes = {
  dashboard: { title: 'Dashboard', group: 'Workspace', icon: '⌂' },
  campaigns: { title: 'Campaign Management', group: 'Workspace', icon: '◫' },
  'campaign-form': { title: 'Add / Edit Campaign', group: 'Workspace', hidden: true },
  analysis: { title: 'Campaign Analysis', group: 'Intelligence', icon: '⌁' },
  generate: { title: 'Generate Recommendation', group: 'Intelligence', icon: '✦' },
  recommendation: { title: 'Recommendation Details', group: 'Intelligence', hidden: true },
  history: { title: 'Recommendation History', group: 'Intelligence', icon: '◷' },
  evaluation: { title: 'Evaluation', group: 'Intelligence', icon: '◎' },
  profile: { title: 'Profile', group: 'Account', icon: '○' },
  rules: { title: 'Rule Management', group: 'Administration', icon: '⚙' },
};

const app = document.getElementById('app');
const money = value => new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR', maximumFractionDigits: 0 }).format(value);
const currentRoute = () => (location.hash.replace('#/', '').split('?')[0] || (state.loggedIn ? 'dashboard' : 'login'));
const routeQuery = () => new URLSearchParams((location.hash.split('?')[1] || ''));
const go = route => { location.hash = `#/${route}`; };

function showToast(message) {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove('show'), 2600);
}

function badge(value) {
  const tone = value === 'Active' || value === 'Accepted' || value === 'Growth' ? '' : value === 'Review' || value === 'Pending' || value === 'Retention' ? 'amber' : value === 'Rejected' ? 'red' : value === 'Survival' ? 'blue' : 'gray';
  return `<span class="badge ${tone}"><span class="status-dot"></span>${value}</span>`;
}

function navigation() {
  const route = currentRoute();
  let html = '';
  [...new Set(Object.values(routes).filter(x => !x.hidden).map(x => x.group))].forEach(group => {
    html += `<div class="nav-label">${group}</div><nav class="nav">`;
    Object.entries(routes).filter(([, x]) => !x.hidden && x.group === group).forEach(([key, x]) => {
      html += `<a href="#/${key}" class="${route === key ? 'active' : ''}"><span class="nav-icon">${x.icon}</span>${x.title.replace(' Management', 's')}</a>`;
    });
    html += '</nav>';
  });
  return html;
}

function shell(content) {
  const route = currentRoute();
  const title = routes[route]?.title || 'Dashboard';
  app.innerHTML = `<div class="app-shell">
    <aside class="sidebar" id="sidebar">
      <a class="brand" href="#/dashboard"><span class="brand-mark">MS</span><span><strong>MarketSense</strong><small>Decision support</small></span></a>
      ${navigation()}
      <div class="sidebar-footer"><a href="#/profile" class="mini-user"><span class="avatar">JY</span><span><strong>${state.user.name}</strong><small>${state.user.role}</small></span></a></div>
    </aside>
    <div class="mobile-overlay" id="overlay"></div>
    <main class="main">
      <header class="topbar"><div class="top-actions"><button class="icon-btn mobile-menu" id="menuButton" aria-label="Open menu">☰</button><span class="breadcrumb">MarketSense / <strong>${title}</strong></span></div><div class="top-actions"><button class="icon-btn" aria-label="Notifications">♢</button><button class="btn btn-primary btn-sm" data-route="generate">✦ New recommendation</button></div></header>
      ${content}
    </main>
  </div>`;
  const menu = document.getElementById('sidebar');
  const overlay = document.getElementById('overlay');
  document.getElementById('menuButton')?.addEventListener('click', () => { menu.classList.add('open'); overlay.classList.add('open'); });
  overlay?.addEventListener('click', () => { menu.classList.remove('open'); overlay.classList.remove('open'); });
  document.querySelectorAll('[data-route]').forEach(el => el.addEventListener('click', () => go(el.dataset.route)));
}

function pageHead(eyebrow, title, subtitle, actions = '') {
  return `<div class="page-head"><div><p class="eyebrow">${eyebrow}</p><h1>${title}</h1><p class="subhead">${subtitle}</p></div>${actions ? `<div class="actions">${actions}</div>` : ''}</div>`;
}

function loginPage() {
  app.innerHTML = `<section class="login-page">
    <div class="login-visual"><div class="brand"><span class="brand-mark">MS</span><span><strong>MarketSense</strong><small>Decision support</small></span></div><div><p class="eyebrow">Intent-aware intelligence</p><h1>Marketing decisions, grounded in evidence.</h1><p>Combine predictive attribution, business rules, strategic intent and calibrated trust in one explainable workflow.</p></div><small>Final decisions remain under human control.</small></div>
    <div class="login-panel"><form class="login-card" id="loginForm"><p class="eyebrow">Welcome back</p><h2>Sign in</h2><p class="subhead">Access your campaign decision workspace.</p><div class="field"><label for="email">Email address</label><input id="email" type="email" value="jingyong@example.com" required></div><div class="field"><label for="password">Password</label><input id="password" type="password" value="prototype" required></div><div class="field"><label><input type="checkbox" style="width:auto"> Remember this device</label></div><button class="btn btn-primary" type="submit">Sign in →</button><div class="demo-note">Prototype access: use the pre-filled credentials.</div></form></div>
  </section>`;
  document.getElementById('loginForm').addEventListener('submit', event => { event.preventDefault(); state.loggedIn = true; sessionStorage.setItem('ms-auth', '1'); go('dashboard'); });
}

function dashboardPage() {
  shell(`<div class="page">${pageHead('Overview', 'Good morning, Jing Yong.', 'Here is the current state of your marketing decision workspace.', `<button class="btn btn-ghost" data-route="campaigns">View campaigns</button><button class="btn btn-primary" data-route="generate">Generate recommendation</button>`)}
    <section class="grid grid-4">
      ${[['Active campaigns','12','+8% this month'],['Average ROI','3.42','+0.38 vs last period'],['Recommendations','28','6 awaiting review'],['Trust alignment','84%','+4.2% calibrated']].map((m,i)=>`<article class="card metric-card"><div class="metric-label">${m[0]}</div><div class="metric-value">${m[1]}</div><div class="trend ${i===2?'down':''}">${m[2]}</div></article>`).join('')}
    </section>
    <section class="grid grid-3" style="margin-top:18px">
      <article class="card span-2"><div class="card-head"><div><h2>Performance pulse</h2><div class="card-note">Revenue and conversions over six months</div></div><select style="width:auto"><option>Last 6 months</option><option>Last 12 months</option></select></div><div class="chart-wrap"><div class="chart">${[['Jan',42,28],['Feb',51,34],['Mar',46,39],['Apr',68,45],['May',74,53],['Jun',88,62]].map(x=>`<div class="bar-group"><span class="bar" style="height:${x[1]}%"></span><span class="bar alt" style="height:${x[2]}%"></span><span class="bar-label">${x[0]}</span></div>`).join('')}</div></div></article>
      <article class="card"><div class="card-head"><div><h2>Campaign intent</h2><div class="card-note">Current portfolio mix</div></div></div><div class="donut"></div><div class="legend"><div class="legend-row"><span class="legend-label"><span class="dot"></span>Growth</span><strong>42%</strong></div><div class="legend-row"><span class="legend-label"><span class="dot amber"></span>Retention</span><strong>30%</strong></div><div class="legend-row"><span class="legend-label"><span class="dot blue"></span>Survival</span><strong>18%</strong></div><div class="legend-row"><span class="legend-label"><span class="dot gray"></span>Other</span><strong>10%</strong></div></div></article>
    </section>
    <section class="grid grid-2" style="margin-top:18px"><article class="card"><div class="card-head"><h2>Recent recommendations</h2><button class="btn btn-ghost btn-sm" data-route="history">View all</button></div>${state.recommendations.slice(0,3).map(r=>`<div class="timeline-item"><h3>${r.action} · ${r.campaign}</h3><p>${r.id} · ${r.date} · ${r.confidence}% confidence</p></div>`).join('')}</article><article class="card"><div class="card-head"><h2>Attention required</h2><span class="badge amber">3 items</span></div><ul class="reason-list"><li><strong>Cashflow Recovery</strong><br><span class="card-note">Negative ROI requires managerial review.</span></li><li><strong>REC-2075 pending</strong><br><span class="card-note">Recommendation has not been accepted or rejected.</span></li><li><strong>Rule R-04</strong><br><span class="card-note">Evidence threshold triggered twice this week.</span></li></ul></article></section>
  </div>`);
}

function campaignsPage() {
  shell(`<div class="page">${pageHead('Campaign workspace', 'Campaign management', 'Create, review and analyse multi-channel marketing campaigns.', `<button class="btn btn-primary" data-route="campaign-form">＋ Add campaign</button>`)}
    <div class="card"><div class="toolbar"><div class="search"><input id="campaignSearch" placeholder="Search campaign or ID"></div><select id="intentFilter" style="width:170px"><option value="">All intents</option><option>Growth</option><option>Retention</option><option>Survival</option></select><select style="width:160px"><option>All statuses</option><option>Active</option><option>Review</option><option>Completed</option></select></div><div class="table-wrap"><table><thead><tr><th>Campaign</th><th>Intent</th><th>Channels</th><th>Status</th><th>ROI</th><th>Budget</th><th></th></tr></thead><tbody id="campaignRows"></tbody></table></div></div>
  </div>`);
  const draw = () => {
    const q = document.getElementById('campaignSearch').value.toLowerCase();
    const intent = document.getElementById('intentFilter').value;
    const filtered = state.campaigns.filter(c => (!q || `${c.name} ${c.id}`.toLowerCase().includes(q)) && (!intent || c.intent === intent));
    document.getElementById('campaignRows').innerHTML = filtered.map(c => `<tr><td><div class="campaign-name">${c.name}</div><div class="campaign-id">${c.id} · ${c.type}</div></td><td>${badge(c.intent)}</td><td>${c.channel}</td><td>${badge(c.status)}</td><td><strong>${c.roi.toFixed(2)}</strong></td><td>${money(c.budget)}</td><td><div class="actions"><button class="btn btn-ghost btn-sm" onclick="go('analysis?id=${c.id}')">Analyse</button><button class="btn btn-secondary btn-sm" onclick="go('campaign-form?id=${c.id}')">Edit</button></div></td></tr>`).join('') || `<tr><td colspan="7"><div class="empty-state"><strong>No campaigns found</strong>Try a different search or filter.</div></td></tr>`;
  };
  document.getElementById('campaignSearch').addEventListener('input', draw);
  document.getElementById('intentFilter').addEventListener('change', draw);
  draw();
}

function campaignFormPage() {
  const id = routeQuery().get('id');
  const c = state.campaigns.find(x => x.id === id) || {};
  const editing = Boolean(c.id);
  shell(`<div class="page">${pageHead('Campaign workspace', editing ? 'Edit campaign' : 'Add a campaign', 'Record the campaign context and performance data used by downstream analysis.', `<button class="btn btn-ghost" data-route="campaigns">Cancel</button>`)}
    <form class="card" id="campaignForm"><div class="card-head"><div><h2>Campaign information</h2><div class="card-note">Fields marked required are used in recommendation generation.</div></div></div><div class="form-grid">
      <div class="field"><label>Campaign name *</label><input name="name" value="${c.name||''}" required></div><div class="field"><label>Campaign type *</label><select name="type"><option ${c.type==='Social Media'?'selected':''}>Social Media</option><option ${c.type==='Email'?'selected':''}>Email</option><option ${c.type==='Paid Ads'?'selected':''}>Paid Ads</option><option ${c.type==='Influencer'?'selected':''}>Influencer</option><option>SEO</option></select></div>
      <div class="field"><label>Strategic intent *</label><select name="intent"><option ${c.intent==='Growth'?'selected':''}>Growth</option><option ${c.intent==='Retention'?'selected':''}>Retention</option><option ${c.intent==='Survival'?'selected':''}>Survival</option></select></div><div class="field"><label>Channels *</label><input name="channel" value="${c.channel||''}" placeholder="e.g. Instagram, Facebook" required></div>
      <div class="field"><label>Budget (MYR)</label><input name="budget" type="number" min="0" value="${c.budget||''}"></div><div class="field"><label>Duration (days)</label><input type="number" min="1" value="21"></div>
      <div class="field"><label>Impressions</label><input type="number" min="0" value="75462"></div><div class="field"><label>Clicks</label><input type="number" min="0" value="6250"></div>
      <div class="field"><label>Conversions</label><input type="number" min="0" value="${c.conversion ? Math.round(6250*c.conversion/100) : 850}"></div><div class="field"><label>Revenue (MYR)</label><input type="number" min="0" value="128000"></div>
      <div class="field"><label>Acquisition cost (MYR)</label><input type="number" min="0" value="240"></div><div class="field"><label>Engagement score</label><input type="number" min="0" max="30" step=".1" value="18.4"></div>
      <div class="field full"><label>Notes</label><textarea rows="3" placeholder="Campaign context, constraints or observations"></textarea></div>
    </div><div class="actions"><button type="button" class="btn btn-ghost" data-route="campaigns">Cancel</button><button type="submit" class="btn btn-primary">${editing?'Save changes':'Create campaign'}</button></div></form>
  </div>`);
  document.getElementById('campaignForm').addEventListener('submit', event => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    if (editing) Object.assign(c, { name:data.get('name'), type:data.get('type'), intent:data.get('intent'), channel:data.get('channel'), budget:Number(data.get('budget')) });
    else state.campaigns.unshift({ id:`CMP-${1050+state.campaigns.length}`, name:data.get('name'), type:data.get('type'), intent:data.get('intent'), channel:data.get('channel'), status:'Review', roi:0, conversion:0, budget:Number(data.get('budget')) });
    showToast(editing ? 'Campaign updated.' : 'Campaign created.'); setTimeout(()=>go('campaigns'),500);
  });
}

function analysisPage() {
  const c = state.campaigns.find(x => x.id === routeQuery().get('id')) || state.campaigns[0];
  shell(`<div class="page">${pageHead('Predictive analytics', c.name, `${c.id} · ${c.channel} · ${c.intent} intent`, `<button class="btn btn-ghost" data-route="campaigns">All campaigns</button><button class="btn btn-primary" data-route="generate?campaign=${c.id}">Generate recommendation</button>`)}
    <section class="grid grid-4">${[['ROI',c.roi.toFixed(2),c.roi>0?'Healthy return':'Needs attention'],['Conversion rate',`${c.conversion}%`,'Above portfolio median'],['Engagement score','18.4','Strong audience response'],['Attribution quality','86%','Sufficient evidence']].map(m=>`<article class="card metric-card"><div class="metric-label">${m[0]}</div><div class="metric-value">${m[1]}</div><div class="trend">${m[2]}</div></article>`).join('')}</section>
    <section class="grid grid-3" style="margin-top:18px"><article class="card span-2"><div class="card-head"><div><h2>Channel attribution</h2><div class="card-note">Estimated contribution to campaign outcome</div></div></div>${[['Instagram',78],['Facebook',63],['Email',41],['Google',34]].map(x=>`<div style="margin:18px 0"><div class="legend-row"><strong>${x[0]}</strong><span>${x[1]}%</span></div><div class="progress"><span style="width:${x[1]}%"></span></div></div>`).join('')}</article><article class="card"><div class="card-head"><h2>Predictive outlook</h2></div><div class="score-ring" style="--score:84;margin:auto"><div><span><strong>84</strong><small>performance</small></span></div></div><p class="card-note" style="text-align:center">Expected effectiveness is high based on ROI, conversion and engagement patterns.</p></article></section>
    <section class="card" style="margin-top:18px"><div class="card-head"><div><h2>Key performance drivers</h2><div class="card-note">Factors with the strongest estimated influence</div></div></div><div class="grid grid-3"><div><span class="badge">Positive</span><h3 style="margin-top:10px">Return on investment</h3><p class="card-note">ROI contributes strongly to the positive outlook.</p></div><div><span class="badge">Positive</span><h3 style="margin-top:10px">Conversion efficiency</h3><p class="card-note">Conversion remains above the portfolio median.</p></div><div><span class="badge amber">Monitor</span><h3 style="margin-top:10px">Acquisition cost</h3><p class="card-note">Cost increased 8% relative to the previous period.</p></div></div></section>
  </div>`);
}

function generatePage() {
  shell(`<div class="page">${pageHead('Neuro-symbolic reasoning', 'Generate recommendation', 'Select a campaign and strategic intent, then run predictive and rule-constrained reasoning.')}
    <div class="grid grid-3"><form class="card span-2" id="generateForm"><div class="card-head"><div><h2>Decision context</h2><div class="card-note">Review the context before generating an action.</div></div></div><div class="field"><label>Campaign</label><select id="generateCampaign">${state.campaigns.map(c=>`<option value="${c.id}" ${routeQuery().get('campaign')===c.id?'selected':''}>${c.name} (${c.id})</option>`).join('')}</select></div><div class="field"><label>Strategic intent</label><select><option>Growth</option><option>Retention</option><option>Survival</option></select></div><div class="field"><label>Decision objective</label><textarea rows="4">Improve campaign performance while maintaining acceptable acquisition cost and avoiding conflicts with the selected strategic intent.</textarea></div><div class="field"><label>Risk tolerance</label><select><option>Balanced</option><option>Conservative</option><option>Aggressive</option></select></div><button class="btn btn-primary" type="submit">✦ Run recommendation engine</button></form>
    <aside class="card"><div class="card-head"><h2>Reasoning pipeline</h2></div><div class="timeline"><div class="timeline-item"><h3>Predictive attribution</h3><p>Estimate performance and channel contribution.</p></div><div class="timeline-item"><h3>Candidate actions</h3><p>Generate Increase, Maintain, Reduce and Investigate.</p></div><div class="timeline-item"><h3>Soft-rule reasoning</h3><p>Score actions against weighted business constraints.</p></div><div class="timeline-item"><h3>Intent alignment</h3><p>Adjust priorities for the selected objective.</p></div><div class="timeline-item"><h3>Trust calibration</h3><p>Calibrate confidence and prepare explanation.</p></div></div></aside></div>
  </div>`);
  document.getElementById('generateForm').addEventListener('submit', event => { event.preventDefault(); showToast('Recommendation generated successfully.'); setTimeout(()=>go(`recommendation?campaign=${document.getElementById('generateCampaign').value}`),650); });
}

function recommendationPage() {
  const c = state.campaigns.find(x=>x.id===routeQuery().get('campaign')) || state.campaigns[0];
  shell(`<div class="page">${pageHead('Recommendation REC-2084', 'Recommendation details', `Generated for ${c.name} using predictive attribution and weighted soft-rule reasoning.`, `<button class="btn btn-ghost" data-route="history">View history</button>`)}
    <article class="card recommendation-hero"><div class="action-orb">↗</div><div><span class="badge">Recommended action</span><h1 style="font-size:38px;margin-top:8px">Increase investment</h1><p class="subhead">Prioritise Instagram and Facebook while monitoring acquisition cost.</p></div><div class="score-ring" style="--score:88"><div><span><strong>88%</strong><small>calibrated trust</small></span></div></div></article>
    <section class="grid grid-2" style="margin-top:18px"><article class="card"><div class="card-head"><h2>Why this action?</h2></div><ul class="reason-list"><li><strong>Strong predictive performance</strong><br><span class="card-note">ROI of ${c.roi.toFixed(2)} and conversion of ${c.conversion}% support controlled growth.</span></li><li><strong>Intent alignment</strong><br><span class="card-note">The Increase action aligns with the campaign's ${c.intent} objective.</span></li><li><strong>No critical rule conflicts</strong><br><span class="card-note">The action passed all active high-weight business constraints.</span></li></ul></article><article class="card"><div class="card-head"><h2>Decision scores</h2></div>${[['Predictive score',84],['Rule compliance',96],['Intent alignment',100],['Evidence quality',82]].map(x=>`<div style="margin:17px 0"><div class="legend-row"><strong>${x[0]}</strong><span>${x[1]}%</span></div><div class="progress"><span style="width:${x[1]}%"></span></div></div>`).join('')}</article></section>
    <section class="grid grid-2" style="margin-top:18px"><article class="card"><div class="card-head"><h2>Recommended next steps</h2></div><ol><li>Increase the campaign allocation by 10–15%.</li><li>Prioritise the two highest-attribution channels.</li><li>Review acquisition cost after seven days.</li><li>Pause expansion if ROI falls below 1.5.</li></ol></article><article class="card"><div class="card-head"><h2>Caveats</h2></div><p>Confidence depends on the completeness of reported clicks, conversions and acquisition cost. Channel attribution is estimated at campaign level.</p><div class="actions"><button class="btn btn-danger" id="rejectRec">Reject</button><button class="btn btn-ghost" id="deferRec">Defer</button><button class="btn btn-primary" id="acceptRec">Accept recommendation</button></div></article></section>
  </div>`);
  [['acceptRec','Recommendation accepted.'],['rejectRec','Recommendation rejected.'],['deferRec','Recommendation deferred for review.']].forEach(([id,msg])=>document.getElementById(id).addEventListener('click',()=>showToast(msg)));
}

function historyPage() {
  shell(`<div class="page">${pageHead('Decision record', 'Recommendation history', 'Review generated recommendations, outcomes and managerial decisions.', `<button class="btn btn-primary" data-route="generate">Generate new</button>`)}
    <div class="card"><div class="toolbar"><div class="search"><input placeholder="Search recommendation or campaign"></div><select style="width:170px"><option>All decisions</option><option>Accepted</option><option>Pending</option><option>Rejected</option></select></div><div class="table-wrap"><table><thead><tr><th>Recommendation</th><th>Campaign</th><th>Action</th><th>Intent</th><th>Trust</th><th>Decision</th><th>Date</th><th></th></tr></thead><tbody>${state.recommendations.map(r=>`<tr><td><strong>${r.id}</strong></td><td>${r.campaign}</td><td><strong>${r.action}</strong></td><td>${badge(r.intent)}</td><td>${r.confidence}%</td><td>${badge(r.status)}</td><td>${r.date}</td><td><button class="btn btn-ghost btn-sm" data-route="recommendation">View</button></td></tr>`).join('')}</tbody></table></div></div>
  </div>`);
}

function evaluationPage() {
  const metrics = [
    ['Recommendation accuracy','81.5%','Correct action agreement'],['Scenario-fit rate','96.3%','Intent-compatible outputs'],['Logical conflict rate','11.1%','Lower is better'],['Expected calibration error','18.6%','Confidence calibration gap'],['Actionability','88.1%','Operational usefulness'],['User acceptance','56.4%','Accepted recommendations']
  ];
  shell(`<div class="page">${pageHead('Experiment results', 'System evaluation', 'Compare decision quality, logical consistency, trust calibration and user-oriented outcomes.', `<button class="btn btn-ghost" id="exportEval">Export summary</button>`)}
    <section class="grid grid-3">${metrics.map((m,i)=>`<article class="card metric-card"><div class="metric-label">${m[0]}</div><div class="metric-value">${m[1]}</div><div class="trend ${i===2||i===3?'down':''}">${m[2]}</div></article>`).join('')}</section>
    <section class="card" style="margin-top:18px"><div class="card-head"><div><h2>Baseline comparison</h2><div class="card-note">Normal holdout evaluation using the same rows and rules</div></div><select style="width:auto"><option>Normal dataset</option><option>Conflict stress dataset</option></select></div><div class="table-wrap"><table><thead><tr><th>System</th><th>Accuracy</th><th>Scenario fit</th><th>Conflict rate</th><th>ECE</th><th>Actionability</th></tr></thead><tbody><tr><td><strong>Baseline A</strong></td><td>59.3%</td><td>100.0%</td><td>3.7%</td><td>13.6%</td><td>89.0%</td></tr><tr><td><strong>Baseline B</strong></td><td>81.5%</td><td>96.3%</td><td>11.1%</td><td>18.6%</td><td>88.1%</td></tr><tr><td><strong>Baseline C</strong></td><td>74.1%</td><td>92.6%</td><td>14.8%</td><td>6.1%</td><td>85.1%</td></tr><tr style="background:#edf6f0"><td><strong>Proposed system</strong><br><span class="campaign-id">Awaiting implementation evaluation</span></td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td></tr></tbody></table></div></section>
  </div>`);
  document.getElementById('exportEval').addEventListener('click',()=>showToast('Evaluation summary prepared for export.'));
}

function profilePage() {
  shell(`<div class="page">${pageHead('Account', 'Profile and preferences', 'Manage your identity, notification preferences and account security.')}
    <div class="grid grid-3"><aside class="card"><div class="avatar" style="width:82px;height:82px;font-size:24px;margin-bottom:14px">JY</div><h2>${state.user.name}</h2><p class="card-note">${state.user.role}</p><span class="badge">Active account</span><hr style="border:0;border-top:1px solid var(--line);margin:22px 0"><p class="card-note">Member since January 2026<br>Last sign-in: Today, 09:42</p><button class="btn btn-danger btn-sm" id="logout">Sign out</button></aside><form class="card span-2" id="profileForm"><div class="card-head"><h2>Personal information</h2></div><div class="form-grid"><div class="field"><label>Full name</label><input value="${state.user.name}"></div><div class="field"><label>Role</label><input value="${state.user.role}"></div><div class="field"><label>Email</label><input type="email" value="${state.user.email}"></div><div class="field"><label>Organisation</label><input value="SME Marketing Lab"></div><div class="field full"><label>Decision summary frequency</label><select><option>Weekly</option><option>Daily</option><option>Monthly</option><option>Never</option></select></div><div class="field full"><label><input type="checkbox" checked style="width:auto"> Notify me when recommendations require review</label><label><input type="checkbox" checked style="width:auto"> Notify me when a critical business rule is triggered</label></div></div><button class="btn btn-primary">Save profile</button></form></div>
  </div>`);
  document.getElementById('profileForm').addEventListener('submit',e=>{e.preventDefault();showToast('Profile saved.');});
  document.getElementById('logout').addEventListener('click',()=>{sessionStorage.removeItem('ms-auth');state.loggedIn=false;go('login');});
}

function rulesPage() {
  shell(`<div class="page">${pageHead('Administration', 'Rule management', 'Configure weighted soft rules used to detect contradictions and rank candidate actions.', `<button class="btn btn-primary" id="addRule">＋ Add rule</button>`)}
    <section class="grid grid-4">${[['Active rules','5','All categories'],['Average weight','0.85','High influence'],['Triggered this month','14','Across 9 campaigns'],['Critical conflicts','3','Require review']].map(m=>`<article class="card metric-card"><div class="metric-label">${m[0]}</div><div class="metric-value">${m[1]}</div><div class="trend">${m[2]}</div></article>`).join('')}</section>
    <section class="card" style="margin-top:18px"><div class="card-head"><div><h2>Business rule catalogue</h2><div class="card-note">Rules are applied consistently to every candidate recommendation.</div></div></div><div id="ruleList">${state.rules.map((r,i)=>`<div class="rule-row"><div><div class="campaign-name">${r.name}</div><div class="card-note">${r.id} · ${r.condition}</div></div><div class="rule-meta">${badge(r.category)}</div><div class="rule-meta"><strong>${r.weight.toFixed(2)}</strong> weight</div><div class="actions"><button class="switch ${r.active?'on':''}" data-rule="${i}" aria-label="Toggle ${r.name}"></button><button class="btn btn-ghost btn-sm" data-edit-rule="${i}">Edit</button></div></div>`).join('')}</div></section>
  </div>`);
  document.querySelectorAll('[data-rule]').forEach(btn=>btn.addEventListener('click',()=>{const r=state.rules[Number(btn.dataset.rule)];r.active=!r.active;btn.classList.toggle('on',r.active);showToast(`${r.name} ${r.active?'enabled':'disabled'}.`);}));
  document.querySelectorAll('[data-edit-rule]').forEach(btn=>btn.addEventListener('click',()=>showToast(`Rule ${state.rules[Number(btn.dataset.editRule)].id} opened for editing.`)));
  document.getElementById('addRule').addEventListener('click',()=>showToast('New rule form ready.'));
}

function render() {
  const route = currentRoute();
  if (route === 'login' || !state.loggedIn) return loginPage();
  const pages = { dashboard:dashboardPage, campaigns:campaignsPage, 'campaign-form':campaignFormPage, analysis:analysisPage, generate:generatePage, recommendation:recommendationPage, history:historyPage, evaluation:evaluationPage, profile:profilePage, rules:rulesPage };
  (pages[route] || dashboardPage)();
  window.scrollTo(0,0);
}

window.addEventListener('hashchange', render);
window.go = go;
render();
