// QuoteSure dashboard. Plain JavaScript: talks to the FastAPI backend on the same server.

// ---------- Helpers ----------
const $ = (sel) => document.querySelector(sel);
const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });
const inr2 = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const money = (x, f) => (x == null ? '–' : `${x < 0 ? '−' : ''}₹${f.format(Math.abs(x))}`);
const rs = (x) => money(x, inr);
const rs2 = (x) => money(x, inr2);
const pct = (x) => (x == null ? '–' : `${x > 0 ? '+' : ''}${x.toFixed(1)}%`);

// Everything shown from the server (including AI text) goes through esc() so it can't inject HTML
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  let body = null;
  try { body = await res.json(); } catch { /* not JSON */ }
  if (!res.ok) {
    const detail = body && body.detail;
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${res.status})`);
  }
  return body;
}
const postJSON = (path, data) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });

let toastTimer;
function toast(text) {
  const t = $('#toast');
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 4000);
}

let materials = [];
let suppliers = [];

// ---------- Navigation ----------
const views = ['overview', 'check', 'price', 'ask'];
function show(view) {
  if (!views.includes(view)) view = 'overview';
  views.forEach((v) => { $(`#view-${v}`).hidden = v !== view; });
  document.querySelectorAll('nav a').forEach((a) => {
    if (a.dataset.view === view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  if (view === 'overview') loadOverview();
  window.scrollTo(0, 0);
}
window.addEventListener('hashchange', () => show(location.hash.slice(1)));

// ---------- Overview ----------
async function loadOverview(freshAlertIds = []) {
  // Run the price watch first, so alerts always match today's prices
  await api('/alerts/check', { method: 'POST' });
  const [dash, sups, quotes, alerts] = await Promise.all([
    api('/dashboard'), api('/suppliers'), api('/quotes?status=open'), api('/alerts'),
  ]);
  $('#factory-name').textContent = dash.factory_name;
  $('#fig-overpaid').textContent = rs(dash.overpaid_90_days);
  $('#fig-overpaid-note').innerHTML = dash.worst_supplier
    ? `Most of it to <b>${esc(dash.worst_supplier)}</b>: ${rs(dash.worst_supplier_overpaid)}`
    : '';
  $('#fig-risk').textContent = `${dash.open_quotes_at_risk} of ${dash.open_quotes}`;
  $('#fig-alerts').textContent = dash.unread_alerts;

  renderAlerts(alerts, freshAlertIds);
  renderSuppliers(sups);
  renderQuotes(quotes);
  loadChart();
}

function renderAlerts(alerts, freshIds) {
  const list = $('#alerts');
  if (!alerts.length) {
    list.innerHTML = '<li class="empty">No alerts. Every open quote still makes a healthy profit at today’s prices.</li>';
    return;
  }
  const kind = { loss_risk: 'Now a loss', thin_margin: 'Thin margin' };
  list.innerHTML = alerts.map((a) => `
    <li class="alert ${esc(a.type)} ${a.is_read ? 'read' : ''} ${freshIds.includes(a.id) ? 'fresh' : ''}">
      <span class="alert-kind">${esc(kind[a.type] || a.type)}</span>
      <span class="alert-text">${esc(a.message)}</span>
      ${a.is_read ? '' : `<button data-read="${a.id}">Mark as read</button>`}
    </li>`).join('');
}

function renderSuppliers(sups) {
  const max = Math.max(...sups.map((s) => s.avg_markup_percent || 0), 1);
  $('#suppliers-table tbody').innerHTML = sups.map((s) => {
    const m = s.avg_markup_percent;
    return `<tr>
      <td><b>${esc(s.name)}</b></td>
      <td>${esc(s.city)}</td>
      <td class="num">${s.purchase_count}</td>
      <td><div class="bar"><div class="bar-track"><div class="bar-fill ${m > 6 ? 'high' : ''}" style="width:${Math.max(0, (m || 0) / max * 100)}%"></div></div>
        <span class="bar-text ${m > 6 ? 'neg' : ''}">${pct(m)}</span></div></td>
    </tr>`;
  }).join('');
}

function renderQuotes(quotes) {
  const body = $('#quotes-table tbody');
  if (!quotes.length) { body.innerHTML = '<tr><td colspan="8" class="empty">No open quotes.</td></tr>'; return; }
  body.innerHTML = quotes.map((q) => {
    const today = q.today_profit;
    const cls = today < 0 ? 'neg' : (today / q.today_total_cost * 100 < 7.5 ? 'thin' : 'pos');
    return `<tr>
      <td>Q-${String(q.id).padStart(4, '0')}</td>
      <td>${esc(q.customer_name)}</td>
      <td>${esc(q.part_name)}</td>
      <td class="num">${inr.format(q.quantity)}</td>
      <td class="num">${rs(q.quoted_price)}</td>
      <td class="num ${q.profit < 0 ? 'neg' : ''}">${rs(q.profit)}</td>
      <td class="num ${cls}">${rs(today)}</td>
      <td class="num"><a class="link" href="/quotes/${q.id}/pdf" target="_blank" rel="noopener">PDF</a></td>
    </tr>`;
  }).join('');
}

async function loadChart() {
  const id = $('#chart-material').value;
  const data = await api(`/materials/${id}/prices?days=90`);
  const pts = data.prices;
  if (!pts.length) { $('#chart').innerHTML = '<p class="empty">No prices yet.</p>'; return; }
  const W = 560, H = 230, L = 52, R = 70, T = 14, B = 28;
  const ys = pts.map((p) => p.price_per_unit);
  const lo = Math.min(...ys), hi = Math.max(...ys), pad = (hi - lo) * 0.12 || 1;
  const y0 = lo - pad, y1 = hi + pad;
  const X = (i) => L + (i / (pts.length - 1)) * (W - L - R);
  const Y = (v) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)} ${Y(p.price_per_unit).toFixed(1)}`).join(' ');
  const last = pts[pts.length - 1], first = pts[0];
  const change = (last.price_per_unit - first.price_per_unit) / first.price_per_unit * 100;
  const ticks = [y0 + pad, (y0 + y1) / 2, y1 - pad];
  const fmtDate = (d) => new Date(d + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
  $('#chart-sub').textContent = `₹ per kg over 90 days: ${pct(change)} overall`;
  $('#chart').innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(data.material_name)} price, now ${rs2(last.price_per_unit)} per kg">
      ${ticks.map((t) => `<line x1="${L}" x2="${W - R}" y1="${Y(t)}" y2="${Y(t)}" stroke="#E3E8ED"/>
        <text x="${L - 8}" y="${Y(t) + 4}" text-anchor="end" font-size="11" fill="#5D6B7A">${inr.format(t)}</text>`).join('')}
      <path d="${line}" fill="none" stroke="#1D3557" stroke-width="2" stroke-linejoin="round"/>
      <circle cx="${X(pts.length - 1)}" cy="${Y(last.price_per_unit)}" r="4" fill="#1D3557"/>
      <text x="${X(pts.length - 1) + 8}" y="${Y(last.price_per_unit) + 4}" font-size="12" font-weight="600" fill="#18222E">${rs2(last.price_per_unit)}</text>
      <text x="${L}" y="${H - 8}" font-size="11" fill="#5D6B7A">${fmtDate(first.date)}</text>
      <text x="${W - R}" y="${H - 8}" font-size="11" fill="#5D6B7A" text-anchor="end">${fmtDate(last.date)}</text>
    </svg>`;
}

