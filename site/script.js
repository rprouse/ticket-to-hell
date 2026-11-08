// Fills in file sizes and release details from the latest GitHub release.
// The download links in index.html already point at /releases/latest/download/<file>,
// so they always serve the newest release. This script leaves those links alone (so a
// copied link stays evergreen) and only adds the sizes and release date.

(function () {
  "use strict";

  var API = "https://api.github.com/repos/tth-dieppe/tth-dieppe.github.io/releases/latest";

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

  function apply(release) {
    var assets = {};
    (release.assets || []).forEach(function (a) { assets[a.name] = a; });

    document.querySelectorAll("[data-asset]").forEach(function (link) {
      var asset = assets[link.getAttribute("data-asset")];
      if (!asset) return;
      var size = link.querySelector(".size");
      if (size) size.textContent = formatSize(asset.size);
    });

    var info = document.getElementById("release-info");
    if (info && release.html_url) {
      info.textContent = "Latest release: " + formatDate(release.published_at) + " (" + release.tag_name + "). ";
      var link = document.createElement("a");
      link.href = release.html_url;
      link.textContent = "Release notes";
      info.appendChild(link);
    }
  }

  if (!window.fetch) return;
  fetch(API, { headers: { Accept: "application/vnd.github+json" } })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (release) { if (release) apply(release); })
    .catch(function () { /* the links still work; sizes just stay hidden */ });
})();
