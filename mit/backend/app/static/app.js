const $ = (id) => document.getElementById(id);
const state = { symbol: 'SPY', socket: null, chart: null, candleSeries: null, volumeSeries: null, lines: [], alertIds: new Set(), alarmEnabled: false, audioContext: null, hmMetric: 'gex',
  trMetric: 'gex', trChart: null, trCandle: null, trSpotLine: null, trPriceSeries: null, trLines: [], trSpot: null, trData: null, trKeyLevels: true, trObserver: null,
  trTime: null, trCol: 0 };

function fmt(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return Number(value).toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits });
}
function compact(value) {
  const n = Number(value || 0), a = Math.abs(n);
  if (a >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return fmt(n, 0);
}
function cssDirection(direction) { return direction === 'up' ? 'positive' : direction === 'down' ? 'negative' : ''; }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }

async function bootstrap() {
  const health = await fetch('/api/health').then(r => r.json());
  $('mode-badge').textContent = health.mode;
  $('symbol-select').innerHTML = health.watchlist.map(s => `<option>${escapeHtml(s)}</option>`).join('');
  state.symbol = health.watchlist.includes('SPY') ? 'SPY' : health.watchlist[0];
  $('symbol-select').value = state.symbol;
  createChart();
  createTraceChart();
  connect();
  loadHeatmap();
  loadTrace();
  $('symbol-select').addEventListener('change', () => { state.symbol = $('symbol-select').value; connect(); loadHeatmap(); loadTrace(); });
  $('alarm-button').addEventListener('click', enableAlarm);
  $('refresh-button').addEventListener('click', async () => {
    const payload = await fetch(`/api/snapshot/${encodeURIComponent(state.symbol)}?force=true`).then(r => r.json());
    render(payload);
  });
  $('hm-refresh').addEventListener('click', loadHeatmap);
  $('hm-toggle').addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-metric]'); if (!btn) return;
    state.hmMetric = btn.dataset.metric;
    [...$('hm-toggle').children].forEach(b => b.classList.toggle('active', b === btn));
    loadHeatmap();
  });
  $('tr-refresh').addEventListener('click', loadTrace);
  $('tr-toggle').addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-metric]'); if (!btn) return;
    state.trMetric = btn.dataset.metric;
    [...$('tr-toggle').children].forEach(b => b.classList.toggle('active', b === btn));
    loadTrace();
  });
  $('tr-keylevels').addEventListener('click', (e) => {
    state.trKeyLevels = !state.trKeyLevels;
    e.currentTarget.classList.toggle('active', state.trKeyLevels);
    if (state.trData) renderTracePriceLines(state.trData);
  });
  wireScrubber();
}

// Diverging scale: teal/green positive, indigo/purple negative, symmetric around 0.
function divergingColor(value, maxAbs) {
  const base = [26, 48, 54], pos = [82, 178, 138], neg = [104, 82, 168];
  const t = maxAbs > 0 ? Math.max(-1, Math.min(1, value / maxAbs)) : 0;
  const f = Math.sign(t) * Math.pow(Math.abs(t), 0.5); // lift midtones for readability
  const target = f >= 0 ? pos : neg, k = Math.abs(f);
  const mix = base.map((c, i) => Math.round(c + (target[i] - c) * k));
  return `rgb(${mix[0]},${mix[1]},${mix[2]})`;
}
function fmtCell(v) {
  const k = v / 1000;
  const s = Math.abs(k).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return `${v < 0 ? '-$' : '$'}${s}K`;
}

async function loadHeatmap() {
  const sym = state.symbol;
  $('hm-symbol').textContent = sym;
  $('hm-metric-title').textContent = `${state.hmMetric.toUpperCase()} · strike × expiration`;
  const grid = $('hm-grid');
  grid.innerHTML = '<div class="empty">Loading…</div>';
  let data;
  try {
    data = await fetch(`/api/gex_heatmap/${encodeURIComponent(sym)}?metric=${state.hmMetric}`).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
  } catch (err) { grid.innerHTML = `<div class="empty">Heatmap unavailable (${escapeHtml(String(err.message || err))})</div>`; return; }
  if (sym !== state.symbol) return; // stale response, symbol changed
  renderHeatmap(data);
}

