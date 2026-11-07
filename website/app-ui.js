/**
 * app-ui.js — ReelMind App UI Logic
 *
 * Handles: view routing, Instagram connect, pipeline SSE,
 * reel grid rendering, and chat with source citations.
 */
'use strict';

// ── State ──────────────────────────────────────────────────────────────────
const state = {
  username: '',
  reels: [],
  chatHistory: [],
  sseSource: null,
  chatBusy: false,
  ollamaAvailable: false,
  generateBusy: false,
  generateMode: 'image',
  generateProvider: 'local',
  generatedItems: [],
};

function saveChatHistory() {
  const messages = Array.from(document.querySelectorAll('.chat-message')).map(el => el.innerHTML);
  localStorage.setItem('reelmind_chat_history', JSON.stringify(messages));
}

function restoreChatHistory() {
  const saved = localStorage.getItem('reelmind_chat_history');
  if (saved && els.chatMessages) {
    try {
      const messages = JSON.parse(saved);
      if (messages.length > 0) {
        // Clear welcome message
        const welcome = document.getElementById('chat-welcome');
        if (welcome) welcome.remove();
        
        messages.forEach(html => {
          const msgEl = document.createElement('div');
          msgEl.className = 'chat-message';
          msgEl.innerHTML = html;
          els.chatMessages.appendChild(msgEl);
        });
        els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
      }
    } catch {}
  }
}

// ── DOM references (populated after DOMContentLoaded) ──────────────────────
let els = {};

// ── View router ────────────────────────────────────────────────────────────
function showView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  const view = document.getElementById(`view-${name}`);
  if (view) view.classList.add('active');
  updateNavBreadcrumb(name);

  // Update nav buttons
  const btnDash = document.getElementById('btn-back-dashboard');
  const btnChat = document.getElementById('btn-nav-chat');
  const btnGen = document.getElementById('btn-nav-generate');
  
  if (btnDash) btnDash.style.display = name === 'chat' || name === 'generate' ? 'inline-block' : 'none';
  if (btnChat) btnChat.style.display = name === 'dashboard' && state.reels.length > 0 ? 'inline-block' : 'none';
  if (btnGen) btnGen.style.display = 'inline-block';
}

function updateNavBreadcrumb(view) {
  const labels = { connect: 'Connect', dashboard: 'Dashboard', chat: 'Chat', generate: 'Generate' };
  if (els.breadcrumbCurrent) {
    els.breadcrumbCurrent.textContent = labels[view] || view;
  }
}

// ── Startup ────────────────────────────────────────────────────────────────
async function init() {
  // Gather DOM refs
  els = {
    breadcrumbCurrent: document.getElementById('breadcrumb-current'),
    navStatus:         document.getElementById('nav-status-text'),
    navStatusDot:      document.getElementById('nav-status-dot'),

    // Connect view
    connectError:   document.getElementById('connect-error'),
    alreadySection: document.getElementById('already-section'),
    alreadyCount:   document.getElementById('already-count'),
    btnAlready:     document.getElementById('btn-already'),

    // Dashboard
    phaseMsgs:       [null, ...document.querySelectorAll('.phase-msg')],
    phaseBars:       [null, ...document.querySelectorAll('.phase-bar')],
    phaseItems:      [null, ...document.querySelectorAll('.phase-item')],
    overallBar:      document.getElementById('overall-bar'),
    overallPct:      document.getElementById('overall-pct'),
    pipelineMsg:     document.getElementById('pipeline-msg'),
    btnStartChat:    document.getElementById('btn-start-chat'),
    reelGrid:        document.getElementById('reel-grid'),
    reelCountBadge:  document.getElementById('reel-count-badge'),

    // Chat
    chatMessages:  document.getElementById('chat-messages'),
    chatInput:     document.getElementById('chat-input'),
    btnSend:       document.getElementById('btn-send'),
    sidebarList:   document.getElementById('sidebar-reel-list'),
    ollamaWarning: document.getElementById('ollama-warning'),
  };

  // Check health to see if reels already indexed
  try {
    const h = await api('/api/health');
    updateOllamaStatus(h.ollama_available);

    if (h.reels_indexed > 0) {
      showAlreadyIndexed(h.reels_indexed);
    }

    if (h.pipeline_status === 'done' || h.reels_indexed > 0) {
      showView('dashboard');
      await onPipelineDone();
      waitForExtensionSync();
    } else {
      showView('connect');
      waitForExtensionSync();
    }
  } catch {
    showView('connect');
    waitForExtensionSync();
  }

  restoreChatHistory();
  bindEvents();
}

