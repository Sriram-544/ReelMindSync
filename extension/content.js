(function() {
  "use strict";

  if (document.getElementById("reelmind-sync-btn")) return;

  var btn = document.createElement("button");
  btn.id = "reelmind-sync-btn";
  btn.innerHTML = '\uD83C\uDFAC Sync to ReelMind';
  document.body.appendChild(btn);

  var toast = document.createElement("div");
  toast.id = "reelmind-toast";
  document.body.appendChild(toast);

  function showToast(msg, type) {
    toast.textContent = msg;
    toast.className = type || "info";
    setTimeout(function() {
      toast.classList.add("show");
    }, 50);
    clearTimeout(toast._timeout);
    toast._timeout = setTimeout(function() {
      toast.classList.remove("show");
    }, 4000);
  }

  btn.addEventListener("click", function(e) {
    btn.disabled = true;
    // If Shift was held, do quick visible scrape, otherwise auto-scroll
    autoScrollAndSync();
  });

  function collectReelsFromDom(seen) {
    var batch = [];
    var anchors = document.querySelectorAll('a[href^="/reel/"], a[href^="/p/"]');
    for (var i = 0; i < anchors.length; i++) {
      var a = anchors[i];
      var url = a.href.split("?")[0];
      var match = url.match(/\/(?:reel|p)\/([A-Za-z0-9_-]+)\/?$/);
      if (match) {
        var shortcode = match[1];
        if (!seen[shortcode]) {
          seen[shortcode] = true;
          var img = a.querySelector("img");
          var thumbnail = img ? img.src : "";
          batch.push({ url: url, shortcode: shortcode, thumbnail_url: thumbnail });
        }
      }
    }
    return batch;
  }

  async function autoScrollAndSync() {
    var allReels = [];
    var seen = {};
    var rounds = 0;
    var maxRounds = 12;
    var idleCount = 0;

    showToast("Collecting reels (Auto-scrolling)...", "info");

    while (rounds < maxRounds && idleCount < 3) {
      rounds++;
      var batch = collectReelsFromDom(seen);
      allReels = allReels.concat(batch);

      btn.innerHTML = '\u23F3 Found ' + allReels.length + ' reels...';
      showToast('Scanning round ' + rounds + '/' + maxRounds + ' — ' + allReels.length + ' reels found', 'info');

      if (batch.length === 0) {
        idleCount++;
      } else {
        idleCount = 0;
      }

      window.scrollBy({ top: 1200, behavior: 'smooth' });
      await new Promise(function(resolve) { setTimeout(resolve, 1100); });
    }

    if (allReels.length === 0) {
      showToast("No reels found on this page. Scroll to load more, then try again.", "error");
      btn.disabled = false;
      btn.innerHTML = '\uD83C\uDFAC Sync to ReelMind';
      return;
    }

    sendReelsToServer(allReels);
  }

  function sendReelsToServer(reels) {
    showToast("Found " + reels.length + " reels. Sending to ReelMind...", "info");
    btn.innerHTML = '\u23F3 Sending ' + reels.length + '...';

    fetch("http://localhost:8000/api/pipeline/start_from_extension", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reels: reels })
    })
    .then(function(res) {
      if (!res.ok) {
        return res.json().catch(function() {
          return { detail: res.statusText };
        }).then(function(err) {
          throw new Error(err.detail || "Server error");
        });
      }
      return res.json();
    })
    .then(function(data) {
      showToast("\u2713 " + reels.length + " reels synced! " + (data.message || ""), "success");
      btn.disabled = false;
      btn.innerHTML = '\uD83C\uDFAC Sync to ReelMind';
    })
    .catch(function(err) {
      showToast("Error: " + err.message, "error");
      btn.disabled = false;
      btn.innerHTML = '\uD83C\uDFAC Sync to ReelMind';
    });
  }
})();