function renderHeatmap(data) {
  const grid = $('hm-grid');
  const exps = data.expirations || [], strikes = data.strikes || [], cells = data.cells || {};
  const q = data.quote || {};
  $('hm-price').textContent = q.last == null ? '—' : `$${fmt(q.last, q.last < 50 ? 3 : 2)}`;
  if (q.change_pct == null) { $('hm-change').textContent = '—'; $('hm-change').className = 'muted'; }
  else {
    const abs = q.last != null ? q.last * (q.change_pct / 100) / (1 + q.change_pct / 100) : null;
    $('hm-change').textContent = `${q.change_pct >= 0 ? '+' : ''}${abs == null ? '' : fmt(abs) + ' '}(${q.change_pct >= 0 ? '+' : ''}${fmt(q.change_pct)}%)`;
    $('hm-change').className = q.change_pct > 0 ? 'positive' : q.change_pct < 0 ? 'negative' : 'muted';
  }
  $('hm-caveat').innerHTML = (data.caveats || []).map(escapeHtml).join(' · ');
  if (!exps.length || !strikes.length) { grid.innerHTML = '<div class="empty">No option-chain nodes</div>'; return; }

  const maxAbs = Object.values(cells).reduce((m, v) => Math.max(m, Math.abs(v)), 0);
  const spot = data.spot;
  const spotStrike = strikes.reduce((best, s) => Math.abs(s - spot) < Math.abs(best - spot) ? s : best, strikes[0]);
  const maxKey = data.max_cell ? `${String(data.max_cell.strike).replace(/\.0$/, '')}|${data.max_cell.expiration}` : null;
  grid.style.gridTemplateColumns = `72px repeat(${exps.length}, minmax(96px, 1fr))`;

  const frag = document.createDocumentFragment();
  const mk = (cls, text) => { const d = document.createElement('div'); d.className = cls; if (text != null) d.textContent = text; return d; };
  frag.appendChild(mk('hm-corner', 'Strike'));
  exps.forEach(e => frag.appendChild(mk('hm-colhead', e)));
  let spotRowhead = null;
  strikes.forEach(strike => {
    const isSpot = strike === spotStrike;
    const rh = mk('hm-rowhead' + (isSpot ? ' hm-spot' : ''), strike.toFixed(1));
    if (isSpot) spotRowhead = rh;
    frag.appendChild(rh);
    exps.forEach(exp => {
      const key = `${String(strike).replace(/\.0$/, '')}|${exp}`;
      const has = Object.prototype.hasOwnProperty.call(cells, key);
      const cell = mk('hm-cell' + (isSpot ? ' hm-spot' : ''));
      if (!has) { cell.classList.add('hm-empty'); frag.appendChild(cell); return; } // fail-loud: blank, no fabricated 0
      const v = cells[key];
      cell.style.background = divergingColor(v, maxAbs);
      if (key === maxKey) { cell.classList.add('hm-max'); cell.textContent = fmtCell(v) + '★'; }
      else cell.textContent = fmtCell(v);
      cell.title = `${strike.toFixed(1)} · ${exp}: ${fmtCell(v)}`;
      frag.appendChild(cell);
    });
  });
  grid.replaceChildren(frag);
  // centrar el mapa en el spot: ahi viven los colores divergentes (call+ arriba / put- abajo)
  if (spotRowhead) requestAnimationFrame(() => spotRowhead.scrollIntoView({ block: 'center' }));
}

// ---- TRACE-style intraday heatmap (strike × time) --------------------------------
const TR_WINDOW = 0.045; // visible price window around spot (±%); bands fill it top-to-bottom
const todayISO = () => new Date().toLocaleDateString('en-CA'); // YYYY-MM-DD, local session date

function createTraceChart() {
  const container = $('tr-chart');
  state.trChart = LightweightCharts.createChart(container, {
    layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#9a8fb8', fontFamily: 'Inter, system-ui, sans-serif' },
    grid: { vertLines: { color: 'rgba(160,140,200,.05)' }, horzLines: { color: 'rgba(160,140,200,.05)' } },
    rightPriceScale: { borderColor: 'rgba(160,140,200,.14)' },
    // Eje en hora LOCAL: los sellos del cubo son locales, un eje en UTC los contradice.
    timeScale: { borderColor: 'rgba(160,140,200,.14)', timeVisible: true, secondsVisible: false, rightOffset: 4,
      tickMarkFormatter: (t) => new Date(t * 1000).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }) },
    localization: { timeFormatter: (t) => new Date(t * 1000).toLocaleString('en-US', { hour12: false }) },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    autoSize: true,
  });
  const window_ = () => {
    if (!state.trSpot) return null; // no fabricated range
    return { priceRange: { minValue: state.trSpot * (1 - TR_WINDOW), maxValue: state.trSpot * (1 + TR_WINDOW) } };
  };
  state.trCandle = state.trChart.addSeries(LightweightCharts.CandlestickSeries, {
    upColor: '#3ad6b0', downColor: '#ff6178', borderUpColor: '#3ad6b0', borderDownColor: '#ff6178', wickUpColor: '#e9f0fa', wickDownColor: '#e9f0fa',
    autoscaleInfoProvider: window_,
  });
  // Spot medido en la cabecera de cada foto de cadena: es precio REAL de esa sesión, sin OHLC
  // inventado. Solo se dibuja si no hay velas de la misma sesión (fail-loud: nunca wicks falsas).
  state.trSpotLine = state.trChart.addSeries(LightweightCharts.LineSeries, {
    color: '#54d9ff', lineWidth: 2, priceLineVisible: false, lastValueVisible: false,
    autoscaleInfoProvider: window_,
  });
  state.trPriceSeries = state.trCandle;
  // Repaint the canvas whenever the chart geometry changes so bands stay aligned to the price axis.
  const repaint = () => { if (state.trData) paintTraceCanvas(state.trData); };
  state.trChart.timeScale().subscribeVisibleLogicalRangeChange(repaint);
  state.trObserver = new ResizeObserver(() => requestAnimationFrame(repaint));
  state.trObserver.observe($('tr-main'));
}

async function loadTrace() {
  const sym = state.symbol;
  const isGex = state.trMetric === 'gex';
  $('tr-symbol').textContent = sym;
  $('tr-title').textContent = `${isGex ? 'GEX' : 'Net OI'} by strike · time`;
  $('tr-left-title').textContent = `${isGex ? 'GEX' : 'Net OI'} by Strike`;
  let data;
  try {
    data = await fetch(`/api/trace/${encodeURIComponent(sym)}?metric=${state.trMetric}`).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
  } catch (err) {
    state.trTime = null; syncScrubber();
    $('tr-empty').hidden = false; $('tr-empty').style.display = '';
    $('tr-empty').textContent = `Trace unavailable (${String(err.message || err)})`;
    $('tr-bars').replaceChildren(); return;
  }
  if (sym !== state.symbol) return; // stale response, symbol changed
  renderTrace(data);
}