async function waitForExtensionSync() {
  while (true) {
    try {
      const snap = await api('/api/pipeline/state');
      if (snap.status === 'running') {
        showView('dashboard');
        startPipelineSSE();
        break;
      }
    } catch {}
    await sleep(2000);
  }
}

function updateOllamaStatus(ok) {
  state.ollamaAvailable = ok;
  if (els.navStatusDot) {
    els.navStatusDot.className = `nav-status-dot ${ok ? 'ok' : 'err'}`;
  }
  if (els.navStatus) {
    els.navStatus.textContent = ok ? 'Ollama: ready' : 'Ollama: offline';
  }
}

function showAlreadyIndexed(count) {
  if (!els.alreadySection) return;
  els.alreadySection.style.display = 'block';
  if (els.alreadyCount) els.alreadyCount.textContent = count;
}

// ── Event bindings ──────────────────────────────────────────────────────────
function bindEvents() {
  // Already indexed → skip to dashboard
  els.btnAlready?.addEventListener('click', async () => {
    showView('dashboard');
    await onPipelineDone();
  });

  // Chat → start chat
  els.btnStartChat?.addEventListener('click', () => {
    showView('chat');
    renderSidebar();
    if (!state.ollamaAvailable && els.ollamaWarning) {
      els.ollamaWarning.classList.remove('hidden');
    }
  });

  // Chat input
  els.btnSend?.addEventListener('click', sendMessage);
  els.chatInput?.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  els.chatInput?.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
  });

  // Suggestion chips
  document.querySelectorAll('.chat-suggestion').forEach(chip => {
    chip.addEventListener('click', () => {
      if (els.chatInput) els.chatInput.value = chip.dataset.q || chip.textContent;
      sendMessage();
    });
  });

  // Nav back buttons
  document.getElementById('btn-back-connect')?.addEventListener('click', () => showView('connect'));
  document.getElementById('btn-back-dashboard')?.addEventListener('click', () => showView('dashboard'));
  document.getElementById('btn-nav-chat')?.addEventListener('click', () => {
    showView('chat');
    renderSidebar();
  });
  document.getElementById('btn-nav-generate')?.addEventListener('click', () => {
    showView('generate');
    renderGeneratedResults();
  });

  // Generate view
  bindGenerateEvents();
}

function showConnectError(msg) {
  if (!els.connectError) return;
  els.connectError.textContent = msg;
  els.connectError.classList.add('show');
}
function hideConnectError() {
  els.connectError?.classList.remove('show');
}

// ── Pipeline SSE ────────────────────────────────────────────────────────────
function startPipelineSSE() {
  if (state.sseSource) state.sseSource.close();

  const es = new EventSource('/api/pipeline/status');
  state.sseSource = es;

  es.onmessage = (e) => {
    try {
      const snap = JSON.parse(e.data);
      updatePipelineUI(snap);

      if (snap.status === 'done') {
        es.close();
        state.sseSource = null;
        onPipelineDone();
      } else if (snap.status === 'error') {
        es.close();
        state.sseSource = null;
        onPipelineError(snap.error);
      }
    } catch {}
  };

  es.onerror = () => {
    es.close();
    // Try polling fallback
    pollPipelineState();
  };
}

async function pollPipelineState() {
  // Fallback if SSE fails — poll every 2s
  while (true) {
    await sleep(2000);
    try {
      const snap = await api('/api/pipeline/state');
      updatePipelineUI(snap);
      if (snap.status === 'done') { onPipelineDone(); break; }
      if (snap.status === 'error') { onPipelineError(snap.error); break; }
    } catch { break; }
  }
}

