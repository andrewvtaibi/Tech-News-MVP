/**
 * static/js/app.js
 * Client-side logic for the BioNews webapp.
 *
 * Responsibilities:
 *   - Read active toggle state (timeframe, content type)
 *   - Trigger search on Enter / button click
 *   - Handle CSV file selection and upload
 *   - Render results: news list OR TradingView widget OR CSV batch view
 *   - Surface loading state and errors cleanly
 *
 * Assumptions:
 *   - API is served from the same origin (relative URLs used).
 *   - TradingView widget script injected per-render for the stock view.
 *   - No framework; vanilla ES2020.
 */

'use strict';

// ---------------------------------------------------------------------------
// Widget configuration
// ---------------------------------------------------------------------------

// 420px × 2.5 = 1050px
const STOCK_WIDGET_HEIGHT = 300;

// Map the app timeframe to the nearest TradingView range token.
// "5D" = 5 trading days ≈ 1 calendar week; "1M" = 1 month.
function daysToTvRange(days) {
  return days >= 30 ? '1M' : '5D';
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const state = {
  contentType: 'headlines',   // headlines | press_releases | stock_price
  days: 7,                    // 7 | 30
  csvFile: null,
};

// ---------------------------------------------------------------------------
// DOM refs (resolved after DOMContentLoaded)
// ---------------------------------------------------------------------------

let searchInput, searchBtn;
let timeframeBtns, contentTypeBtns;
let csvInput, csvFilename, csvSubmitBtn;
let statusBar, statusMsg, errorBanner, noResults, resultsArea;

// ---------------------------------------------------------------------------
// Initialise
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  searchInput    = document.getElementById('search-input');
  searchBtn      = document.getElementById('search-btn');
  timeframeBtns  = document.querySelectorAll('.timeframe-btn');
  contentTypeBtns = document.querySelectorAll('.content-type-btn');
  csvInput       = document.getElementById('csv-input');
  csvFilename    = document.getElementById('csv-filename');
  csvSubmitBtn   = document.getElementById('csv-submit-btn');
  statusBar      = document.getElementById('status-bar');
  statusMsg      = document.getElementById('status-msg');
  errorBanner    = document.getElementById('error-banner');
  noResults      = document.getElementById('no-results');
  resultsArea    = document.getElementById('results-area');

  // Timeframe toggles
  timeframeBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      timeframeBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.days = parseInt(btn.dataset.days, 10);
      if (searchInput.value.trim()) doSearch();
      if (state.csvFile) doUpload();
    });
  });

  // Content-type toggles
  contentTypeBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      contentTypeBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.contentType = btn.dataset.type;
      if (searchInput.value.trim()) doSearch();
      if (state.csvFile) doUpload();
    });
  });

  // Search input — Enter key
  searchInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') doSearch();
  });

  // Search button
  searchBtn.addEventListener('click', doSearch);

  // CSV file selection
  csvInput.addEventListener('change', () => {
    const f = csvInput.files && csvInput.files[0];
    if (f) {
      state.csvFile = f;
      csvFilename.textContent = f.name;
      csvSubmitBtn.classList.add('visible');
    }
  });

  // CSV submit
  csvSubmitBtn.addEventListener('click', doUpload);
});

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

async function doSearch() {
  const q = searchInput.value.trim();
  if (!q) {
    showError('Please enter a company name or ticker symbol.');
    return;
  }

  showLoading(`Searching for "${q}"…`);

  const params = new URLSearchParams({
    q,
    content_type: state.contentType,
    days: state.days,
  });

  try {
    const resp = await fetch(`/api/search?${params}`);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${resp.status}`);
    }
    const data = await resp.json();
    renderSingleResult(data);
  } catch (e) {
    showError(e.message || 'Search failed. Please try again.');
  }
}

// ---------------------------------------------------------------------------
// CSV Upload
// ---------------------------------------------------------------------------

async function doUpload() {
  if (!state.csvFile) return;

  showLoading('Processing CSV upload…');

  const formData = new FormData();
  formData.append('file', state.csvFile);
  formData.append('content_type', state.contentType);
  formData.append('days', state.days);

  try {
    const resp = await fetch('/api/upload', {
      method: 'POST',
      body: formData,
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${resp.status}`);
    }
    const data = await resp.json();
    renderBatchResults(data);
  } catch (e) {
    showError(e.message || 'Upload failed. Please try again.');
  }
}

// ---------------------------------------------------------------------------
// Renderers
// ---------------------------------------------------------------------------

