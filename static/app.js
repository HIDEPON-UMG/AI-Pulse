/* ============================================================
   AI-Pulse — shared behaviour
   palette persistence · category filtering
   ============================================================ */
(function () {
  "use strict";

  /* Swallow benign cross-document View Transition rejections */
  window.addEventListener("unhandledrejection", function (e) {
    if (e && e.reason && /transition was skipped/i.test(String(e.reason && e.reason.message || e.reason))) {
      e.preventDefault();
    }
  });

  /* ---- Palette switcher (persisted) ---- */
  var KEY = "aipulse-palette";
  function applyPalette(p) {
    if (p && p !== "cyan") document.documentElement.setAttribute("data-palette", p);
    else document.documentElement.removeAttribute("data-palette");
    document.querySelectorAll(".palette-switch button").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.palette === (p || "cyan")));
    });
  }
  function initPalette() {
    var saved = "cyan";
    try { saved = localStorage.getItem(KEY) || "cyan"; } catch (e) {}
    applyPalette(saved);
    document.querySelectorAll(".palette-switch button").forEach(function (b) {
      b.addEventListener("click", function () {
        var p = b.dataset.palette;
        applyPalette(p);
        try { localStorage.setItem(KEY, p); } catch (e) {}
      });
    });
  }

  /* ---- Category filter chips ---- */
  function initFilter() {
    var bar = document.querySelector("[data-filter-bar]");
    if (!bar) return;
    var chips = Array.prototype.slice.call(bar.querySelectorAll(".chip"));
    var items = Array.prototype.slice.call(document.querySelectorAll("[data-filter-item]"));
    var catChips = chips.filter(function (c) { return !c.classList.contains("all"); });
    var allCats = catChips.map(function (c) { return c.dataset.cat; });
    var selected = new Set(allCats);   /* default: every category selected */
    var first = true;
    var searchEl = document.querySelector("[data-search]");
    var query = "";

    function shows(el) {
      var catOk = selected.has(el.dataset.cat);
      var qOk = !query || el.textContent.toLowerCase().indexOf(query) !== -1;
      return catOk && qOk;
    }

    function render() {
      catChips.forEach(function (c) {
        c.setAttribute("aria-pressed", String(selected.has(c.dataset.cat)));
      });
      items.forEach(function (el) {
        el.hidden = !shows(el);
      });
      /* empty-date groups in archive */
      document.querySelectorAll("[data-date-group]").forEach(function (g) {
        var any = g.querySelectorAll("[data-filter-item]:not([hidden])").length > 0;
        g.hidden = !any;
      });
      /* live count */
      var counter = document.querySelector("[data-count]");
      if (counter) {
        var n = items.filter(function (el) { return !el.hidden; }).length;
        counter.textContent = String(n).padStart(2, "0");
      }
      var empty = document.querySelector(".empty");
      if (empty) {
        var visible = items.filter(function (el) { return !el.hidden; }).length;
        empty.style.display = visible === 0 ? "block" : "none";
      }
      first = false;
    }

    chips.forEach(function (c) {
      c.addEventListener("click", function () {
        if (c.classList.contains("all")) {
          selected = new Set(allCats);          /* reset: select every category */
        } else {
          var k = c.dataset.cat;
          if (selected.has(k)) selected.delete(k); else selected.add(k);
        }
        render();
      });
    });
    if (searchEl) {
      searchEl.addEventListener("input", function () {
        query = searchEl.value.trim().toLowerCase();
        render();
      });
    }
    render();
  }

  function boot() { initPalette(); initFilter(); initThumbs(); initDigest(); }

  /* ---- Dynamic daily digest headline (derived from top-score story) ---- */
  function initDigest() {
    var el = document.querySelector("[data-digest]");
    if (!el) return;
    var stories = Array.prototype.slice.call(document.querySelectorAll(".story[data-score]"));
    if (!stories.length) return;
    var top = stories.reduce(function (a, b) {
      return (+b.dataset.score || 0) > (+a.dataset.score || 0) ? b : a;
    });
    var cat = top.dataset.catname || "生成AI";
    var hEl = top.querySelector("h2");
    var h = hEl ? hEl.textContent.trim() : "";
    var subj = h.split(/[\u2014\u2013-]/)[0].trim() || h;
    el.textContent = subj + " \u2014 \u672c\u65e5\u306f" + cat + "\u304c\u4e3b\u5f79\u3002";
  }

  /* ---- Thumbnails: real image if present, else category fallback ---- */
  function initThumbs() {
    document.querySelectorAll("img.thumb").forEach(function (img) {
      var host = img.closest("[data-cat]");
      var cat = (host && host.dataset.cat) || "model";
      var fb = "thumb-" + cat + ".svg";
      var real = (img.getAttribute("data-thumb") || "").trim();
      img.addEventListener("error", function () {
        if (img.getAttribute("src") !== fb) img.src = fb;
      });
      img.src = real || fb;
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