function updatePipelineUI(snap) {
  const { phase, progress, total, message, status } = snap;
  const pct = total > 0 ? Math.round((progress / total) * 100) : 0;

  // Update phase items
  [1, 2, 3].forEach(p => {
    const item = els.phaseItems[p];
    const bar  = els.phaseBars[p];
    const msg  = els.phaseMsgs[p];
    if (!item) return;

    item.classList.remove('active', 'done', 'pending');

    if (p < phase) {
      item.classList.add('done');
      if (bar) bar.style.width = '100%';
      if (msg) msg.textContent = 'Completed';
    } else if (p === phase) {
      item.classList.add('active');
      if (bar) bar.style.width = `${pct}%`;
      if (msg) msg.textContent = message || '';
    } else {
      item.classList.add('pending');
      if (bar) bar.style.width = '0%';
    }
  });

  // Overall progress: phase contributes 33.3% each
  const overallPct = Math.min(100, Math.round(((phase - 1) * 33.33) + (pct * 0.3333)));
  if (els.overallBar) els.overallBar.style.width = `${overallPct}%`;
  if (els.overallPct) els.overallPct.textContent = `${overallPct}%`;
  if (els.pipelineMsg) els.pipelineMsg.textContent = message || '';

  // Load reels as they get indexed
  if (snap.reels_indexed > state.reels.length) {
    loadReels();
  }
}

async function onPipelineDone() {
  await loadReels();
  enableChatButton();
  showView('dashboard'); // re-evaluate nav buttons now that reels are loaded
  
  // Update all phase bars to 100%
  [1, 2, 3, 4].forEach(p => {
    const item = els.phaseItems[p];
    const bar  = els.phaseBars[p];
    const msg  = els.phaseMsgs[p];
    if (item) { item.classList.remove('active', 'pending'); item.classList.add('done'); }
    if (bar)  bar.style.width = '100%';
    if (msg)  msg.textContent = 'Completed';
  });
  if (els.overallBar) els.overallBar.style.width = '100%';
  if (els.overallPct) els.overallPct.textContent = '100%';
  if (els.pipelineMsg) els.pipelineMsg.textContent = '✓ All reels indexed and ready!';
}

function onPipelineError(err) {
  if (els.pipelineMsg) {
    els.pipelineMsg.textContent = `⚠ Error: ${err}`;
    els.pipelineMsg.style.color = 'var(--red)';
  }
}

function enableChatButton() {
  if (els.btnStartChat) els.btnStartChat.disabled = false;
}

// ── Reel grid ────────────────────────────────────────────────────────────────
async function loadReels() {
  try {
    const data = await api('/api/reels');
    state.reels = data.reels || [];
    renderReelGrid();
  } catch {}
}

function renderReelGrid() {
  const grid = els.reelGrid;
  if (!grid) return;

  if (els.reelCountBadge) {
    els.reelCountBadge.textContent = `${state.reels.length} reels`;
  }

  if (state.reels.length === 0) {
    grid.innerHTML = `
      <div class="grid-empty">
        <div class="empty-icon">🎬</div>
        <div>Reels will appear here as they're indexed…</div>
      </div>`;
    return;
  }

  grid.innerHTML = state.reels.map((r, i) => reelCardHTML(r, i)).join('');
}

function reelCardHTML(reel, idx) {
  const thumb = reel.thumbnail
    ? `<img src="/thumbs/${reel.thumbnail}" alt="Reel thumbnail" loading="lazy" />`
    : `<div class="reel-thumb-placeholder">🎬</div>`;
  const user = reel.username ? `<span class="reel-username">@${escHtml(reel.username)}</span>` : '';
  const date = reel.timestamp ? new Date(reel.timestamp).toLocaleDateString() : '';
  const caption = reel.caption ? escHtml(reel.caption.slice(0, 80)) : 'No caption';

  return `
    <div class="reel-card" data-idx="${idx}" onclick="openReelModal('${reel.shortcode}')" style="cursor: pointer;" title="Open Video and Chat">
      <div class="reel-thumb">
        ${thumb}
        ${user}
      </div>
      <div class="reel-meta">
        <div class="reel-caption">${caption}</div>
        <div class="reel-date">${date}</div>
      </div>
    </div>`;
}