function renderSingleResult(data) {
  hideLoading();
  clearResults();

  const ct = data.content_type;

  if (ct === 'stock_price') {
    renderStockWidget(data);
    return;
  }

  const section = makeSingleSection(data);
  resultsArea.appendChild(section);

  if (data.items.length === 0) {
    noResults.classList.add('visible');
  }
}

function renderBatchResults(data) {
  hideLoading();
  clearResults();

  if (!data.results || data.results.length === 0) {
    noResults.classList.add('visible');
    return;
  }

  data.results.forEach(result => {
    if (result.content_type === 'stock_price') {
      resultsArea.appendChild(makeStockSection(result));
    } else {
      resultsArea.appendChild(makeCompanySection(result));
    }
  });

  if (data.errors && data.errors.length > 0) {
    const errEl = document.createElement('div');
    errEl.className = 'error-banner visible';
    errEl.style.marginTop = '12px';
    errEl.textContent =
      `${data.errors.length} row(s) could not be processed: ` +
      data.errors.map(e => e.value).join(', ');
    resultsArea.appendChild(errEl);
  }
}

// Single company search result (no collapsible header)
function makeSingleSection(data) {
  const wrap = document.createElement('div');
  wrap.className = 'company-section';

  const header = document.createElement('div');
  header.className = 'company-header';

  const label = escHtml(
    data.resolved.company_name || data.query
  );
  const ticker = data.resolved.ticker
    ? `<span class="ticker-badge">${escHtml(data.resolved.ticker)}</span>`
    : '';
  const timeLabel = data.days === 7 ? 'Past 7 days' : 'Past 30 days';

  header.innerHTML = `
    ${label} ${ticker}
    <span style="font-size:12px;opacity:0.75;margin-left:8px">${timeLabel}</span>
  `;

  const body = document.createElement('div');
  body.className = 'company-body';

  if (data.items.length === 0) {
    body.innerHTML =
      '<p class="no-items-msg">No results found for this query and timeframe.</p>';
  } else {
    body.appendChild(buildNewsList(data.items));
  }

  wrap.appendChild(header);
  wrap.appendChild(body);
  return wrap;
}

// Collapsible company section for batch results
function makeCompanySection(data) {
  const wrap = document.createElement('div');
  wrap.className = 'company-section';

  const header = document.createElement('div');
  header.className = 'company-header';

  const label = escHtml(data.resolved.company_name || data.query);
  const ticker = data.resolved.ticker
    ? `<span class="ticker-badge">${escHtml(data.resolved.ticker)}</span>`
    : '';
  const count = `<span style="margin-left:auto;font-size:12px;opacity:0.7">
      ${data.items.length} item${data.items.length !== 1 ? 's' : ''}
    </span>`;

  header.innerHTML = `${label} ${ticker} ${count}
    <span class="toggle-icon">▼</span>`;

  header.addEventListener('click', () => {
    header.classList.toggle('collapsed');
    body.classList.toggle('collapsed');
  });

  const body = document.createElement('div');
  body.className = 'company-body';

  if (data.items.length === 0) {
    body.innerHTML =
      '<p class="no-items-msg">No results found.</p>';
  } else {
    body.appendChild(buildNewsList(data.items));
  }

  wrap.appendChild(header);
  wrap.appendChild(body);
  return wrap;
}

function buildNewsList(items) {
  const ul = document.createElement('ul');
  ul.className = 'news-list';

  items.forEach(item => {
    const li = document.createElement('li');
    li.className = 'news-item';

    const date = item.published_date
      ? formatDate(item.published_date)
      : '';

    const summary = item.summary_snippet
      ? `<p class="news-summary">${escHtml(item.summary_snippet)}</p>`
      : '';

    li.innerHTML = `
      <a href="${escAttr(item.link)}" target="_blank" rel="noopener noreferrer">
        ${escHtml(item.title)}
      </a>
      <div class="news-meta">
        <span class="source">${escHtml(item.source)}</span>
        ${date ? `<span>${escHtml(date)}</span>` : ''}
      </div>
      ${summary}
    `;
    ul.appendChild(li);
  });

  return ul;
}

