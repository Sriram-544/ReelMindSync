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

  btn.addEventListener("click", function() {
    btn.disabled = true;
    btn.innerHTML = '\u23F3 Scanning...';
    showToast("Scanning page for reels...", "info");

    setTimeout(function() {
      scrapeAndSync();
    }, 200);
  });

  function scrapeAndSync() {
    var reels = [];
    var seen = {};
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
          reels.push({ url: url, shortcode: shortcode, thumbnail_url: thumbnail });
        }
      }
    }

    if (reels.length === 0) {
      showToast("No reels found on this page. Scroll to load more, then try again.", "error");
      btn.disabled = false;
      btn.innerHTML = '\uD83C\uDFAC Sync to ReelMind';
      return;
    }

    showToast("Found " + reels.length + " reels. Sending...", "info");

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
