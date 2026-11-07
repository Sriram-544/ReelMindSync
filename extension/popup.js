document.getElementById('sync-btn').addEventListener('click', function() {
  var btn = document.getElementById('sync-btn');
  var statusEl = document.getElementById('status');

  btn.disabled = true;
  statusEl.textContent = 'Scanning page...';
  statusEl.className = '';

  chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
    var tab = tabs[0];

    if (!tab || !tab.url) {
      statusEl.textContent = 'Error: Cannot access page. Try refreshing Instagram.';
      statusEl.className = 'error';
      btn.disabled = false;
      return;
    }

    if (tab.url.indexOf('instagram.com') === -1) {
      statusEl.textContent = 'Please open Instagram first (instagram.com/saved).';
      statusEl.className = 'error';
      btn.disabled = false;
      return;
    }

    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: scrapeReels
    }, function(results) {
      if (chrome.runtime.lastError) {
        statusEl.textContent = 'Error: ' + chrome.runtime.lastError.message;
        statusEl.className = 'error';
        btn.disabled = false;
        return;
      }

      var reels = (results && results[0] && results[0].result) ? results[0].result : [];

      if (reels.length === 0) {
        statusEl.textContent = 'No reels found. Make sure you are on instagram.com/saved.';
        statusEl.className = 'error';
        btn.disabled = false;
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
        btn.disabled = false;
      })
      .catch(function(err) {
        statusEl.textContent = 'Error: ' + err.message;
        statusEl.className = 'error';
        btn.disabled = false;
      });
    });
  });
});

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
