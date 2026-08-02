const $ = (id) => document.getElementById(id);
const state = { symbol: 'SPY', socket: null, chart: null, candleSeries: null, volumeSeries: null, lines: [], alertIds: new Set(), alarmEnabled: false, audioContext: null };

function fmt(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
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
  connect();
  $('symbol-select').addEventListener('change', () => { state.symbol = $('symbol-select').value; connect(); });
  $('alarm-button').addEventListener('click', enableAlarm);
  $('refresh-button').addEventListener('click', async () => {
    const payload = await fetch(`/api/snapshot/${encodeURIComponent(state.symbol)}?force=true`).then(r => r.json());
    render(payload);
  });
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

bootstrap().catch(error => { console.error(error); setConnection('offline', 'Failed'); });
