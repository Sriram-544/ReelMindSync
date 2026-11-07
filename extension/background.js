try {
  chrome.action.onClicked.addListener(async (tab) => {
    if (!tab.url || !tab.url.includes("instagram.com")) {
      chrome.notifications.create({
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: "ReelMind",
        message: "Please navigate to Instagram first, then click this icon."
      });
      return;
    }

    try {
      var results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: scrapeReelsFromPage
      });

      var reels = results[0] && results[0].result ? results[0].result : [];

      if (reels.length === 0) {
        chrome.notifications.create({
          type: "basic",
          iconUrl: "icons/icon128.png",
          title: "ReelMind",
          message: "No reel/post links found. Make sure you are on a page with reels (e.g. Saved page)."
        });
        return;
      }

      var res = await fetch("http://localhost:8000/api/pipeline/start_from_extension", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reels: reels })
      });

      if (!res.ok) {
        var err = await res.json().catch(function() { return { detail: res.statusText }; });
        throw new Error(err.detail || "Server error");
      }

      var data = await res.json();
      chrome.notifications.create({
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: "ReelMind",
        message: "Synced " + reels.length + " reels! " + (data.message || "")
      });
    } catch (e) {
      chrome.notifications.create({
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: "ReelMind - Error",
        message: String(e.message)
      });
    }
  });
} catch (e) {
  console.error("ReelMind init error:", e);
}

function scrapeReelsFromPage() {
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
  return reels;
}
