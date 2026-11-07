function handleSync(autoScroll) {
  var quickBtn = document.getElementById('sync-btn');
  var scrollBtn = document.getElementById('sync-scroll-btn');
  var statusEl = document.getElementById('status');

  if (quickBtn) quickBtn.disabled = true;
  if (scrollBtn) scrollBtn.disabled = true;

  statusEl.textContent = autoScroll ? 'Auto-scrolling page to collect reels...' : 'Scanning visible reels...';
  statusEl.className = '';

  chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
    var tab = tabs[0];

    if (!tab || !tab.url) {
      statusEl.textContent = 'Error: Cannot access page. Try refreshing Instagram.';
      statusEl.className = 'error';
      if (quickBtn) quickBtn.disabled = false;
      if (scrollBtn) scrollBtn.disabled = false;
      return;
    }

    if (tab.url.indexOf('instagram.com') === -1) {
      statusEl.textContent = 'Please open Instagram first (instagram.com/saved).';
      statusEl.className = 'error';
      if (quickBtn) quickBtn.disabled = false;
      if (scrollBtn) scrollBtn.disabled = false;
      return;
    }

    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: autoScroll ? scrapeReelsWithScroll : scrapeReels
    }, function(results) {
      if (chrome.runtime.lastError) {
        statusEl.textContent = 'Error: ' + chrome.runtime.lastError.message;
        statusEl.className = 'error';
        if (quickBtn) quickBtn.disabled = false;
        if (scrollBtn) scrollBtn.disabled = false;
        return;
      }

      var reels = (results && results[0] && results[0].result) ? results[0].result : [];

      if (reels.length === 0) {
        statusEl.textContent = 'No reels found. Make sure you are on instagram.com/saved.';
        statusEl.className = 'error';
        if (quickBtn) quickBtn.disabled = false;
        if (scrollBtn) scrollBtn.disabled = false;
        return;
      }

      statusEl.textContent = 'Found ' + reels.length + ' reels. Sending to ReelMind...';

      fetch('http://localhost:8000/api/pipeline/start_from_extension', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reels: reels })
      })
      .then(function(res) {
        if (!res.ok) {
          return res.json().catch(function() {
            return { detail: res.statusText };
          }).then(function(err) {
            throw new Error(err.detail || 'Server error');
          });
        }
        return res.json();
      })
      .then(function(data) {
        statusEl.textContent = '\u2713 Sent ' + reels.length + ' reels! ' + (data.message || '');
        statusEl.className = '';
        if (quickBtn) quickBtn.disabled = false;
        if (scrollBtn) scrollBtn.disabled = false;
      })
      .catch(function(err) {
        statusEl.textContent = 'Error: ' + err.message;
        statusEl.className = 'error';
        if (quickBtn) quickBtn.disabled = false;
        if (scrollBtn) scrollBtn.disabled = false;
      });
    });
  });
}

document.getElementById('sync-btn')?.addEventListener('click', function() {
  handleSync(false);
});

document.getElementById('sync-scroll-btn')?.addEventListener('click', function() {
  handleSync(true);
});

async function scrapeReelsWithScroll() {
  var allReels = [];
  var seen = {};
  var rounds = 0;
  var maxRounds = 10;
  var idleCount = 0;

  while (rounds < maxRounds && idleCount < 3) {
    rounds++;
    var batch = [];
    var anchors = document.querySelectorAll('a[href^="/reel/"], a[href^="/p/"]');
    for (var i = 0; i < anchors.length; i++) {
      var a = anchors[i];
      var url = a.href.split('?')[0];
      var match = url.match(/\/(?:reel|p)\/([A-Za-z0-9_-]+)\/?$/);
      if (match) {
        var shortcode = match[1];
        if (!seen[shortcode]) {
          seen[shortcode] = true;
          var img = a.querySelector('img');
          var thumbnail = img ? img.src : '';
          batch.push({ url: url, shortcode: shortcode, thumbnail_url: thumbnail });
        }
      }
    }
    allReels = allReels.concat(batch);
    if (batch.length === 0) {
      idleCount++;
    } else {
      idleCount = 0;
    }
    window.scrollBy({ top: 1200, behavior: 'smooth' });
    await new Promise(function(resolve) { setTimeout(resolve, 900); });
  }

  return allReels;
}

function scrapeReels() {
  var reels = [];
  var seen = {};

  var anchors = document.querySelectorAll('a[href^="/reel/"], a[href^="/p/"]');
  for (var i = 0; i < anchors.length; i++) {
    var a = anchors[i];
    var url = a.href.split('?')[0];
    var match = url.match(/\/(?:reel|p)\/([A-Za-z0-9_-]+)\/?$/);
    if (match) {
      var shortcode = match[1];
      if (!seen[shortcode]) {
        seen[shortcode] = true;
        var img = a.querySelector('img');
        var thumbnail = img ? img.src : '';
        reels.push({ url: url, shortcode: shortcode, thumbnail_url: thumbnail });
      }
    }
  }
  return reels;
}