$('#chart-material').addEventListener('change', loadChart);

$('#alerts').addEventListener('click', async (e) => {
  const id = e.target.dataset.read;
  if (!id) return;
  await api(`/alerts/${id}/read`, { method: 'POST' });
  loadOverview();
});

$('#btn-watch').addEventListener('click', async (e) => {
  e.target.disabled = true;
  try {
    const fresh = await api('/alerts/check', { method: 'POST' });
    toast(fresh.length ? `${fresh.length} new alert${fresh.length > 1 ? 's' : ''}` : 'No new alerts. Nothing has changed since the last check.');
    await loadOverview(fresh.map((a) => a.id));
  } finally { e.target.disabled = false; }
});

$('#btn-spike').addEventListener('click', async (e) => {
  e.target.disabled = true;
  try {
    const fresh = await postJSON('/materials/2/simulate-spike', { percent: 15 });
    toast(`MS Round Bar is now 15% dearer. ${fresh.length ? `${fresh.length} new alert${fresh.length > 1 ? 's' : ''}.` : 'No new alerts.'}`);
    await loadOverview(fresh.map((a) => a.id));
  } catch (err) { toast(err.message); } finally { e.target.disabled = false; }
});

// ---------- Check a supplier quote ----------
const fileInput = $('#check-file');
const drop = $('#drop');
fileInput.addEventListener('change', () => {
  $('#drop-title').textContent = fileInput.files[0] ? fileInput.files[0].name : 'Choose a quote, or drop it here';
});
['dragenter', 'dragover'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('over'); }));
['dragleave', 'drop'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove('over'); }));
drop.addEventListener('drop', (e) => {
  if (e.dataTransfer.files.length) { fileInput.files = e.dataTransfer.files; fileInput.dispatchEvent(new Event('change')); }
});

