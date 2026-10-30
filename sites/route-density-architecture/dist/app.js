const architecture = {
  source: { kicker: 'STEP 1 · LOCAL SOURCE', title: 'Generate deterministic operational extracts.', body: 'A seeded Python generator produces trucks, routes, customers, pickup attempts, route-day costs and an error manifest. The same seed produces byte-identical files.', input: 'Seed 42 · 90 calendar days', output: 'CSV files + _manifest.json', guarantee: 'Replayable synthetic source' },
  bronze: { kicker: 'STEP 2 · STORAGE', title: 'Land source values exactly as received.', body: 'Bronze is an immutable S3 prefix. Every CSV column remains text so malformed values survive long enough to be evaluated by the quality rules.', input: '132 source objects', output: 's3://…/bronze/', guarantee: 'Original values preserved' },
  workflow: { kicker: 'STEP 3 · ORCHESTRATION', title: 'Visualize success-only job dependency.', body: 'The Glue Workflow has a disabled ON_DEMAND start trigger. A conditional trigger connects Job 1 to Job 2 only when Bronze-to-Silver succeeds; deployment runs the jobs sequentially through the API.', input: 'Disabled start trigger', output: 'Job 1 → SUCCEEDED → Job 2', guarantee: 'No automatic run on creation' },
  job1: { kicker: 'STEP 4 · COMPUTE', title: 'Validate and account for every source row.', body: 'Glue reads every Bronze field as text, removes deterministic duplicates, parses contract types, applies five rules in exact order and captures the first failed rule.', input: 'Raw Bronze CSV', output: 'Valid rows + rejects + audit', guarantee: 'No silent row loss' },
  silver: { kicker: 'STEP 5 · STORAGE', title: 'Persist trusted operations and their audit trail.', body: 'Silver stores typed trucks, routes, customers, pickups and route days alongside rejects and load_audit. Each source satisfies the reconciliation equation.', input: 'Validated Spark frames', output: '7 Parquet datasets', guarantee: 'raw = valid + rejected + duplicates' },
  job2: { kicker: 'STEP 6 · COMPUTE', title: 'Model business processes at natural grains.', body: 'The second Glue job creates conformed dimensions, separate pickup and route-day facts, an additive route-day mart, reject summary, and materialized route and fuel KPIs.', input: 'Trusted Silver Parquet', output: 'Dimensions · facts · marts', guarantee: 'Grain-safe modeling' },
  gold: { kicker: 'STEP 7 · STORAGE', title: 'Publish decision-ready analytical datasets.', body: 'Gold contains four dimensions, two facts and four marts. Counts and sums remain additive; ratios use sum-over-sum at query time or in dedicated KPI tables.', input: 'Modeled Spark frames', output: '10 Parquet datasets', guarantee: 'No cost fanout' },
  catalog: { kicker: 'STEP 8 · METADATA', title: 'Expose explicit schemas without inference.', body: 'Terraform defines all seven Silver and ten Gold tables in Glue Catalog. There is no crawler: names, types and S3 locations are infrastructure as code.', input: 'Terraform table definitions', output: '17 Catalog tables', guarantee: 'Stable Athena schemas' },
  athena: { kicker: 'STEP 9 · QUERY', title: 'Query Parquet without managing a cluster.', body: 'Athena reads Gold through the Catalog, writes temporary results to a seven-day S3 prefix, and runs reconciliation and uniqueness checks after deployment.', input: 'SQL + Catalog metadata', output: 'Compact result sets', guarantee: '4 / 4 AWS QA checks' },
  streamlit: { kicker: 'STEP 10 · SERVING', title: 'Reuse one KPI definition across backends.', body: 'The local Streamlit app submits Athena queries with boto3, converts dates before filtering and passes additive results through the same sum-over-sum KPI functions used locally.', input: 'Athena result CSV', output: 'Filtered KPIs and charts', guarantee: 'No dashboard ETL' },
  decision: { kicker: 'STEP 11 · OUTCOME', title: 'Turn route economics into an action list.', body: 'Operations sees high-cost and low-density routes, missed pickup behavior, fuel economics and an upper-bound annual savings estimate against each service line’s median.', input: 'Trusted route and fuel KPIs', output: 'Prioritized route decisions', guarantee: 'Residential ≠ commercial benchmark' }
};

const tourOrder = ['source','bronze','workflow','job1','silver','job2','gold','catalog','athena','streamlit','decision'];
let tourIndex = -1;
const archNodes = [...document.querySelectorAll('[data-arch]')];
const fields = {
  kicker: document.querySelector('#arch-kicker'), title: document.querySelector('#arch-title'),
  body: document.querySelector('#arch-body'), input: document.querySelector('#arch-input'),
  output: document.querySelector('#arch-output'), guarantee: document.querySelector('#arch-guarantee')
};
const tourCount = document.querySelector('#tour-count');