function renderTrace(data) {
  state.trData = data;
  state.trTime = (data.trace_time && (data.trace_time.columns || []).length) ? data.trace_time : null;
  // El panel muestra UNA sesión: si es la del cubo, la ventana de precio es la de ESE día.
  const sessionSpots = state.trTime ? state.trTime.columns.map(c => c.spot).filter(v => v != null) : [];
  state.trSpot = sessionSpots.length ? sessionSpots[sessionSpots.length - 1] : (data.spot || null);
  const q = data.quote || {};
  $('tr-price').textContent = q.last == null ? '—' : `$${fmt(q.last, q.last < 50 ? 3 : 2)}`;
  $('tr-change').textContent = q.change_pct == null ? '—' : `${q.change_pct >= 0 ? '+' : ''}${fmt(q.change_pct)}%`;
  $('tr-change').className = q.change_pct > 0 ? 'positive' : q.change_pct < 0 ? 'negative' : 'muted';
  const caveats = (data.caveats || []).slice();
  if (state.trTime && state.trTime.date !== todayISO()) {
    caveats.unshift(`Archived session ${state.trTime.date}: price window and bands are that day's; key levels come from the current chain.`);
  }
  $('tr-caveat').textContent = caveats.join(' · ');

  const candles = (data.candles || []).map(c => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close }));
  const track = (data.spot_track || []).filter(p => p.value != null).map(p => ({ time: p.time, value: p.value }));
  const hasCandles = candles.length > 0;
  const useTrack = !hasCandles && track.length > 0;
  state.trCandle.setData(candles);
  state.trSpotLine.setData(useTrack ? track : []);
  state.trPriceSeries = hasCandles ? state.trCandle : state.trSpotLine;
  const empty = hasCandles || useTrack ? '' :
    (state.trTime ? 'No price series for the archived session' : 'No candle data');
  $('tr-empty').textContent = empty;
  $('tr-empty').style.display = empty ? '' : 'none';  // style gana a cualquier CSS

  // Última columna con datos medidos; sin cubo el cursor no existe.
  const cols = state.trTime ? state.trTime.columns : [];
  let idx = cols.length - 1;
  while (idx > 0 && !cols[idx].has_data) idx -= 1;
  state.trCol = Math.max(0, idx);

  renderTracePriceLines(data);
  syncScrubber();
  renderTraceBars(data);
  requestAnimationFrame(() => { state.trChart.timeScale().fitContent(); paintTraceCanvas(data); });
}

// ---- time scrubber ---------------------------------------------------------------
function wireScrubber() {
  const track = $('tr-scrub-track');
  const pick = (ev) => {
    const cols = state.trTime ? state.trTime.columns : [];
    if (!cols.length) return;
    const rect = track.getBoundingClientRect();
    if (!rect.width) return;
    const t = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width));
    setScrubIndex(Math.round(t * (cols.length - 1)));
  };
  track.addEventListener('pointerdown', (ev) => {
    if (!state.trTime) return;
    track.setPointerCapture(ev.pointerId); pick(ev); ev.preventDefault();
  });
  track.addEventListener('pointermove', (ev) => { if (state.trTime && track.hasPointerCapture(ev.pointerId)) pick(ev); });
  track.addEventListener('pointerup', (ev) => { if (track.hasPointerCapture(ev.pointerId)) track.releasePointerCapture(ev.pointerId); });
  track.addEventListener('keydown', (ev) => {
    const cols = state.trTime ? state.trTime.columns : [];
    if (!cols.length) return;
    const step = { ArrowLeft: -1, ArrowRight: 1, PageUp: 6, PageDown: -6, Home: -1e6, End: 1e6 }[ev.key];
    if (step === undefined) return;
    setScrubIndex(state.trCol + step); ev.preventDefault();
  });
}

function setScrubIndex(index) {
  const cols = state.trTime ? state.trTime.columns : [];
  if (!cols.length) return;
  const next = Math.max(0, Math.min(cols.length - 1, index));
  if (next === state.trCol) return;
  state.trCol = next;
  syncScrubber();
  renderTraceBars(state.trData);
  paintTraceCanvas(state.trData);
}

function syncScrubber() {
  const wrap = $('tr-scrubber'), track = $('tr-scrub-track'), badge = $('tr-axis-badge');
  const measured = !!state.trTime;
  const cols = measured ? state.trTime.columns : [];
  wrap.classList.toggle('disabled', !measured);
  badge.textContent = measured ? 'measured' : 'flat';
  badge.className = `tr-axis-badge ${measured ? 'measured' : 'flat'}`;
  const pct = measured && cols.length > 1 ? (state.trCol / (cols.length - 1)) * 100 : 0;
  $('tr-scrub-fill').style.width = `${pct}%`;
  $('tr-scrub-handle').style.left = `${pct}%`;
  track.setAttribute('aria-valuemin', '0');
  track.setAttribute('aria-valuemax', String(Math.max(0, cols.length - 1)));
  track.setAttribute('aria-valuenow', String(measured ? state.trCol : 0));
  track.setAttribute('aria-disabled', measured ? 'false' : 'true');
  track.tabIndex = measured ? 0 : -1;
  if (!measured) {
    track.setAttribute('aria-valuetext', 'no measured session');
    $('tr-scrub-label').textContent = `Time scrubber inactive — no measured cube for ${state.symbol} (run scripts/trace_cube.py ${state.symbol})`;
    return;
  }
  const col = cols[state.trCol] || {};
  const gp = col.greeks_ok_pct;
  const detail = col.has_data
    ? `spot ${col.spot == null ? '—' : fmt(col.spot)}${gp == null ? '' : ` · greeks ${(gp * 100).toFixed(0)}%`}`
    : 'no measured greeks in this snapshot';
  track.setAttribute('aria-valuetext', `${col.label || ''} ${detail}`);
  $('tr-scrub-label').textContent = `${state.trTime.date} · snapshot ${state.trCol + 1}/${cols.length} @ ${col.label || '—'} · ${detail}`;
}

function traceColumnValues() {
  /** Valores de la columna seleccionada: {strike: value}. null si no hay eje medido. */
  if (!state.trTime) return null;
  const col = state.trTime.columns[state.trCol];
  if (!col || !col.has_data) return {};
  const out = {};
  const suffix = `|${col.epoch}`;
  for (const [key, value] of Object.entries(state.trTime.cells)) {
    if (key.endsWith(suffix)) out[key.slice(0, -suffix.length)] = value;
  }
  return out;
}