// ── Sidebar ──────────────────────────────────────────────────────────────────
function renderSidebar() {
  const list = els.sidebarList;
  if (!list || state.reels.length === 0) return;

  list.innerHTML = state.reels.map((r, i) => {
    const thumb = r.thumbnail
      ? `<img src="/thumbs/${r.thumbnail}" alt="" loading="lazy" />`
      : '🎬';
    return `
      <div class="sidebar-reel" data-idx="${i}" id="sidebar-reel-${i}" onclick="openReelModal('${r.shortcode}')" style="cursor: pointer;" title="Open Video and Chat">
        <div class="sidebar-thumb">${thumb}</div>
        <div class="sidebar-reel-info">
          <div class="sidebar-reel-name">${escHtml(r.filename || r.shortcode || '')}</div>
          <div class="sidebar-reel-user">${r.username ? '@' + escHtml(r.username) : ''}</div>
        </div>
      </div>`;
  }).join('');
}

function highlightReel(idx) {
  document.querySelectorAll('.sidebar-reel').forEach(el => el.classList.remove('highlighted'));
  const el = document.getElementById(`sidebar-reel-${idx}`);
  if (el) el.classList.add('highlighted');
}

// ── Chat ─────────────────────────────────────────────────────────────────────
async function sendMessage() {
  const input = els.chatInput;
  if (!input || state.chatBusy) return;

  const question = input.value.trim();
  if (!question) return;

  input.value = '';
  input.style.height = 'auto'; // Reset height
  state.chatBusy = true;
  if (els.btnSend) els.btnSend.disabled = true;

  // Remove welcome screen if present
  const welcome = document.getElementById('chat-welcome');
  if (welcome) welcome.remove();

  // Append user message
  appendMessage('user', question);

  // Show typing indicator
  const typingId = appendTyping();

  try {
    const result = await api('/api/chat', 'POST', { question });
    removeTyping(typingId);
    appendMessage('ai', result.answer, result.source_reels || []);
    highlightSourceReels(result.source_reels || []);
  } catch (err) {
    removeTyping(typingId);
    appendErrorMessage(err.message || 'Chat request failed. Is Ollama running?');
  }

  state.chatBusy = false;
  if (els.btnSend) els.btnSend.disabled = false;
  input.focus();
}

function appendMessage(role, text, sources = []) {
  const container = els.chatMessages;
  if (!container) return;

  const msgEl = document.createElement('div');
  msgEl.className = 'chat-message';

  const isUser = role === 'user';
  const avatar = isUser
    ? `<div class="chat-avatar chat-avatar--user">👤</div>`
    : `<div class="chat-avatar chat-avatar--ai">🤖</div>`;

  msgEl.innerHTML = `
    <div class="chat-msg-row ${isUser ? 'chat-msg-row--user' : ''}">
      ${avatar}
      <div class="chat-bubble ${isUser ? 'chat-bubble--user' : 'chat-bubble--ai'}">
        ${isUser 
          ? linkify(escHtml(text)).replace(/\n/g, '<br>')
          : (window.marked ? marked.parse(text) : linkify(escHtml(text)).replace(/\n/g, '<br>'))}
      </div>
    </div>
    ${sources.length > 0 ? renderSources(sources) : ''}`;

  container.appendChild(msgEl);
  container.scrollTop = container.scrollHeight;
  saveChatHistory();
}

function renderSources(sources) {
  const cards = sources.map(s => {
    const thumb = s.thumbnail
      ? `<img src="/thumbs/${s.thumbnail}" alt="" />`
      : '🎬';
    return `
      <div class="source-card" onclick="openReelUrl('${s.shortcode}')" style="cursor: pointer;" title="Open on Instagram">
        <div class="source-thumb">${thumb}</div>
        <div class="source-info">
          <div class="source-label">📹 Source</div>
          <div class="source-name">${escHtml(s.filename || s.shortcode || '')}</div>
        </div>
      </div>`;
  }).join('');
  return `<div class="chat-sources">${cards}</div>`;
}

