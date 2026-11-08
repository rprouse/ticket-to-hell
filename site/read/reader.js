// Online reading edition: reading settings, progress bar, "continue reading", and the picture viewer.
// Everything is stored in this browser only (localStorage); nothing is sent anywhere.

(function () {
  "use strict";

  var root = document.documentElement;
  var body = document.body;
  var page = body.getAttribute("data-page");
  var KEY = "tth-progress";
  var SIZES = [0.85, 0.92, 1, 1.1, 1.22, 1.36];

  function get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function set(k, v) { try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} }

  // ---------------------------------------------------------------- settings panel
  var btn = document.querySelector(".settings-btn");
  var panel = document.getElementById("settings");

  function markSettings() {
    var scale = parseFloat(get("tth-size") || "1");
    panel.querySelectorAll("[data-size]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-size") === "0" && scale === 1));
    });
    var theme = get("tth-theme") || "";
    panel.querySelectorAll("[data-theme-set]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-theme-set") === theme));
    });
  }

  if (btn && panel) {
    btn.addEventListener("click", function () {
      var open = panel.hidden;
      panel.hidden = !open;
      btn.setAttribute("aria-expanded", String(open));
      if (open) markSettings();
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && !panel.hidden) { panel.hidden = true; btn.setAttribute("aria-expanded", "false"); btn.focus(); }
    });
    document.addEventListener("click", function (ev) {
      if (!panel.hidden && !panel.contains(ev.target) && ev.target !== btn) {
        panel.hidden = true; btn.setAttribute("aria-expanded", "false");
      }
    });
    panel.addEventListener("click", function (ev) {
      var b = ev.target.closest("button");
      if (!b) return;
      if (b.hasAttribute("data-size")) {
        var step = parseInt(b.getAttribute("data-size"), 10);
        var cur = parseFloat(get("tth-size") || "1");
        var i = SIZES.indexOf(cur); if (i < 0) i = 2;
        var next = step === 0 ? 1 : SIZES[Math.max(0, Math.min(SIZES.length - 1, i + step))];
        root.style.setProperty("--scale", next);
        set("tth-size", next === 1 ? null : String(next));
      } else if (b.hasAttribute("data-theme-set")) {
        var t = b.getAttribute("data-theme-set");
        if (t) root.setAttribute("data-theme", t); else root.removeAttribute("data-theme");
        set("tth-theme", t || null);
      }
      markSettings();
    });
  }

  // ---------------------------------------------------------------- progress bar and saved place
  var bar = document.querySelector(".progress span");
  var isChapter = body.classList.contains("is-chapter");

  function fraction() {
    var max = document.documentElement.scrollHeight - window.innerHeight;
    return max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
  }

  if (isChapter) {
    var ticking = false, saveTimer = null;
    var save = function () {
      set(KEY, JSON.stringify({ page: page, title: body.getAttribute("data-title"), at: Math.round(fraction() * 1000) / 1000 }));
    };
    window.addEventListener("scroll", function () {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(function () { if (bar) bar.style.width = (fraction() * 100) + "%"; ticking = false; });
      }
      clearTimeout(saveTimer);
      saveTimer = setTimeout(save, 400);
    }, { passive: true });

    // Coming back from "Continue reading": return to the saved spot.
    if (location.hash === "#resume") {
      var saved = null;
      try { saved = JSON.parse(get(KEY)); } catch (e) {}
      history.replaceState(null, "", location.pathname);
      if (saved && saved.page === page) {
        var go = function () { window.scrollTo(0, saved.at * (document.documentElement.scrollHeight - window.innerHeight)); };
        if (document.readyState === "complete") go(); else window.addEventListener("load", go);
      }
    } else if (!location.hash) {
      save();
    }
  }

  // Contents page: offer to continue where the reader left off.
  if (page === "index") {
    var p = null;
    try { p = JSON.parse(get(KEY)); } catch (e) {}
    var box = document.getElementById("continue");
    if (p && p.page && box) {
      var link = document.querySelector('ol.toc a[href="' + p.page + '.html"]');
      if (link) {
        link.parentNode.classList.add("current");
        box.innerHTML = "";
        var a = document.createElement("a");
        a.className = "button";
        a.href = p.page + ".html#resume";
        a.textContent = "Continue reading: " + p.title;
        box.appendChild(a);
        box.hidden = false;
        var start = document.getElementById("start");
        if (start) { start.textContent = "Start from the beginning"; start.className = "button secondary"; }
      }
    }
  }

  // ---------------------------------------------------------------- picture viewer
  if (!window.HTMLDialogElement) return;   // without <dialog>, the links just open the large picture
  var dlg = null, img, cap;

  function viewer() {
    if (dlg) return dlg;
    dlg = document.createElement("dialog");
    dlg.className = "lightbox";
    dlg.setAttribute("aria-label", "Picture");
    dlg.innerHTML = '<button type="button" class="lb-close" aria-label="Close">×</button><figure><img alt=""><figcaption></figcaption></figure>';
    body.appendChild(dlg);
    img = dlg.querySelector("img");
    cap = dlg.querySelector("figcaption");
    dlg.querySelector(".lb-close").addEventListener("click", function () { dlg.close(); });
    // Tap the picture to switch between fitting the screen and full size; tap the background to close.
    img.addEventListener("click", function (ev) { ev.stopPropagation(); img.classList.toggle("fit"); img.style.cursor = img.classList.contains("fit") ? "zoom-in" : "zoom-out"; });
    dlg.addEventListener("click", function (ev) { if (ev.target === dlg || ev.target.tagName === "FIGURE") dlg.close(); });
    dlg.addEventListener("close", function () { img.removeAttribute("src"); });
    return dlg;
  }

  document.addEventListener("click", function (ev) {
    var a = ev.target.closest("a.zoom");
    if (!a || ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button !== 0) return;
    ev.preventDefault();
    var d = viewer();
    var fig = a.closest("figure");
    var small = a.querySelector("img");
    var fc = fig && fig.querySelector("figcaption");
    var text = "";
    if (fc) {
      var copy = fc.cloneNode(true);
      var tr = copy.querySelector(".transcription");
      if (tr) tr.remove();
      text = copy.textContent.trim();
    }
    img.className = "fit";
    img.style.cursor = "zoom-in";
    img.src = small.currentSrc || small.src;      // show the page image at once, then swap in the large one
    img.alt = small.alt;
    var big = new Image();
    big.onload = function () { if (d.open) img.src = big.src; };
    big.src = a.href;
    cap.textContent = text;
    d.showModal();
  });
})();