function renderTracePriceLines(data) {
  state.trLines.forEach(({ series, line }) => series.removePriceLine(line));
  state.trLines = [];
  const series = state.trPriceSeries || state.trCandle;
  const legend = [];
  const lv = data.levels || {};
  const defs = state.trKeyLevels ? [
    ['Call wall', lv.call_wall, '#ff6178', 2, LightweightCharts.LineStyle.Solid],
    ['Put wall', lv.put_wall, '#3ad6b0', 2, LightweightCharts.LineStyle.Solid],
    ['Gamma flip', lv.gamma_flip, '#ad8cff', 2, LightweightCharts.LineStyle.Solid],
    ['Max pain', lv.max_pain, '#ffbe4f', 1, LightweightCharts.LineStyle.Dotted],
    // Implied move = ATM straddle MEDIDO; sin él, el orchestrator no manda estos campos.
    ['Implied move +', lv.implied_move_up, '#54d9ff', 1, LightweightCharts.LineStyle.LargeDashed],
    ['Implied move −', lv.implied_move_dn, '#54d9ff', 1, LightweightCharts.LineStyle.LargeDashed],
    ['Last close', lv.last_close, '#8494aa', 1, LightweightCharts.LineStyle.Dashed],
  ] : [];
  defs.forEach(([title, price, color, width, style]) => {
    if (price == null) return;
    state.trLines.push({ series, line: series.createPriceLine({ price, color, lineWidth: width, lineStyle: style, axisLabelVisible: true, title }) });
    if (title !== 'Implied move −') legend.push(`<span style="--color:${color}">${escapeHtml(title === 'Implied move +' ? `Implied move ±${fmt(lv.implied_move)}` : title)}</span>`);
  });
  // La cotización viva solo tiene sentido sobre la sesión de hoy; con una sesión archivada
  // el precio de esa sesión ya lo dibuja el spot track medido.
  const spot = (state.trTime && state.trTime.date !== todayISO()) ? null : (data.quote && data.quote.last);
  if (spot != null) {
    state.trLines.push({ series, line: series.createPriceLine({ price: spot, color: '#54d9ff', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: 'Price' }) });
    legend.push(`<span style="--color:#54d9ff">Current price</span>`);
  }
  legend.push(`<span style="--color:#52b28a">${data.metric === 'gex' ? 'Positive GEX' : 'Net calls'}</span>`);
  legend.push(`<span style="--color:#6852a8">${data.metric === 'gex' ? 'Negative GEX' : 'Net puts'}</span>`);
  $('tr-legend').innerHTML = legend.join('');
}

// Row geometry (y) shared by both paths: [{strike, y, h}] for the visible price axis.
function traceRows(strikes) {
  const series = state.trPriceSeries || state.trCandle;
  const asc = strikes.slice().sort((a, b) => a - b);
  if (!asc.length || series.priceToCoordinate(asc[0]) == null) return []; // no price scale yet
  const rows = [];
  for (let i = 0; i < asc.length; i++) {
    const s = asc[i];
    const upP = i < asc.length - 1 ? (s + asc[i + 1]) / 2 : s + (i > 0 ? (s - asc[i - 1]) / 2 : s * 0.001);
    const loP = i > 0 ? (asc[i - 1] + s) / 2 : s - (asc.length > 1 ? (asc[i + 1] - s) / 2 : s * 0.001);
    const yTop = series.priceToCoordinate(upP), yBot = series.priceToCoordinate(loP);
    if (yTop == null || yBot == null) continue;
    rows.push({ strike: s, y: Math.min(yTop, yBot), h: Math.abs(yBot - yTop) + 1 });
  }
  return rows;
}

const cellAt = (map, strike) => map[`${strike}`.replace(/\.0$/, '')] ?? map[`${strike}`];

// Paint the metric onto the canvas: one column per archived chain snapshot when the time axis
// is MEASURED, otherwise one flat band per strike (and the caveat/badge says it is flat).
function paintTraceCanvas(data) {
  const canvas = $('tr-canvas'), main = $('tr-main');
  const w = main.clientWidth, h = main.clientHeight;
  if (!w || !h) return;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  if (state.trTime) { paintTraceColumns(ctx, w, h); return; }

  const byStrike = data.by_strike || {};
  const rows = traceRows(data.strikes || []);
  if (!rows.length) return;
  const maxAbs = Object.values(byStrike).reduce((m, v) => Math.max(m, Math.abs(v)), 0);
  rows.forEach(r => {
    if (r.y + r.h < 0 || r.y > h) return; // off-screen
    ctx.fillStyle = divergingColor(cellAt(byStrike, r.strike) ?? 0, maxAbs);
    ctx.fillRect(0, r.y, w, r.h);
  });
}

// timeToCoordinate only answers for times that ARE in the series; snapshot epochs (09:07:11)
// are not bar timestamps. Anchor on the series' own times and interpolate piecewise-linearly
// in bar index — no invented axis, just the chart's own geometry read between its anchors.
function traceTimeMapper() {
  const data = state.trData || {};
  const times = (data.candles || []).length
    ? data.candles.map(c => c.time)
    : (data.spot_track || []).map(p => p.time);
  const ts = state.trChart.timeScale();
  const anchors = [];
  for (const t of times) { const x = ts.timeToCoordinate(t); if (x != null) anchors.push([t, x]); }
  if (anchors.length < 2) return null;
  anchors.sort((a, b) => a[0] - b[0]);
  const lerp = (t, [t0, x0], [t1, x1]) => t1 === t0 ? x0 : x0 + (x1 - x0) * (t - t0) / (t1 - t0);
  return (t) => {
    if (t <= anchors[0][0]) return lerp(t, anchors[0], anchors[1]);
    const n = anchors.length;
    if (t >= anchors[n - 1][0]) return lerp(t, anchors[n - 2], anchors[n - 1]);
    let lo = 0, hi = n - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (anchors[mid][0] <= t) lo = mid; else hi = mid; }
    return lerp(t, anchors[lo], anchors[hi]);
  };
}

