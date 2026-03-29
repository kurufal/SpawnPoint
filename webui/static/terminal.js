/* SpawnPoint Terminal — collapse, tabs, resize, draggable dialogs */

/* ── Draggable dialog via .drag-handle (GPU-accelerated) ── */
(function initDragDialogs() {
  var tx = 0, ty = 0;
  document.addEventListener('mousedown', function (e) {
    var handle = e.target.closest('.drag-handle');
    if (!handle) return;
    var card = handle.closest('.q-card');
    if (!card) return;
    e.preventDefault();
    var startX = e.clientX, startY = e.clientY;
    // read any existing translate offset
    var m = (card.style.transform || '').match(/translate\(\s*(-?[\d.]+)px\s*,\s*(-?[\d.]+)px\s*\)/);
    var ox = m ? parseFloat(m[1]) : 0;
    var oy = m ? parseFloat(m[2]) : 0;
    card.style.willChange = 'transform';

    function onMove(ev) {
      tx = ox + ev.clientX - startX;
      ty = oy + ev.clientY - startY;
      card.style.transform = 'translate(' + tx + 'px,' + ty + 'px)';
    }
    function onUp() {
      card.style.willChange = '';
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    }
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  });
})();

/* Toggle collapse */
window.spToggleTerminal = function () {
  var col = document.getElementById('terminal-column');
  var btn = document.getElementById('terminal-toggle-btn');
  var resizer = document.getElementById('terminal-resizer');
  if (!col) return;
  col.classList.toggle('collapsed');
  var collapsed = col.classList.contains('collapsed');
  if (btn) btn.innerHTML = collapsed ? '\u276E' : '\u276F';
  if (resizer) resizer.setAttribute('data-collapsed', collapsed ? 'true' : 'false');
};

/* Switch active tab */
window.spSwitchTab = function (tabId) {
  document.querySelectorAll('.terminal-tab').forEach(function (t) { t.classList.remove('active'); });
  document.querySelectorAll('.terminal-tab-panel').forEach(function (p) { p.classList.remove('active'); });
  var tab = document.querySelector('.terminal-tab[data-tab="' + tabId + '"]');
  var panel = document.getElementById('tab-panel-' + tabId);
  if (tab) tab.classList.add('active');
  if (panel) panel.classList.add('active');
};

/* Open a new closable tab (for game server logs) */
window.spOpenTab = function (tabId, title) {
  /* If already collapsed, expand first */
  var col = document.getElementById('terminal-column');
  if (col && col.classList.contains('collapsed')) {
    window.spToggleTerminal();
  }
  if (document.querySelector('.terminal-tab[data-tab="' + tabId + '"]')) {
    window.spSwitchTab(tabId);
    return;
  }
  var bar = document.getElementById('terminal-tab-bar');
  if (!bar) return;
  var spacer = bar.querySelector('[data-role="spacer"]');
  var btn = document.createElement('button');
  btn.className = 'terminal-tab';
  btn.setAttribute('data-tab', tabId);
  btn.onclick = function () { window.spSwitchTab(tabId); };
  btn.innerHTML = title +
    '<span class="terminal-tab-close" ' +
    'onclick="event.stopPropagation(); window.spCloseTab(\'' + tabId + '\')">\u00d7</span>';
  if (spacer) {
    bar.insertBefore(btn, spacer);
  } else {
    bar.appendChild(btn);
  }
  var content = document.getElementById('terminal-content');
  if (!content) return;
  var panel = document.createElement('div');
  panel.className = 'terminal-tab-panel';
  panel.id = 'tab-panel-' + tabId;
  panel.innerHTML = '<div class="terminal-log" style="width:100%;height:100%;' +
    'overflow-y:auto;overflow-x:hidden;padding:0.75rem;">Waiting for output\u2026</div>';
  content.appendChild(panel);
  window.spSwitchTab(tabId);
};

/* Close a tab (Main cannot be closed) */
window.spCloseTab = function (tabId) {
  if (tabId === 'main') return;
  var tab = document.querySelector('.terminal-tab[data-tab="' + tabId + '"]');
  var panel = document.getElementById('tab-panel-' + tabId);
  var wasActive = tab && tab.classList.contains('active');
  if (tab) tab.remove();
  if (panel) panel.remove();
  if (wasActive) window.spSwitchTab('main');
};

/* ── Resizer — polls until DOM elements exist, then binds ── */
(function initResizer() {
  var resizer = document.getElementById('terminal-resizer');
  var termCol = document.getElementById('terminal-column');
  if (!resizer || !termCol) { setTimeout(initResizer, 200); return; }

  var MIN_W = 120, MAX_W = 800;
  var dragging = false, startX = 0, startW = 0;

  function onMove(e) {
    if (!dragging) return;
    e.preventDefault();
    var cx = e.touches ? e.touches[0].clientX : e.clientX;
    termCol.style.width = Math.max(MIN_W, Math.min(MAX_W, startW + (startX - cx))) + 'px';
  }
  function onUp() {
    if (!dragging) return;
    dragging = false;
    termCol.classList.remove('resizing');
    resizer.classList.remove('is-active');
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    document.removeEventListener('touchmove', onMove);
    document.removeEventListener('touchend', onUp);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }
  function onDown(e) {
    if (termCol.classList.contains('collapsed')) return;
    e.preventDefault();
    dragging = true;
    startX = e.touches ? e.touches[0].clientX : e.clientX;
    startW = termCol.getBoundingClientRect().width;
    termCol.classList.add('resizing');
    resizer.classList.add('is-active');
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    document.addEventListener('touchmove', onMove, { passive: false });
    document.addEventListener('touchend', onUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }
  resizer.addEventListener('mousedown', onDown);
  resizer.addEventListener('touchstart', onDown, { passive: false });
})();

/* ── Re-attach onclick handlers after DOM is ready ── */
document.addEventListener('DOMContentLoaded', function () {
  var tb = document.getElementById('terminal-toggle-btn');
  if (tb) tb.onclick = function () { window.spToggleTerminal(); };
  document.querySelectorAll('.terminal-tab[data-tab]').forEach(function (t) {
    var tid = t.getAttribute('data-tab');
    t.onclick = function () { window.spSwitchTab(tid); };
  });
});