function selectArchitecture(key, fromTour = false) {
  const item = architecture[key];
  if (!item) return;
  archNodes.forEach(node => node.classList.toggle('active', node.dataset.arch === key));
  const active = archNodes.find(node => node.dataset.arch === key);
  if (active) { active.classList.remove('pulse'); void active.offsetWidth; active.classList.add('pulse'); }
  Object.keys(fields).forEach(name => fields[name].textContent = item[name]);
  tourIndex = tourOrder.indexOf(key);
  tourCount.textContent = `Step ${tourIndex + 1} of ${tourOrder.length}`;
  if (fromTour && active && window.innerWidth < 760) active.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

archNodes.forEach(node => node.addEventListener('click', () => selectArchitecture(node.dataset.arch)));
document.querySelector('#tour-start')?.addEventListener('click', () => selectArchitecture(tourOrder[0], true));
document.querySelector('#tour-prev')?.addEventListener('click', () => selectArchitecture(tourOrder[Math.max(0, tourIndex - 1)], true));
document.querySelector('#tour-next')?.addEventListener('click', () => selectArchitecture(tourOrder[Math.min(tourOrder.length - 1, tourIndex + 1)], true));

const modelDetails = {
  customer: ['DIMENSION', 'Customers provide route ownership, market segment, weekday service pattern and monthly revenue context.'],
  route: ['DIMENSION', 'Routes provide the depot and service-line boundary used for fair residential-versus-commercial comparisons.'],
  truck: ['DIMENSION', 'Trucks provide fuel type, model year and body type for fleet economics and maintenance analysis.'],
  date: ['DIMENSION', 'The complete date spine covers every calendar day in the source range, including weekends without service.'],
  pickup: ['FACT · PICKUP GRAIN', 'One row represents one attempted stop. Completed and missed flags are additive; tons is null for a missed stop. Cost does not belong here.'],
  routeDay: ['FACT · ROUTE-DAY-TRUCK GRAIN', 'One row represents one truck operating one route on one service date. Hours, kilometres and all costs belong at this grain.'],
  routeMart: ['MART · ROUTE-DAY-TRUCK GRAIN', 'Pickup attempts are rolled up first, then inner-joined to trusted route-day cost using date + route + truck. Rejected cost days are intentionally excluded.'],
  routeKpi: ['KPI MART · ROUTE GRAIN', 'Route totals become stops/hour, missed rate, cost/stop, service-line median, flags and annual savings using sum-over-sum.'],
  fuelKpi: ['KPI MART · FUEL-TYPE GRAIN', 'Fuel and maintenance sums become CNG-versus-diesel costs per kilometre. Labour is excluded from vehicle cost.']
};

document.querySelectorAll('[data-model]').forEach(node => node.addEventListener('click', () => {
  document.querySelectorAll('[data-model]').forEach(item => item.classList.toggle('active', item === node));
  const [kicker, body] = modelDetails[node.dataset.model];
  document.querySelector('#model-kicker').textContent = kicker;
  document.querySelector('#model-title').textContent = node.querySelector('strong').textContent;
  document.querySelector('#model-body').textContent = body;
}));

const relationshipLayer = document.querySelector('#relationship-lines');
const relationshipCanvas = document.querySelector('.clear-model');
const modelRelationships = [
  ['customer', 'pickup', '1', '*', false],
  ['route', 'pickup', '1', '*', false],
  ['truck', 'pickup', '1', '*', false],
  ['date', 'pickup', '1', '*', false],
  ['route', 'routeDay', '1', '*', false],
  ['truck', 'routeDay', '1', '*', false],
  ['date', 'routeDay', '1', '*', false],
  ['pickup', 'routeMart', 'Σ', '1', true],
  ['routeDay', 'routeMart', '1', '1', true]
];

function drawModelRelationships() {
  if (!relationshipLayer || !relationshipCanvas || window.innerWidth <= 700) return;
  const canvas = relationshipCanvas.getBoundingClientRect();
  relationshipLayer.replaceChildren();
  modelRelationships.forEach(([fromKey, toKey, fromCardinality, toCardinality, safe]) => {
    const from = document.querySelector(`[data-model="${fromKey}"]`)?.getBoundingClientRect();
    const to = document.querySelector(`[data-model="${toKey}"]`)?.getBoundingClientRect();
    if (!from || !to) return;
    const x1 = from.right - canvas.left;
    const y1 = from.top + from.height / 2 - canvas.top;
    const x2 = to.left - canvas.left;
    const y2 = to.top + to.height / 2 - canvas.top;
    const bend = Math.max(24, Math.abs(x2 - x1) * .45);
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('class', `relationship${safe ? ' safe' : ''}`);
    path.setAttribute('d', `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`);
    relationshipLayer.append(path);
    [[x1 + 8, y1 - 5, fromCardinality], [x2 - 13, y2 - 5, toCardinality]].forEach(([x, y, label]) => {
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', x); text.setAttribute('y', y);
      if (safe) text.setAttribute('class', 'safe');
      text.textContent = label;
      relationshipLayer.append(text);
    });
  });
}

window.addEventListener('load', drawModelRelationships);
window.addEventListener('resize', drawModelRelationships, { passive: true });
new ResizeObserver(drawModelRelationships).observe(relationshipCanvas);
setTimeout(drawModelRelationships, 800);

const observer = new IntersectionObserver(entries => {
  entries.forEach(entry => { if (entry.isIntersecting) entry.target.classList.add('visible'); });
}, { threshold: .1 });
document.querySelectorAll('.reveal').forEach(element => observer.observe(element));

const sections = [...document.querySelectorAll('section[id]')];
const links = [...document.querySelectorAll('.site-header nav a')];
window.addEventListener('scroll', () => {
  const current = sections.filter(section => section.getBoundingClientRect().top < 160).pop();
  links.forEach(link => link.style.color = current && link.getAttribute('href') === `#${current.id}` ? '#101923' : '');
}, { passive: true });