function paintTraceColumns(ctx, w, h) {
  const tt = state.trTime;
  const rows = traceRows(tt.strikes || []);
  if (!rows.length) return;
  const toX = traceTimeMapper();
  if (!toX) return; // sin serie de precio no hay eje: no se inventa uno
  const xs = tt.columns.map(c => toX(c.epoch));
  const known = xs.filter(x => x != null);
  if (!known.length) return; // cube epochs outside the rendered session: nothing faked
  const diffs = [];
  for (let i = 1; i < known.length; i++) diffs.push(Math.abs(known[i] - known[i - 1]));
  const dw = diffs.length ? diffs.sort((a, b) => a - b)[Math.floor(diffs.length / 2)] : w / known.length;
  const maxAbs = Object.values(tt.cells).reduce((m, v) => Math.max(m, Math.abs(v)), 0);
  const byCol = tt.columns.map(c => {
    const map = {};
    const suffix = `|${c.epoch}`;
    for (const [key, value] of Object.entries(tt.cells)) {
      if (key.endsWith(suffix)) map[key.slice(0, -suffix.length)] = value;
    }
    return map;
  });
  for (let i = 0; i < tt.columns.length; i++) {
    const x = xs[i];
    if (x == null) continue;
    const prev = i > 0 && xs[i - 1] != null ? xs[i - 1] : null;
    const next = i < xs.length - 1 && xs[i + 1] != null ? xs[i + 1] : null;
    const left = prev != null ? (prev + x) / 2 : x - dw / 2;
    const right = next != null ? (x + next) / 2 : x + dw / 2;
    if (right < 0 || left > w) continue;
    const map = byCol[i];
    rows.forEach(r => {
      if (r.y + r.h < 0 || r.y > h) return;
      const v = cellAt(map, r.strike);
      if (v === undefined) return; // sin dato medido en esa foto: se queda en blanco, no en cero
      ctx.fillStyle = divergingColor(v, maxAbs);
      ctx.fillRect(left, r.y, Math.max(1, right - left), r.h);
    });
  }
  const cx = xs[state.trCol];
  if (cx == null) return;
  ctx.strokeStyle = 'rgba(255,255,255,.75)';
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(Math.round(cx) + .5, 0); ctx.lineTo(Math.round(cx) + .5, h); ctx.stroke();
}

function renderTraceBars(data) {
  const col = state.trTime ? state.trTime.columns[state.trCol] : null;
  const colValues = traceColumnValues();          // null sin eje medido
  const byStrike = colValues || data.by_strike || {};
  const spot = (col && col.spot) || data.spot || 0;
  const isGex = data.metric === 'gex';
  const stamp = col ? ` · ${col.label}` : '';
  $('tr-left-title').textContent = `${isGex ? 'GEX' : 'Net OI'} by Strike${stamp}`;
  // Only the visible window (matches the heatmap), descending so top = high strike.
  const lo = spot * (1 - TR_WINDOW), hi = spot * (1 + TR_WINDOW);
  const universe = state.trTime ? state.trTime.strikes : (data.strikes || []);
  const rows = universe.filter(s => s >= lo && s <= hi && cellAt(byStrike, s) !== undefined).sort((a, b) => b - a);
  if (!rows.length) {
    $('tr-bars').replaceChildren(mkEmpty(col && !col.has_data
      ? `No measured greeks in the ${col.label} snapshot`
      : 'No strikes in window'));
    return;
  }
  const maxAbs = rows.reduce((m, s) => Math.max(m, Math.abs(cellAt(byStrike, s))), 0) || 1;
  const spotStrike = rows.reduce((best, s) => Math.abs(s - spot) < Math.abs(best - spot) ? s : best, rows[0]);
  const frag = document.createDocumentFragment();
  rows.forEach(s => {
    const v = cellAt(byStrike, s);
    const pct = Math.min(50, Math.abs(v) / maxAbs * 50);
    const row = document.createElement('div'); row.className = 'tr-bar-row';
    const lab = document.createElement('div'); lab.className = 'tr-bar-strike' + (s === spotStrike ? ' tr-spot' : ''); lab.textContent = s.toFixed(s < 50 ? 1 : 0);
    const track = document.createElement('div'); track.className = 'tr-bar-track';
    const fill = document.createElement('div'); fill.className = 'tr-bar-fill ' + (v >= 0 ? 'pos' : 'neg'); fill.style.width = `${pct}%`;
    fill.title = `${s}${stamp}: ${isGex ? compact(v) : fmt(v, 0)}`;
    track.appendChild(fill); row.append(lab, track); frag.appendChild(row);
  });
  $('tr-bars').replaceChildren(frag);
}

function mkEmpty(text) {
  const d = document.createElement('div'); d.className = 'empty'; d.textContent = text; return d;
}

function createChart() {
  const container = $('price-chart');
  state.chart = LightweightCharts.createChart(container, {
    layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#8292a8', fontFamily: 'Inter, system-ui, sans-serif' },
    grid: { vertLines: { color: 'rgba(132,148,170,.08)' }, horzLines: { color: 'rgba(132,148,170,.08)' } },
    rightPriceScale: { borderColor: 'rgba(132,148,170,.14)' },
    timeScale: { borderColor: 'rgba(132,148,170,.14)', timeVisible: true, secondsVisible: false, rightOffset: 8 },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    autoSize: true,
  });
  state.candleSeries = state.chart.addSeries(LightweightCharts.CandlestickSeries, {
    upColor: '#32d6a0', downColor: '#ff6178', borderUpColor: '#32d6a0', borderDownColor: '#ff6178', wickUpColor: '#32d6a0', wickDownColor: '#ff6178',
  });
  state.volumeSeries = state.chart.addSeries(LightweightCharts.HistogramSeries, {
    priceFormat: { type: 'volume' }, priceScaleId: '', color: 'rgba(96,165,250,.3)',
  });
  state.volumeSeries.priceScale().applyOptions({ scaleMargins: { top: .82, bottom: 0 } });
}

