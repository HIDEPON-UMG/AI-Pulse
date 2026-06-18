/* ============================================================
   AI-Pulse — shared behaviour
   category filtering · digest headline · thumbnail fallback
   (palette switcher は 2026-06-05 に Azure Mid 単独へ集約・削除)
   ============================================================ */
(function () {
  "use strict";

  /* Swallow benign cross-document View Transition rejections */
  window.addEventListener("unhandledrejection", function (e) {
    if (e && e.reason && /transition was skipped/i.test(String(e.reason && e.reason.message || e.reason))) {
      e.preventDefault();
    }
  });

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
      var n = items.filter(function (el) { return !el.hidden; }).length;
      document.querySelectorAll("[data-count]").forEach(function (counter) {
        counter.textContent = String(n).padStart(2, "0");
      });
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

  /* ---- Mobile swipe navigation (表示順に沿った主要ページ遷移) ----
     ユーザー要件 2026-06-18: スマホの横スワイプ順をメニュー表示順に一致させる。
     - 順序: feed → buzzpost → karte_index → repo_radar → archive (左スワイプ = 次のページへ)
     - 両端 (feed の右端 / archive の左端) では何もしない (循環しない)
     - 個別カルテ (data-page="karte") では発火しない (戻る導線は親カルテ一覧経由)
     - desktop (>= 769px) では発火しない (誤クリック防止 + マウス UX を変えない)
     - スクロール領域内の縦スクロールと干渉しないよう、垂直移動が大きい時はキャンセル
     - 0.6s 超のスローモーションも誤検知 (慎重なドラッグの可能性) としてキャンセル

     なぜ document.body の touch event か:
     ヘッダ・chip-bar・フィード本体すべてを横断するため body 上で listen し、
     passive:true で縦スクロールの主経路を絶対に塞がない。preventDefault() は
     呼ばず、判定後に location.href で遷移する。 */
  function initSwipeNav() {
    if (document.documentElement.clientWidth >= 769) return;  // desktop は対象外
    var page = document.body.dataset.page || "";
    var ORDER = ["feed", "buzzpost", "karte_index", "repo_radar", "archive"];
    var idx = ORDER.indexOf(page);
    if (idx < 0) return;  // 個別カルテなど ORDER 外は対象外
    var TARGETS = {
      "feed": "index.html",
      "buzzpost": "buzz-posts.html",
      "karte_index": "karte-index.html",
      "repo_radar": "repo-radar.html",
      "archive": "archive.html",
    };
    var X_THRESHOLD = 60;   // 水平移動 60px 以上で発火 (人差し指ストロークの平均)
    var Y_TOLERANCE = 50;   // 垂直 50px 超は縦スクロール意図とみなしキャンセル
    var T_MAX = 600;        // 600ms 超は誤操作 / 慎重なドラッグでキャンセル

    var x0 = 0, y0 = 0, t0 = 0, tracking = false;

    document.body.addEventListener("touchstart", function (ev) {
      if (ev.touches.length !== 1) { tracking = false; return; }
      var t = ev.touches[0];
      x0 = t.clientX; y0 = t.clientY; t0 = Date.now(); tracking = true;
    }, { passive: true });

    document.body.addEventListener("touchend", function (ev) {
      if (!tracking) return;
      tracking = false;
      var t = ev.changedTouches[0];
      var dx = t.clientX - x0;
      var dy = t.clientY - y0;
      var dt = Date.now() - t0;
      if (dt > T_MAX) return;
      if (Math.abs(dy) > Y_TOLERANCE) return;       // 縦スクロール優先
      if (Math.abs(dx) < X_THRESHOLD) return;       // 短すぎ
      if (Math.abs(dx) < Math.abs(dy) * 1.2) return; // 角度が斜め過ぎ
      var nextIdx = dx < 0 ? idx + 1 : idx - 1;     // 左スワイプ = 次、右 = 前
      if (nextIdx < 0 || nextIdx >= ORDER.length) return;  // 両端で止める
      var target = TARGETS[ORDER[nextIdx]];
      if (target) location.href = target;
    }, { passive: true });

    document.body.addEventListener("touchcancel", function () {
      tracking = false;
    }, { passive: true });
  }

  function boot() { initFilter(); initThumbs(); initDigest(); initSwipeNav(); }

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
    /* (2026-06-08) summary_points 由来の display_headline を優先表示。
       長い直訳 headline_ja を digest に使うと大見出しが省略されるため、要約済みタイトルだけを採用する。 */
    var hjaEl = top.querySelector(".headline-ja");
    var hEl = top.querySelector("h2");
    var h = (top.dataset.digestTitle || "").trim() ||
      (hEl ? hEl.textContent.trim() : "") ||
      (hjaEl ? hjaEl.textContent.trim() : "");
    /* (2026-06-05) 主語マーカー規則見直し:
       旧 dash split (h.split(/[—–-]/)) は英文見出しに dash が無いと見出し全文を <mark> 化していた
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
    el.innerHTML = html + " — " +
      "本日は<mark>" + escHtml(cat) + "</mark>が主役。";
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