function highlightSourceReels(sources) {
  const filenames = new Set(sources.map(s => s.filename));
  state.reels.forEach((r, i) => {
    const el = document.getElementById(`sidebar-reel-${i}`);
    if (!el) return;
    if (filenames.has(r.filename)) {
      el.classList.add('highlighted');
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } else {
      el.classList.remove('highlighted');
    }
  });
}

let _typingCounter = 0;
function appendTyping() {
  const id = `typing-${++_typingCounter}`;
  const container = els.chatMessages;
  if (!container) return id;

  const el = document.createElement('div');
  el.id = id;
  el.className = 'typing-indicator';
  el.innerHTML = `
    <div class="chat-avatar chat-avatar--ai">🤖</div>
    <div class="typing-dots">
      <span></span><span></span><span></span>
    </div>`;
  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
  return id;
}

function removeTyping(id) {
  document.getElementById(id)?.remove();
}

function appendErrorMessage(msg) {
  const container = els.chatMessages;
  if (!container) return;
  const el = document.createElement('div');
  el.className = 'chat-error-msg';
  el.textContent = `⚠ ${msg}`;
  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
}

// ── API helper ────────────────────────────────────────────────────────────────
async function api(url, method = 'GET', body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function linkify(text) {
  const urlRegex = /(https?:\/\/[^\s]+)/g;
  return text.replace(urlRegex, function(url) {
    return '<a href="' + url + '" target="_blank" style="color: var(--cyan); text-decoration: underline; word-break: break-all;">' + url + '</a>';
  });
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

function openReelUrl(shortcode) {
  if (shortcode) {
    window.open(`https://www.instagram.com/reel/${shortcode}/`, '_blank');
  }
}

// ── Modal & Single Reel Chat ──────────────────────────────────────────────────
let activeModalShortcode = null;
let modalChatBusy = false;

async function openReelModal(shortcode) {
  if (!shortcode) return;
  activeModalShortcode = shortcode;
  
  const modal = document.getElementById('reel-modal');
  const video = document.getElementById('modal-video');
  const igLink = document.getElementById('modal-ig-link');
  const transcriptArea = document.getElementById('modal-transcript');
  const chatMessages = document.getElementById('modal-chat-messages');
  
  // Reset state
  video.src = '';
  transcriptArea.innerHTML = '<div style="opacity:0.5;">Loading context...</div>';
  chatMessages.innerHTML = '';
  modal.showModal();
  
  try {
    const data = await api(`/api/reels/${shortcode}`);
    video.src = `/reels/${data.filename || shortcode + '.mp4'}`;
    igLink.href = `https://www.instagram.com/reel/${shortcode}/`;
    
    let html = '';
    if (data.caption) html += `<h4>Caption</h4><p>${escHtml(data.caption)}</p>`;
    if (data.transcript) html += `<h4>Spoken Audio</h4><p>${escHtml(data.transcript)}</p>`;
    if (data.screen_text) html += `<h4>On-Screen Text</h4><p>${escHtml(data.screen_text)}</p>`;
    
    transcriptArea.innerHTML = html || '<div style="opacity:0.5;">No context found.</div>';
    
    // Add welcome message
    const welcome = document.createElement('div');
    welcome.className = 'chat-message chat-message--ai';
    welcome.innerHTML = `
      <div class="chat-avatar chat-avatar--ai">🤖</div>
      <div class="chat-bubble">What would you like to know about this specific reel?</div>
    `;
    chatMessages.appendChild(welcome);
    
  } catch (e) {
    transcriptArea.innerHTML = `<div style="color:var(--red-500)">Failed to load reel data: ${e.message}</div>`;
  }
}

// Close Modal
document.getElementById('modal-close')?.addEventListener('click', () => {
  document.getElementById('reel-modal').close();
  document.getElementById('modal-video').pause();
  activeModalShortcode = null;
});

// Send Modal Chat
document.getElementById('btn-modal-send')?.addEventListener('click', sendModalMessage);
document.getElementById('modal-chat-input')?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendModalMessage();
  }
});
document.getElementById('modal-chat-input')?.addEventListener('input', function() {
  this.style.height = 'auto';
  this.style.height = (this.scrollHeight) + 'px';
});

