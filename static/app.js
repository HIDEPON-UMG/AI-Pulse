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

  /* ---- Dynamic daily digest headline (derived from top-score story) ----
     News-Grasp 流の「行下半分マーカー」(linear-gradient 60% 区切り) を主語とカテゴリ名に当てる。
     textContent ではなく innerHTML を使うため、ユーザ供給文字列は escHtml で必ずエスケープ。
     CSS 側は .feed-head h1 mark で theme.css の全面塗り mark を override する。 */
  function escHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function initDigest() {
    var el = document.querySelector("[data-digest]");
    if (!el) return;
    var stories = Array.prototype.slice.call(document.querySelectorAll(".story[data-score]"));
    if (!stories.length) return;
    var top = stories.reduce(function (a, b) {
      return (+b.dataset.score || 0) > (+a.dataset.score || 0) ? b : a;
    });
    var cat = top.dataset.catname || "生成AI";
    var entname = (top.dataset.entname || "").trim();
    var hEl = top.querySelector("h2");
    var h = hEl ? hEl.textContent.trim() : "";
    /* (2026-06-05) 主語マーカー規則見直し:
       旧 dash split (h.split(/[\u2014\u2013-]/)) は英文見出しに dash が無いと見出し全文を <mark> 化していた
       (例: "DeepSeek slated to raise $7 billion ..." 全文が緑塗り事故)。
       新ルール: story の主 entity 名 (data-entname) が見出しに含まれる時のみ、
       その部分文字列のみ <mark>。含まれない場合はマーク無しで素の見出しを出す。 */
    var html;
    if (entname && h.indexOf(entname) >= 0) {
      var i = h.indexOf(entname);
      html = escHtml(h.slice(0, i)) +
             "<mark>" + escHtml(entname) + "</mark>" +
             escHtml(h.slice(i + entname.length));
    } else {
      html = escHtml(h);
    }
    el.innerHTML = html + " \u2014 " +
      "\u672c\u65e5\u306f<mark>" + escHtml(cat) + "</mark>\u304c\u4e3b\u5f79\u3002";
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