// Single stock widget (for single search)
function renderStockWidget(data) {
  const wrap = document.createElement('div');
  wrap.className = 'stock-widget-wrap';

  const ticker = data.resolved.ticker;
  const name = escHtml(data.resolved.company_name || data.query);

  if (!ticker) {
    wrap.innerHTML = `
      <div class="stock-widget-header">${name}</div>
      <p class="stock-no-ticker">
        No ticker symbol found for "<strong>${name}</strong>".
        Try searching by the exact ticker (e.g. PFE, MRNA).
      </p>
    `;
    resultsArea.appendChild(wrap);
    return;
  }

  wrap.innerHTML = `
    <div class="stock-widget-header">
      Stock chart: <span class="ticker-display">${escHtml(ticker)}</span>
      — ${name}
    </div>
    <div style="height:${STOCK_WIDGET_HEIGHT}px;width:100%">
      <div class="tradingview-widget-container"
           id="tv-widget-${escAttr(ticker)}"
           style="height:100%;width:100%">
      </div>
    </div>
  `;
  resultsArea.appendChild(wrap);
  injectTradingViewWidget(ticker, `tv-widget-${ticker}`, state.days);
}

// Collapsible stock section for batch view
function makeStockSection(data) {
  const wrap = document.createElement('div');
  wrap.className = 'company-section';

  const ticker = data.resolved.ticker;
  const name = escHtml(data.resolved.company_name || data.query);

  const header = document.createElement('div');
  header.className = 'company-header';
  header.innerHTML = `${name}
    ${ticker ? `<span class="ticker-badge">${escHtml(ticker)}</span>` : ''}
    <span class="toggle-icon" style="margin-left:auto">▼</span>`;
  header.addEventListener('click', () => {
    header.classList.toggle('collapsed');
    body.classList.toggle('collapsed');
  });

  const body = document.createElement('div');
  body.className = 'company-body';

  if (!ticker) {
    body.innerHTML = `<p class="no-items-msg">
      No ticker symbol found. Try using the exact ticker abbreviation.</p>`;
  } else {
    const containerId = `tv-batch-${escAttr(ticker)}-${Date.now()}`;
    body.innerHTML = `
      <div style="padding:16px">
        <div style="height:${STOCK_WIDGET_HEIGHT}px;width:100%">
          <div class="tradingview-widget-container"
               id="${containerId}"
               style="height:100%;width:100%"></div>
        </div>
      </div>
    `;
    // Defer widget injection until after DOM insertion
    requestAnimationFrame(
      () => injectTradingViewWidget(ticker, containerId, state.days)
    );
  }

  wrap.appendChild(header);
  wrap.appendChild(body);
  return wrap;
}

// ---------------------------------------------------------------------------
// TradingView widget injection
// ---------------------------------------------------------------------------

function injectTradingViewWidget(ticker, containerId, days) {
  const container = document.getElementById(containerId);
  if (!container) return;

  container.innerHTML = '';

  // Inner mount point required by TradingView's iframe embed format
  const inner = document.createElement('div');
  inner.className = 'tradingview-widget-container__widget';
  inner.style.cssText = 'height:calc(100% - 32px);width:100%';
  container.appendChild(inner);

  // TradingView reads the script's textContent for widget options
  const script = document.createElement('script');
  script.type = 'text/javascript';
  script.src =
    'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
  script.async = true;
  script.text = JSON.stringify({
    autosize: true,
    symbol: ticker,
    interval: 'D',
    range: daysToTvRange(days || state.days),
    withdateranges: true,
    timezone: 'Etc/UTC',
    theme: 'light',
    style: '1',
    locale: 'en',
    allow_symbol_change: false,
    calendar: false,
    support_host: 'https://www.tradingview.com',
  });
  container.appendChild(script);
}

// ---------------------------------------------------------------------------
// UI state helpers
// ---------------------------------------------------------------------------

function showLoading(msg) {
  errorBanner.classList.remove('visible');
  noResults.classList.remove('visible');
  clearResults();
  statusMsg.textContent = msg;
  statusBar.classList.add('visible');
}

function hideLoading() {
  statusBar.classList.remove('visible');
}

function showError(msg) {
  hideLoading();
  clearResults();
  errorBanner.textContent = msg;
  errorBanner.classList.add('visible');
}

function clearResults() {
  resultsArea.innerHTML = '';
  noResults.classList.remove('visible');
  errorBanner.classList.remove('visible');
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escAttr(str) {
  // For use inside HTML attribute values (href, id).
  // Allow only safe URL characters; strip everything else.
  if (!str) return '';
  return String(str).replace(/[^A-Za-z0-9\-._~:/?#[\]@!$&'()*+,;=%]/g, '');
}

function formatDate(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric',
    });
  } catch {
    return iso.slice(0, 10);
  }
}