async function sendModalMessage() {
  const input = document.getElementById('modal-chat-input');
  const container = document.getElementById('modal-chat-messages');
  const btn = document.getElementById('btn-modal-send');
  if (!input || modalChatBusy || !activeModalShortcode) return;

  const question = input.value.trim();
  if (!question) return;

  input.value = '';
  input.style.height = 'auto'; // Reset height
  modalChatBusy = true;
  if (btn) btn.disabled = true;

  // Append user message
  const userMsg = document.createElement('div');
  userMsg.className = 'chat-message chat-message--user';
  userMsg.innerHTML = `
    <div class="chat-bubble">${escHtml(question)}</div>
    <div class="chat-avatar chat-avatar--user">U</div>
  `;
  container.appendChild(userMsg);
  container.scrollTop = container.scrollHeight;

  // Show typing indicator
  const typingId = `modal-typing-${Date.now()}`;
  const typingEl = document.createElement('div');
  typingEl.id = typingId;
  typingEl.className = 'typing-indicator';
  typingEl.innerHTML = `
    <div class="chat-avatar chat-avatar--ai">🤖</div>
    <div class="typing-dots"><span></span><span></span><span></span></div>
  `;
  container.appendChild(typingEl);
  container.scrollTop = container.scrollHeight;

  try {
    const result = await api('/api/chat_single', 'POST', { 
      shortcode: activeModalShortcode, 
      question 
    });
    
    document.getElementById(typingId)?.remove();
    
    const aiMsg = document.createElement('div');
    aiMsg.className = 'chat-message chat-message--ai';
    aiMsg.innerHTML = `
      <div class="chat-avatar chat-avatar--ai">🤖</div>
      <div class="chat-bubble markdown-body">${marked.parse(result.answer)}</div>
    `;
    container.appendChild(aiMsg);
  } catch (err) {
    document.getElementById(typingId)?.remove();
    const errEl = document.createElement('div');
    errEl.className = 'chat-error-msg';
    errEl.textContent = `⚠ ${err.message}`;
    container.appendChild(errEl);
  } finally {
    modalChatBusy = false;
    if (btn) btn.disabled = false;
    container.scrollTop = container.scrollHeight;
    input.focus();
  }
}

// Expose for inline onclick handlers
window.highlightReel = highlightReel;
window.openReelUrl = openReelUrl;
window.openReelModal = openReelModal;

// ── Generate View ──────────────────────────────────────────────────────────────

function bindGenerateEvents() {
  // Mode tabs (Image/Video)
  document.querySelectorAll('.gen-tab[data-mode]').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.gen-tab[data-mode]').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      state.generateMode = tab.dataset.mode;

      const framesGroup = document.querySelector('.gen-frames-group');
      if (framesGroup) framesGroup.style.display = state.generateMode === 'video' ? '' : 'none';
    });
  });

  // Provider tabs (Local/Cloud)
  document.querySelectorAll('.gen-tab[data-provider]').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.gen-tab[data-provider]').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      state.generateProvider = tab.dataset.provider;

      const cloudGroup = document.querySelector('.gen-cloud-info');
      if (cloudGroup) cloudGroup.style.display = state.generateProvider === 'cloud' ? '' : 'none';

      // Hide video tab when cloud is selected (cloud only does images)
      const videoTab = document.querySelector('.gen-tab[data-mode="video"]');
      if (videoTab) {
        videoTab.style.display = state.generateProvider === 'cloud' ? 'none' : '';
        if (state.generateProvider === 'cloud' && state.generateMode === 'video') {
          state.generateMode = 'image';
          const imgTab = document.querySelector('.gen-tab[data-mode="image"]');
          if (imgTab) imgTab.classList.add('active');
          const framesGroup = document.querySelector('.gen-frames-group');
          if (framesGroup) framesGroup.style.display = 'none';
        }
      }
    });
  });

  // Advanced toggle
  document.getElementById('gen-adv-toggle')?.addEventListener('click', () => {
    const panel = document.getElementById('gen-advanced');
    const toggle = document.getElementById('gen-adv-toggle');
    if (!panel) return;
    const visible = panel.style.display !== 'none';
    panel.style.display = visible ? 'none' : '';
    if (toggle) toggle.textContent = visible ? 'Advanced settings ▸' : 'Advanced settings ▾';
  });

  // Generate button
  document.getElementById('btn-generate')?.addEventListener('click', doGenerate);

  // Enter key in prompt
  document.getElementById('gen-prompt')?.addEventListener('keydown', e => {
    if (e.key === 'Enter' && e.metaKey) {
      e.preventDefault();
      doGenerate();
    }
  });

  // Restore persisted results
  restoreGeneratedResults();
}