async function checkFile(file) {
  const btn = $('#check-btn');
  btn.disabled = true;
  btn.textContent = 'Reading the quote…';
  $('#check-result').innerHTML = '<div class="panel thinking">Gemini is reading the quote and QuoteSure is checking each rate. This takes a few seconds.</div>';
  const form = new FormData();
  form.append('file', file);
  if ($('#check-supplier').value) form.append('supplier_id', $('#check-supplier').value);
  try {
    renderCheck(await api('/buying/check-quote', { method: 'POST', body: form }));
  } catch (err) {
    $('#check-result').innerHTML = `<div class="panel"><b>Couldn’t check this quote.</b> ${esc(err.message)}
      <p class="note">If Gemini isn’t responding, run <code>python -m data.check_gemini</code> in the backend folder.</p></div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Check this quote';
  }
}

$('#check-form').addEventListener('submit', (e) => {
  e.preventDefault();
  if (!fileInput.files[0]) { toast('Choose a quote file first.'); return; }
  checkFile(fileInput.files[0]);
});

document.querySelectorAll('[data-sample]').forEach((b) => b.addEventListener('click', async () => {
  const name = b.dataset.sample;
  const blob = await (await fetch(`/samples/${name}`)).blob();
  $('#drop-title').textContent = name;
  checkFile(new File([blob], name, { type: blob.type }));
}));

function renderCheck(r) {
  const word = { overpriced: 'Overpriced', fair: 'Fair price', good_deal: 'Good deal', unknown: 'Can’t judge' }[r.verdict] || r.verdict;
  const verdictWord = { overpriced: 'Overpriced', fair: 'Fair', good_deal: 'Good deal', unknown: 'Unknown material' };
  const rows = r.items.map((i) => `<tr>
      <td>${esc(i.description)}</td>
      <td>${esc(i.material_name || 'Not matched')}</td>
      <td class="num">${inr.format(i.quantity_kg)} kg</td>
      <td class="num">${rs2(i.price_per_kg)}</td>
      <td class="num">${rs2(i.market_price)}</td>
      <td class="num ${i.difference_percent > 6 ? 'neg' : i.difference_percent < 0 ? 'pos' : ''}">${pct(i.difference_percent)}</td>
      <td>${esc(verdictWord[i.verdict] || i.verdict)}</td>
      <td class="num">${i.potential_saving ? rs(i.potential_saving) : '–'}</td>
      <td>${i.best_supplier ? `${esc(i.best_supplier)} <span class="note">(${pct(i.best_supplier_markup)})</span>` : '–'}</td>
    </tr>`).join('');
  const msg = r.negotiation_message;
  $('#check-result').innerHTML = `
    <div class="verdict ${esc(r.verdict)}">
      <div class="verdict-word">${esc(word)}</div>
      <div class="verdict-saving">${r.potential_saving > 0 ? `<b>${rs(r.potential_saving)}</b><span>you can save at a fair price</span>` : '<b>₹0</b><span>nothing to negotiate</span>'}</div>
      <div class="verdict-who">${esc(r.supplier_name || 'Unknown supplier')} · ${esc(r.file_name)}</div>
      <p class="verdict-summary">${esc(r.summary.replace(/^[A-Za-z ]{3,20}:\s*/, ''))}</p>
    </div>
    <div class="panel">
      <h2>Line by line</h2>
      <p class="panel-sub">Rates are ₹ per kg before GST, compared with today’s market price</p>
      <div style="overflow-x:auto"><table class="table">
        <thead><tr><th>On the quote</th><th>Matched to</th><th class="num">Qty</th><th class="num">Quoted</th><th class="num">Market</th><th class="num">Difference</th><th>Verdict</th><th class="num">Saving</th><th>Usually cheapest</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
      ${r.ai_notes ? `<p class="note">The AI noted: ${esc(r.ai_notes)}</p>` : ''}
    </div>
    ${msg ? `<div class="panel">
      <h2>Reply to ${esc(r.supplier_name || 'the supplier')}</h2>
      <p class="panel-sub">Target rates are worked out by QuoteSure; the wording is drafted by AI. Edit it before sending if you like.</p>
      <div class="message" id="nego-msg">${esc(msg)}</div>
      <div class="row-actions">
        <button class="btn" id="copy-msg">Copy message</button>
        <a class="btn ghost" href="https://wa.me/?text=${encodeURIComponent(msg)}" target="_blank" rel="noopener">Open in WhatsApp</a>
      </div>
    </div>` : ''}`;
  const copy = $('#copy-msg');
  if (copy) copy.addEventListener('click', async () => { await navigator.clipboard.writeText(msg); toast('Message copied'); });
  $('#check-result').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ---------- Price an order ----------
let lastEstimate = null;
$('#price-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const owner = parseFloat($('#p-owner').value);
  const req = {
    material_id: parseInt($('#p-material').value, 10),
    quantity: parseInt($('#p-qty').value, 10),
    weight_per_piece_kg: parseFloat($('#p-weight').value),
    machine_hours_per_piece: parseFloat($('#p-machine').value) || 0,
    labour_hours_per_piece: parseFloat($('#p-labour').value) || 0,
    owner_price_per_piece: owner > 0 ? owner : null,
  };
  try {
    const b = await postJSON('/quotes/estimate', req);
    lastEstimate = { req, b };
    renderEstimate(req, b);
  } catch (err) { toast(err.message); }
});

function renderEstimate(req, b) {
  const parts = [
    ['Material (incl. scrap)', b.material_cost, '#1D3557'],
    ['Machine + power', b.machine_cost, '#4F6D93'],
    ['Labour', b.labour_cost, '#8FA6C1'],
    ['Overhead', b.overhead_cost, '#C5CDD6'],
  ];
  const callout = {
    loss: [`Your price loses ${rs(-b.owner_profit)}`, `At ${rs2(req.owner_price_per_piece)} a piece you are below the true cost of ${rs2(b.cost_per_piece)}.`],
    thin_margin: [`Only ${b.owner_margin_percent.toFixed(1)}% profit`, `At ${rs2(req.owner_price_per_piece)} a piece you make ${rs(b.owner_profit)}, under half your target margin.`],
    healthy: [`Healthy: ${b.owner_margin_percent.toFixed(1)}% profit`, `At ${rs2(req.owner_price_per_piece)} a piece you make ${rs(b.owner_profit)} on this order.`],
    no_price_given: ['Here is your safe price', 'Enter the price you were planning to quote to check it.'],
  }[b.verdict];
  const riseCost = b.cost_if_material_up_10 / req.quantity;
  $('#price-result').innerHTML = `
    <div class="panel">
      <div class="callout ${esc(b.verdict)}"><b>${esc(callout[0])}</b><span>${esc(callout[1])}</span></div>
      <div class="price-pair">
        <div><b>${rs2(b.cost_per_piece)}</b><span>true cost per piece (break-even)</span></div>
        <div><b>${rs2(b.recommended_price_per_piece)}</b><span>safe price per piece, with your target margin</span></div>
      </div>
      <h2>Where the money goes</h2>
      <div class="breakdown" aria-hidden="true">${parts.map(([, v, c]) => `<div style="width:${v / b.total_cost * 100}%;background:${c}"></div>`).join('')}</div>
      <div class="legend">
        ${parts.map(([n, v, c]) => `<span class="swatch" style="background:${c}"></span><span>${n}</span><span class="num">${rs(v)}</span>`).join('')}
        <span></span><span class="total">True cost for ${inr.format(req.quantity)} pieces</span><span class="num total">${rs(b.total_cost)}</span>
      </div>
      <p class="note">${esc(b.material_name)} at today’s ${rs2(b.material_price_used)}/kg; you need ${b.raw_material_kg_per_piece} kg per piece with scrap. If this material rises 10% before you buy it, the true cost becomes ${rs2(riseCost)} a piece.</p>
      <div class="save-row">
        <label class="field"><span>Customer</span><input id="s-customer" placeholder="e.g. Deccan Auto Components"></label>
        <label class="field"><span>Part</span><input id="s-part" placeholder="e.g. Mounting bracket"></label>
        <button class="btn" id="save-quote">Save at safe price</button>
      </div>
      <div id="save-done"></div>
    </div>`;
  $('#save-quote').addEventListener('click', saveQuote);
}

async function saveQuote() {
  const customer = $('#s-customer').value.trim();
  const part = $('#s-part').value.trim();
  if (!customer || !part) { toast('Enter the customer and the part first.'); return; }
  try {
    const q = await postJSON('/quotes', { ...lastEstimate.req, owner_price_per_piece: null, customer_name: customer, part_name: part });
    $('#save-done').innerHTML = `<p class="note">Saved as Q-${String(q.id).padStart(4, '0')} at ${rs2(q.price_per_piece)} a piece. <a class="link" href="/quotes/${q.id}/pdf" target="_blank" rel="noopener">Open the quotation PDF</a></p>`;
    toast('Quotation saved');
  } catch (err) { toast(err.message); }
}

// ---------- Ask QuoteSure ----------
const history = [];
function addMsg(role, html, cls = '') {
  const div = document.createElement('div');
  div.className = `msg ${role} ${cls}`;
  div.innerHTML = html;
  $('#chat').appendChild(div);
  $('#chat').scrollTop = $('#chat').scrollHeight;
  return div;
}

async function ask(text) {
  if (!text.trim()) return;
  $('#suggestions').hidden = true;
  addMsg('user', esc(text));
  const pending = addMsg('assistant', '<span class="thinking">Looking it up…</span>');
  $('#chat-input').value = '';
  try {
    const r = await postJSON('/agent/chat', { message: text, history });
    history.push({ role: 'user', text }, { role: 'assistant', text: r.reply });
    const steps = r.steps.length ? `<details class="steps"><summary>Used ${r.steps.length} tool${r.steps.length > 1 ? 's' : ''}</summary><ol>
      ${r.steps.map((s) => `<li><code>${esc(s.tool)}</code>: ${esc(s.result)}</li>`).join('')}</ol></details>` : '';
    pending.innerHTML = esc(r.reply) + steps;
  } catch (err) {
    pending.classList.add('error');
    pending.textContent = `Couldn’t get an answer: ${err.message}`;
  }
}
$('#chat-form').addEventListener('submit', (e) => { e.preventDefault(); ask($('#chat-input').value); });
document.querySelectorAll('#suggestions .chip').forEach((c) => c.addEventListener('click', () => ask(c.textContent)));

// ---------- Start ----------
(async function start() {
  try {
    let settings;
    [materials, suppliers, settings] = await Promise.all([api('/materials'), api('/suppliers'), api('/settings')]);
    $('#factory-name').textContent = settings.factory_name;
    const opts = materials.map((m) => `<option value="${m.id}">${esc(m.name)} ${esc(m.grade)} (${rs2(m.latest_price)}/kg)</option>`).join('');
    $('#chart-material').innerHTML = opts;
    $('#p-material').innerHTML = opts;
    $('#chart-material').value = '2';   // MS Round Bar: the material the price-rise demo moves
    $('#check-supplier').innerHTML += suppliers.map((s) => `<option value="${s.id}">${esc(s.name)}</option>`).join('');
  } catch (err) {
    toast(`Couldn’t reach the server: ${err.message}`);
  }
  show(location.hash.slice(1) || 'overview');
})();