function connect() {
  if (state.socket) state.socket.close();
  setConnection('pending', 'Connecting');
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  const socket = new WebSocket(`${protocol}://${location.host}/ws/${encodeURIComponent(state.symbol)}`);
  state.socket = socket;
  socket.onopen = () => setConnection('live', 'Live');
  socket.onmessage = event => render(JSON.parse(event.data));
  socket.onerror = () => setConnection('offline', 'Fallback');
  socket.onclose = () => { setConnection('offline', 'Disconnected'); setTimeout(() => { if (state.socket === socket) connect(); }, 2500); };
}
function setConnection(mode, label) { const pill = $('connection-pill'); pill.className = `pill ${mode}`; pill.innerHTML = `<span></span>${label}`; }

function render(data) {
  renderQuote(data);
  renderChart(data);
  renderSignals(data.signals);
  renderDealer(data.dealer);
  renderGex(data.dealer.gex_by_strike || {});
  renderMagnets(data.dealer.magnets || [], data.quote.last);
  renderShock(data.shock);
  renderBook(data.book);
  renderFlows(data.flows || []);
  renderWeekly(data.weekly || []);
  renderAlerts(data.alerts || []);
  renderProviders(data.provider_status || []);
}

function renderQuote(data) {
  const q = data.quote;
  $('quote-symbol').textContent = q.symbol;
  $('quote-last').textContent = fmt(q.last, q.last < 50 ? 3 : 2);
  $('quote-change').textContent = `${q.change_pct >= 0 ? '+' : ''}${fmt(q.change_pct)}%`;
  $('quote-change').className = q.change_pct > 0 ? 'positive' : q.change_pct < 0 ? 'negative' : 'muted';
  $('quote-detail').textContent = `Bid ${fmt(q.bid)} · Ask ${fmt(q.ask)} · Spread ${fmt(q.ask - q.bid, 4)}`;
  $('gamma-regime').textContent = data.dealer.gamma_regime;
  $('gamma-regime').className = data.dealer.net_gex >= 0 ? 'positive' : 'negative';
  $('book-imbalance').textContent = `${data.book.imbalance >= 0 ? '+' : ''}${fmt(data.book.imbalance * 100, 0)}%`;
  $('book-imbalance').className = data.book.imbalance >= 0 ? 'positive' : 'negative';
  $('shock-state').textContent = data.shock.label;
  $('updated-at').textContent = new Date(data.generated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function renderChart(data) {
  const bars = (data.bars || []).map(b => ({ time: Math.floor(new Date(b.timestamp).getTime() / 1000), open: b.open, high: b.high, low: b.low, close: b.close }));
  const volumes = (data.bars || []).map(b => ({ time: Math.floor(new Date(b.timestamp).getTime() / 1000), value: b.volume, color: b.close >= b.open ? 'rgba(50,214,160,.22)' : 'rgba(255,97,120,.22)' }));
  state.candleSeries.setData(bars);
  state.volumeSeries.setData(volumes);
  state.lines.forEach(line => state.candleSeries.removePriceLine(line));
  state.lines = [];
  const levels = [
    ['Gamma flip', data.dealer.gamma_flip, '#ad8cff', 2], ['Call wall', data.dealer.call_wall, '#ff6178', 1],
    ['Put wall', data.dealer.put_wall, '#32d6a0', 1], ['Max pain', data.dealer.max_pain, '#ffbe4f', 1],
    ['Bid wall', data.book.bid_wall, '#54d9ff', 1], ['Ask wall', data.book.ask_wall, '#f58fff', 1],
  ];
  const legend = [];
  levels.forEach(([title, price, color, width]) => {
    if (!price) return;
    const line = state.candleSeries.createPriceLine({ price, color, lineWidth: width, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title });
    state.lines.push(line); legend.push(`<span style="--color:${color}">${escapeHtml(title)}</span>`);
  });
  $('chart-legend').innerHTML = legend.join('');
  state.chart.timeScale().fitContent();
}

function renderSignals(s) {
  $('bento-state').textContent = s.bento_state; $('bento-score').textContent = `${Math.round(s.bento_score * 100)}%`;
  $('bento-direction').textContent = `Predicts ${s.bento_direction} reversal · independent`;
  $('trinity-state').textContent = s.trinity_state; $('trinity-score').textContent = `${Math.round(s.trinity_score * 100)}%`;
  $('trinity-direction').textContent = `Predicts ${s.trinity_direction} continuation · independent`;
  const router = $('router-state'); router.textContent = s.router_state;
  router.className = `router-state ${s.router_state.includes('WAIT') || s.router_state.includes('DO NOT') ? 'wait' : s.router_direction === 'up' ? 'up' : s.router_direction === 'down' ? 'down' : 'neutral'}`;
  $('reversal-score').textContent = `${s.reversal_score} / 6`; $('reversal-meter').style.width = `${s.reversal_score / 6 * 100}%`;
  $('signal-reasons').innerHTML = (s.reasons || []).map(x => `<span>${escapeHtml(x)}</span>`).join('') || '<span>No active confirmation factors</span>';
}

function renderDealer(d) {
  $('net-gex').textContent = compact(d.net_gex); $('net-gex').className = d.net_gex >= 0 ? 'positive' : 'negative';
  $('net-dex').textContent = compact(d.net_dex); $('gamma-flip').textContent = fmt(d.gamma_flip); $('expected-move').textContent = d.expected_move ? `±${fmt(d.expected_move)}` : '—';
  $('call-wall').textContent = fmt(d.call_wall); $('put-wall').textContent = fmt(d.put_wall);
}

function renderGex(values) {
  const entries = Object.entries(values).map(([k,v]) => [Number(k), Number(v)]).sort((a,b) => a[0]-b[0]);
  if (!entries.length) { $('gex-bars').innerHTML = '<div class="empty">No GEX data</div>'; return; }
  const max = Math.max(...entries.map(([,v]) => Math.abs(v)), 1);
  const selected = entries.length > 45 ? entries.filter((_,i) => i % Math.ceil(entries.length / 45) === 0) : entries;
  $('gex-bars').innerHTML = '<div class="gex-zero"></div>' + selected.map(([strike,value], i) => {
    const h = Math.max(1, Math.abs(value) / max * 47);
    return `<div class="gex-column" title="${strike}: ${compact(value)}"><div class="positive-bar" style="height:${value > 0 ? h : 0}%"></div><div class="negative-bar" style="height:${value < 0 ? h : 0}%"></div>${i % 7 === 0 ? `<span class="gex-label">${strike}</span>` : ''}</div>`;
  }).join('');
}

function renderMagnets(items, spot) {
  $('magnet-list').innerHTML = items.map(item => {
    const distance = (item.price / spot - 1) * 100; const width = Math.min(100, item.strength * 70);
    return `<div class="magnet-row"><span>${escapeHtml(item.label)} <small class="muted">${distance >= 0 ? '+' : ''}${fmt(distance)}%</small></span><strong>${fmt(item.price)}</strong><div class="strength"><i style="width:${width}%"></i></div></div>`;
  }).join('') || '<div class="empty">No positioning levels</div>';
}

function renderShock(s) {
  $('shock-badge').textContent = s.label; $('shock-badge').className = `badge ${s.severity}`;
  $('shock-change').textContent = `${s.change_pct >= 0 ? '+' : ''}${fmt(s.change_pct)}%`; $('shock-change').className = cssDirection(s.direction);
  $('shock-zscore').textContent = s.zscore == null ? 'z-score —' : `${s.zscore >= 0 ? '+' : ''}${fmt(s.zscore)}σ`;
  const p = s.historical_reversion_probability;
  $('reversion-probability').textContent = p == null ? '—' : `${Math.round(p * 100)}%`;
  $('probability-meter').style.width = `${p == null ? 0 : p * 100}%`;
  $('reversion-sample').textContent = s.sample_size ? `${s.sample_size} comparable historical shocks · ${s.horizon_days}-session horizon` : 'No comparable sample at this threshold';
  $('shock-note').textContent = s.note;
}

function renderBook(b) {
  $('bid-wall').textContent = fmt(b.bid_wall); $('bid-wall-size').textContent = compact(b.bid_wall_size);
  $('ask-wall').textContent = fmt(b.ask_wall); $('ask-wall-size').textContent = compact(b.ask_wall_size);
  $('microprice').textContent = fmt(b.microprice, 4); $('spread').textContent = `Spread ${fmt(b.spread, 4)}`;
  $('imbalance-fill').style.left = `${Math.max(1, Math.min(99, 50 + b.imbalance * 48))}%`;
}

function renderFlows(flows) {
  const total = flows.reduce((a,x) => a + x.premium, 0), bullish = flows.filter(x => x.sentiment === 'bullish').reduce((a,x) => a+x.premium,0);
  const bias = total ? bullish / total : .5; $('flow-bias').textContent = bias > .58 ? 'BULLISH' : bias < .42 ? 'BEARISH' : 'MIXED';
  $('flow-bias').className = `badge ${bias > .58 ? 'positive' : bias < .42 ? 'negative' : ''}`;
  $('flow-list').innerHTML = flows.slice(0, 18).map(f => `<div class="flow-row"><span class="flow-dot ${escapeHtml(f.sentiment)}"></span><div class="flow-main"><strong>${escapeHtml(f.option_symbol || f.symbol)} · ${escapeHtml(f.side)}</strong><small>${new Date(f.timestamp).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})} · ${escapeHtml((f.tags || []).join(', ') || f.option_type || '')}</small></div><div class="flow-premium">$${compact(f.premium)}</div></div>`).join('') || '<div class="empty">No flow events yet</div>';
}

function renderWeekly(rows) {
  const heads = ['','Mon','Tue','Wed','Thu','Fri'].map(x => `<div class="week-head">${x}</div>`).join('');
  const body = rows.map(row => `<div class="week-symbol">${escapeHtml(row.symbol)}</div>${row.days.map(d => `<div class="week-cell ${d.direction} ${d.shock ? 'shock' : ''}"><strong>${d.change_pct == null ? '—' : `${d.change_pct >= 0 ? '+' : ''}${fmt(d.change_pct)}%`}</strong><small>${escapeHtml(d.status)}</small></div>`).join('')}`).join('');
  $('weekly-table').innerHTML = `<div class="week-grid">${heads}${body}</div>`;
}

async function enableAlarm() {
  state.alarmEnabled = !state.alarmEnabled;
  $('alarm-button').textContent = state.alarmEnabled ? 'Alarm on' : 'Alarm off';
  if (state.alarmEnabled) {
    state.audioContext = state.audioContext || new (window.AudioContext || window.webkitAudioContext)();
    if ('Notification' in window && Notification.permission === 'default') await Notification.requestPermission();
    beep('watch');
  }
}
function beep(severity = 'warning') {
  if (!state.alarmEnabled || !state.audioContext) return;
  const ctx = state.audioContext, osc = ctx.createOscillator(), gain = ctx.createGain();
  osc.frequency.value = severity === 'critical' ? 880 : severity === 'warning' ? 660 : 440;
  gain.gain.setValueAtTime(.0001, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(.14, ctx.currentTime + .02);
  gain.gain.exponentialRampToValueAtTime(.0001, ctx.currentTime + .24);
  osc.connect(gain).connect(ctx.destination); osc.start(); osc.stop(ctx.currentTime + .25);
}
function renderAlerts(alerts) {
  $('alert-count').textContent = alerts.length;
  $('alert-list').innerHTML = alerts.map(a => `<div class="alert-row"><span class="severity-dot ${a.severity}"></span><div class="alert-main"><strong>${escapeHtml(a.title)}</strong><small>${escapeHtml(a.message)}</small></div></div>`).join('') || '<div class="empty">No active alerts</div>';
  alerts.forEach(a => { if (!state.alertIds.has(a.id) && ['warning','critical'].includes(a.severity)) { toast(`${a.symbol}: ${a.title}`, a.message); beep(a.severity); if (state.alarmEnabled && 'Notification' in window && Notification.permission === 'granted') new Notification(`${a.symbol}: ${a.title}`, { body: a.message }); state.alertIds.add(a.id); } });
}

function renderProviders(items) {
  $('provider-list').innerHTML = items.map(p => `<div class="provider-item ${p.connected ? 'good' : 'bad'}"><span>${escapeHtml(p.capability)}</span><strong>${escapeHtml(p.provider)}</strong><small>${p.latency_ms == null ? '' : `${fmt(p.latency_ms,0)} ms`} ${escapeHtml(p.message || '')}</small></div>`).join('');
}
function toast(title, message) { const node = document.createElement('div'); node.className = 'toast'; node.innerHTML = `<strong>${escapeHtml(title)}</strong><small>${escapeHtml(message)}</small>`; $('toast-container').appendChild(node); setTimeout(() => node.remove(), 8000); }

document.getElementById('fut-refresh').addEventListener('click', loadFutures);
setInterval(loadFutures, 60000);
loadFutures().catch(e => console.error('gap map', e));

bootstrap().catch(error => { console.error(error); setConnection('offline', 'Failed'); });

// ---- Gap map (futuros CME + liderazgo coreano) --------------------------------------------
// El widget esencial de futuros: entre el cierre del viernes y las 09:30 del lunes las acciones
// US no imprimen NADA (medido 2026-08-02 21:18 ET: ultimo print de SPY/QQQ del viernes 19:59 y
// el WS de Finnhub con 26 suscripciones a 0 trades). El hueco de los futuros es la unica
// informacion de apertura que existe.
async function loadFutures() {
  let d;
  try {
    d = await fetch('/api/futures').then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
  } catch (e) {
    $('fut-rows').innerHTML = `<div class="empty">Gap map unavailable (${escapeHtml(String(e.message || e))})</div>`;
    return;
  }
  const rows = $('fut-rows'), div = $('fut-diverge'), kr = $('fut-korea');
  if (!d.disponible) {
    rows.innerHTML = `<div class="empty">${escapeHtml(d.motivo || 'no data')}</div>`;
    div.hidden = true; kr.innerHTML = ''; $('fut-age').textContent = '—';
    $('fut-caveat').textContent = (d.avisos || []).join(' · ');
    return;
  }
  $('fut-age').textContent = `${fmt(d.edad_s, 0)}s ago · ${d.generado_et || ''} ET`;
  rows.innerHTML = d.futuros.map(f => {
    const up = f.pct >= 0, io = f.implied_open;
    // el retraso se PINTA: ninguna de las fuentes es tiempo real y el widget no puede disimularlo
    const lag = f.lag_s == null ? 'lag ?' : `${fmt(f.lag_s / 60, 0)} min late`;
    return `<div class="fut-row ${up ? 'up' : 'dn'}">
      <div class="fut-name"><strong>${escapeHtml(f.nombre)}</strong><small>${escapeHtml(f.etiqueta || '')}</small></div>
      <div class="fut-pct">${up ? '+' : ''}${fmt(f.pct, 2)}%</div>
      <div class="fut-last">${fmt(f.last, 2)}<small>${f.rango && f.rango[0] != null ? `${fmt(f.rango[0], 2)} – ${fmt(f.rango[1], 2)}` : ''}</small></div>
      <div class="fut-io">${io ? `${escapeHtml(io.simbolo)} → <strong>${fmt(io.apertura_implicita, 2)}</strong><small>${io.delta >= 0 ? '+' : ''}${fmt(io.delta, 2)} vs ${fmt(io.cierre_previo, 2)}</small>` : '<small class="muted">no cash proxy</small>'}</div>
      <div class="fut-src"><small>${escapeHtml(f.fuente)} · ${lag}</small></div>
    </div>`;
  }).join('');
  const kv = Object.entries(d.corea || {});
  kr.innerHTML = kv.length
    ? `<span class="fut-krlabel">🇰🇷 leads ~13h</span>` + kv.map(([n, v]) =>
        `<span class="fut-kr ${v.pct >= 0 ? 'up' : 'dn'}">${escapeHtml(n)} ${v.pct == null ? '—' : `${v.pct >= 0 ? '+' : ''}${fmt(v.pct, 2)}%`}</span>`).join('')
    : '';
  const dv = d.divergencia;
  if (dv && dv.hay) {
    div.hidden = false;
    div.textContent = `⚠ ${dv.lectura}: US ${dv.us_pct >= 0 ? '+' : ''}${fmt(dv.us_pct, 2)}% vs Korea ${fmt(dv.korea_pct, 2)}% — ${fmt(dv.brecha_pp, 2)} pp apart (doctrine, not measured)`;
  } else div.hidden = true;
  $('fut-caveat').textContent = [d.nota, ...(d.avisos || [])].filter(Boolean).join(' · ');
}