async function doGenerate() {
  if (state.generateBusy) return;

  const promptEl = document.getElementById('gen-prompt');
  const prompt = promptEl?.value.trim();
  if (!prompt) return;

  const negPrompt = document.getElementById('gen-neg-prompt')?.value || '';
  const numSteps = parseInt(document.getElementById('gen-steps')?.value || '25');
  const width = parseInt(document.getElementById('gen-width')?.value || '512');
  const height = parseInt(document.getElementById('gen-height')?.value || '512');
  const numFrames = parseInt(document.getElementById('gen-frames')?.value || '16');
  const mode = state.generateMode;

  state.generateBusy = true;
  const btn = document.getElementById('btn-generate');
  if (btn) {
    btn.classList.add('generating');
    btn.innerHTML = '<span class="spinner"></span> Generating…';
    btn.disabled = true;
  }

  // Add placeholder card
  const tempId = 'gen-tmp-' + Date.now();
  addGeneratedCard({ id: tempId, prompt, mode, loading: true });
  saveGeneratedResults();

  try {
    let endpoint, body;
    if (state.generateProvider === 'cloud') {
      endpoint = '/api/generate/cloud_image';
      body = { prompt, negative_prompt: negPrompt, num_steps: 4, height: Math.min(height, 1440), width: Math.min(width, 1440) };
    } else {
      endpoint = mode === 'image' ? '/api/generate/image' : '/api/generate/video';
      body = { prompt, negative_prompt: negPrompt, num_steps: numSteps, height, width };
      if (mode === 'video') body.num_frames = numFrames;
    }

    const result = await api(endpoint, 'POST', body);

    const genMode = state.generateProvider === 'cloud' ? 'cloud' : mode;

    removeGeneratedCard(tempId);
    state.generatedItems.unshift({
      id: 'gen-' + Date.now(),
      prompt,
      mode: genMode,
      url: result.url,
      filename: result.filename,
      timestamp: new Date().toISOString(),
    });
  } catch (err) {
    removeGeneratedCard(tempId);
    state.generatedItems.unshift({
      id: 'gen-' + Date.now(),
      prompt,
      mode: state.generateProvider === 'cloud' ? 'cloud' : mode,
      error: err.message,
      timestamp: new Date().toISOString(),
    });
  }

  state.generateBusy = false;
  if (btn) {
    btn.classList.remove('generating');
    btn.innerHTML = 'Generate';
    btn.disabled = false;
  }

  renderGeneratedResults();
  saveGeneratedResults();
}

