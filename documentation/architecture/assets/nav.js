/* Builds the sidebar nav on every architecture page and wires the "Pause animations" button.
   The page list lives here only: to add or rename a page, edit PAGES and nothing else.
   Each page carries <meta name="verified-at" content="commit <sha> · <date>">, written by
   .claude/team/archdocs.py stamp. Each page includes <nav class="sidenav" aria-label="Architecture pages"></nav> and loads this
   script with `defer`. Works over http:// and file://. */
(function () {
  var PAGES = [
    { group: null, items: [["index.html", "Overview"]] },
    { group: "Runtime", items: [
      ["pages/deployment.html", "Deployment & config"],
      ["pages/backend-api.html", "Backend API"],
      ["pages/auth-tenancy.html", "Auth & multi-tenancy"],
      ["pages/observability.html", "Observability"],
    ]},
    { group: "Data", items: [
      ["pages/database.html", "Database & migrations"],
      ["pages/wcl-data.html", "WCL client, cache & store"],
      ["pages/knowledge-base.html", "Knowledge base"],
    ]},
    { group: "Agent", items: [
      ["pages/agent.html", "Agent runtime & tools"],
      ["pages/models.html", "Models & providers"],
    ]},
    { group: "User-facing", items: [
      ["pages/streaming.html", "Stream protocol"],
      ["pages/frontend.html", "Frontend"],
      ["pages/pdf-reports.html", "PDF reports"],
    ]},
    { group: "Status", items: [
      ["pages/open-points.html", "Planned, drift & open points"],
      ["pages/maintaining.html", "Keeping these docs current"],
    ]},
  ];

  var me = document.currentScript && document.currentScript.src;
  var root = me ? me.replace(/assets\/nav\.js(\?.*)?$/, "") : "";
  var here = location.href.split("#")[0].split("?")[0];
  if (/\/$/.test(here)) here += "index.html";

  function esc(t) { return t.replace(/&/g, "&amp;").replace(/</g, "&lt;"); }
  // Any element with class "verified" shows the page's stamp, so the commit is written in one place.
  var meta = document.querySelector('meta[name="verified-at"]');
  if (meta) document.querySelectorAll(".verified").forEach(function (el) {
    el.textContent = "Verified against " + meta.content + ".";
  });

  var nav = document.querySelector("nav.sidenav");
  if (nav) {
    var stamp = document.querySelector('meta[name="verified-at"]');
    var html = '<a class="home" href="' + root + 'index.html">WCL Agent architecture</a>' +
      '<button class="navtoggle" type="button" aria-expanded="false">Pages</button><div class="links">';
    PAGES.forEach(function (g) {
      if (g.group) html += '<div class="grp">' + g.group + "</div>";
      g.items.forEach(function (it) {
        var href = root + it[0];
        var cur = href === here ? ' aria-current="page"' : "";
        html += '<a class="pg" href="' + href + '"' + cur + ">" + it[1].replace(/&/g, "&amp;") + "</a>";
      });
    });
    if (stamp) html += '<p class="stamp">Verified against ' + esc(stamp.content) + "</p>";
    nav.innerHTML = html + "</div>";
    var t = nav.querySelector(".navtoggle");
    t.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      t.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  var btn = document.querySelector(".pausebtn");
  if (btn) btn.addEventListener("click", function () {
    var on = document.documentElement.classList.toggle("paused");
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    btn.textContent = on ? "Play animations" : "Pause animations";
  });
})();
