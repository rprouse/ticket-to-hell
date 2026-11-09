// Fills in file sizes, download counts and release details from GitHub releases.
// The download links in index.html already point at /releases/latest/download/<file>,
// so they always serve the newest release. This script leaves those links alone (so a
// copied link stays evergreen) and only adds the sizes, counts and release date.
//
// Sizes and the date come from the latest release. Download counts are added up across
// every release by file name, so they don't drop back to zero when a new release is
// published. GitHub's counts can lag by a few minutes.

(function () {
  "use strict";

  var API = "https://api.github.com/repos/tth-dieppe/tth-dieppe.github.io/releases?per_page=100";

  function formatSize(bytes) {
    if (bytes >= 100e6) return Math.round(bytes / 1e6) + " MB";
    if (bytes >= 1e6) return (bytes / 1e6).toFixed(1) + " MB";
    return Math.max(1, Math.round(bytes / 1e3)) + " KB";
  }

  function formatDate(iso) {
    try {
      return new Date(iso).toLocaleDateString("en-CA", { year: "numeric", month: "long", day: "numeric" });
    } catch (e) {
      return iso.slice(0, 10);
    }
  }

  function formatCount(n) {
    return n.toLocaleString("en-CA") + (n === 1 ? " download" : " downloads");
  }

  function apply(releases) {
    releases = releases.filter(function (r) { return !r.draft && !r.prerelease; });
    if (!releases.length) return;
    var latest = releases[0]; // the API lists newest first

    var assets = {};
    (latest.assets || []).forEach(function (a) { assets[a.name] = a; });

    var counts = {};
    var total = 0;
    releases.forEach(function (r) {
      (r.assets || []).forEach(function (a) {
        counts[a.name] = (counts[a.name] || 0) + a.download_count;
        total += a.download_count;
      });
    });

    document.querySelectorAll("[data-asset]").forEach(function (link) {
      var name = link.getAttribute("data-asset");
      var asset = assets[name];
      var size = link.querySelector(".size");
      if (asset && size) size.textContent = formatSize(asset.size);

      if (counts[name]) {
        var note = document.createElement("p");
        note.className = "count";
        note.textContent = formatCount(counts[name]);
        link.insertAdjacentElement("afterend", note);
      }
    });

    var info = document.getElementById("release-info");
    if (info && latest.html_url) {
      var text = "Latest release: " + formatDate(latest.published_at) + " (" + latest.tag_name + "). ";
      if (total) text += "Downloaded " + total.toLocaleString("en-CA") + " times so far. ";
      info.textContent = text;
      var link = document.createElement("a");
      link.href = latest.html_url;
      link.textContent = "Release notes";
      info.appendChild(link);
    }
  }

  if (!window.fetch) return;
  fetch(API, { headers: { Accept: "application/vnd.github+json" } })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (releases) { if (Array.isArray(releases)) apply(releases); })
    .catch(function () { /* the links still work; sizes and counts just stay hidden */ });
})();