function addGeneratedCard(item) {
  const grid = document.getElementById('gen-results-grid');
  if (!grid) return;

  // Remove empty state
  const empty = grid.querySelector('.grid-empty');
  if (empty) empty.remove();

  const card = document.createElement('div');
  card.className = 'gen-result-card';
  card.id = item.id;
  card.style.position = 'relative';

  const typeLabel = item.mode === 'video' ? 'VID' : (item.mode === 'cloud' ? 'CLOUD' : 'IMG');

  if (item.loading) {
    card.innerHTML = `
      <div class="gen-result-media" style="position: relative;">
        <div class="gen-loading-overlay">
          <span class="spinner"></span>
        </div>
        <div class="gen-result-type">${typeLabel}</div>
      </div>
      <div class="gen-result-prompt">${escHtml(item.prompt)}</div>`;
  } else if (item.error) {
    card.innerHTML = `
      <div class="gen-result-media" style="position: relative; display: flex; align-items: center; justify-content: center; background: rgba(239,68,68,0.1);">
        <span style="color: var(--red); font-size: 0.8rem; padding: 12px; text-align: center;">${escHtml(item.error)}</span>
        <div class="gen-result-type">ERR</div>
      </div>
      <div class="gen-result-prompt">${escHtml(item.prompt)}</div>`;
  } else if (item.url) {
    const media = item.mode === 'video'
      ? `<video src="${item.url}" autoplay loop muted playsinline style="width:100%;height:100%;object-fit:cover;" onclick="event.stopPropagation();"></video>`
      : `<img src="${item.url}" alt="${escHtml(item.prompt)}" loading="lazy" />`;
    card.innerHTML = `
      <div class="gen-result-media" style="position: relative;">
        ${media}
        <div class="gen-result-type">${typeLabel}</div>
      </div>
      <div class="gen-result-prompt">${escHtml(item.prompt)}</div>`;
    card.addEventListener('click', function() {
      openGenPreview(item);
    });
  }

  grid.prepend(card);

  // Update count
  updateGeneratedCount();
}

function removeGeneratedCard(id) {
  document.getElementById(id)?.remove();
}

function renderGeneratedResults() {
  const grid = document.getElementById('gen-results-grid');
  if (!grid) return;

  grid.innerHTML = '';
  if (state.generatedItems.length === 0) {
    grid.innerHTML = `
      <div class="grid-empty">
        <div class="empty-icon">✨</div>
        <div>Generated images and videos will appear here…</div>
      </div>`;
  } else {
    state.generatedItems.forEach(item => addGeneratedCard(item));
  }
  updateGeneratedCount();
}

function updateGeneratedCount() {
  const count = document.getElementById('gen-count');
  if (count) {
    const realItems = state.generatedItems.filter(i => !i.loading && !i.error);
    count.textContent = realItems.length;
  }
}

function saveGeneratedResults() {
  try {
    const toSave = state.generatedItems.filter(i => !i.loading);
    localStorage.setItem('reelmind_generated', JSON.stringify(toSave.slice(0, 20)));
  } catch {}
}

function restoreGeneratedResults() {
  try {
    const saved = localStorage.getItem('reelmind_generated');
    if (saved) {
      state.generatedItems = JSON.parse(saved);
    }
  } catch {}
}

// ── Generate Preview Modal ─────────────────────────────────────────────────────

function openGenPreview(item) {
  if (!item || !item.url) return;

  const modal = document.getElementById('gen-preview-modal');
  const mediaContainer = document.getElementById('gen-preview-media');
  const promptEl = document.getElementById('gen-preview-prompt');
  const downloadBtn = document.getElementById('gen-preview-download');

  if (item.mode === 'video') {
    mediaContainer.innerHTML = `<video src="${item.url}" controls autoplay loop playsinline style="max-width:100%;max-height:60vh;"></video>`;
    downloadBtn.download = item.filename || 'generated.gif';
  } else {
    mediaContainer.innerHTML = `<img src="${item.url}" alt="${escHtml(item.prompt)}" style="max-width:100%;max-height:60vh;" />`;
    downloadBtn.download = item.filename || 'generated.png';
  }

  downloadBtn.href = item.url;
  promptEl.textContent = item.prompt || '';
  modal.showModal();
}

document.getElementById('gen-preview-close')?.addEventListener('click', function() {
  document.getElementById('gen-preview-modal')?.close();
});

document.getElementById('gen-preview-close-btn')?.addEventListener('click', function() {
  document.getElementById('gen-preview-modal')?.close();
});

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', init);
