/* Tustco Dashboard - our own free-form dashboard. No frameworks, no CDN. */
(function () {
  "use strict";

  var S = {
    layout: { cards: [] },
    states: {},
    editing: false,
    snap: true,
    phone: false,
    saveTimer: null
  };

  var COLORS = ["#5fd0c5", "#ffb454", "#ff6b81", "#8ea2ff", "#a6e22e", "#c678dd"];
  var DISPLAY = /[?&]display=1/.test(window.location.search);
  var canvas = document.getElementById("canvas");
  var statusEl = document.getElementById("status");

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function defaultLayout() {
    return {
      cards: [
        { id: "c1", type: "text", title: "TUSTCO // LOCAL CONTROL", x: 24, y: 24, w: 520, h: 84,
          text: "Everything here runs on the Pi. No cloud, no account, no telemetry." },
        { id: "c2", type: "clock", title: "LOCAL TIME", x: 1450, y: 24, w: 400, h: 150 },
        { id: "c3", type: "media", title: "Curved TV (55\")", x: 24, y: 136, w: 330, h: 180,
          entity: "media_player.samsung_6_series_55" },
        { id: "c4", type: "media", title: "Living Room Display", x: 372, y: 136, w: 330, h: 180,
          entity: "media_player.living_room_display" },
        { id: "c5", type: "media", title: "32\" TV", x: 720, y: 136, w: 330, h: 180,
          entity: "media_player.tv_samsung_4_series_32" },
        { id: "c6", type: "group", title: "LIVING ROOM (logical device)", x: 1068, y: 136, w: 460, h: 230,
          entities: ["media_player.samsung_6_series_55", "media_player.tv_samsung_6_series_55",
                     "media_player.living_room_display", "media_player.tv_samsung_4_series_32"] },
        { id: "c7", type: "state", title: "Black toner", x: 24, y: 344, w: 260, h: 140,
          entity: "sensor.hl_l2360d_black_toner_remaining" },
        { id: "c8", type: "state", title: "Page counter", x: 302, y: 344, w: 260, h: 140,
          entity: "sensor.hl_l2360d_page_counter" },
        { id: "c9", type: "state", title: "Drum life", x: 580, y: 344, w: 260, h: 140,
          entity: "sensor.hl_l2360d_drum_remaining_life" },
        { id: "c10", type: "chart", title: "TIMELINE - toner / pages / drum", x: 24, y: 502, w: 930, h: 330,
          entities: ["sensor.hl_l2360d_black_toner_remaining", "sensor.hl_l2360d_page_counter",
                     "sensor.hl_l2360d_drum_remaining_life"], hours: 24 }
      ]
    };
  }

  async function api(path, options) {
    var r = await fetch("/ha/" + path, options);
    var data;
    try { data = await r.json(); } catch (e) { data = {}; }
    if (!r.ok) throw new Error(data.error || ("HTTP " + r.status));
    return data;
  }

  function setStatus(msg, kind) {
    statusEl.textContent = msg;
    statusEl.className = "status" + (kind ? " " + kind : "");
  }

  async function refreshStates() {
    try {
      var list = await api("states");
      var map = {};
      (list || []).forEach(function (s) { map[s.entity_id] = s; });
      S.states = map;
      populateDatalist(list || []);
      updateBindings();
      setStatus("LIVE - " + Object.keys(map).length + " entities", "live");
    } catch (e) {
      setStatus("HA unreachable: " + e.message, "err");
    }
  }

  function populateDatalist(list) {
    var dl = document.getElementById("entityList");
    if (!dl || dl.childElementCount) return;
    list.forEach(function (s) {
      var o = document.createElement("option");
      o.value = s.entity_id;
      dl.appendChild(o);
    });
  }

  function friendly(id) {
    var s = S.states[id];
    return (s && s.attributes && s.attributes.friendly_name) || id;
  }

  function updateBindings() {
    document.querySelectorAll("[data-entity]").forEach(function (node) {
      var s = S.states[node.getAttribute("data-entity")];
      var mode = node.getAttribute("data-mode") || "state";
      if (!s) { node.textContent = "unavailable"; return; }
      if (mode === "unit") {
        node.textContent = (s.attributes && s.attributes.unit_of_measurement) || "";
      } else if (mode === "badge") {
        var off = ["off", "unavailable", "unknown"].indexOf(s.state) !== -1;
        node.textContent = s.state;
        node.className = "state-badge" + (off ? " off" : "");
      } else if (mode === "friendly") {
        node.textContent = (s.attributes && s.attributes.friendly_name) || node.getAttribute("data-entity");
      } else {
        node.textContent = s.state;
      }
    });
  }

  function saveLayout() {
    clearTimeout(S.saveTimer);
    S.saveTimer = setTimeout(function () {
      fetch("/layout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(S.layout)
      }).then(function (r) {
        if (!r.ok) setStatus("layout save failed", "err");
      }).catch(function () { setStatus("layout save failed", "err"); });
    }, 250);
  }

  /* ---------- card bodies ---------- */

  function bodyState(card, host) {
    var v = el("div", "bigval");
    var num = el("span", "", "?");
    num.setAttribute("data-entity", card.entity);
    var unit = el("span", "unit");
    unit.setAttribute("data-entity", card.entity);
    unit.setAttribute("data-mode", "unit");
    v.appendChild(num);
    v.appendChild(unit);
    host.appendChild(v);
    var sub = el("div", "sub", friendly(card.entity));
    sub.setAttribute("data-entity", card.entity);
    sub.setAttribute("data-mode", "friendly");
    // friendly names come from attributes, not state; fill once now
    sub.textContent = friendly(card.entity);
    host.appendChild(sub);
  }

  function bodyMedia(card, host) {
    var badge = el("span", "state-badge", "?");
    badge.setAttribute("data-entity", card.entity);
    badge.setAttribute("data-mode", "badge");
    host.appendChild(badge);
    var id = el("div", "sub", card.entity);
    host.appendChild(id);
    var controls = el("div", "controls");
    var on = el("button", "", "TURN ON");
    var off = el("button", "", "TURN OFF");
    on.addEventListener("click", function () { callService(card.entity, true); });
    off.addEventListener("click", function () { callService(card.entity, false); });
    controls.appendChild(on);
    controls.appendChild(off);
    host.appendChild(controls);
  }

  async function callService(entity, turnOn) {
    var svc = turnOn ? "media_player/turn_on" : "media_player/turn_off";
    try {
      await api("services/" + svc, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entity_id: entity })
      });
      setStatus("service sent: " + entity, "live");
      setTimeout(refreshStates, 1200);
    } catch (e) {
      setStatus("service failed: " + e.message, "err");
    }
  }

  function bodyGroup(card, host) {
    (card.entities || []).forEach(function (id) {
      var row = el("div", "group-row");
      var name = el("span", "", friendly(id) || id);
      var val = el("span", "v", "?");
      val.setAttribute("data-entity", id);
      row.appendChild(name);
      row.appendChild(val);
      host.appendChild(row);
    });
  }

  function bodyClock(card, host) {
    var t = el("div", "clocktime", "--:--:--");
    t.className = "clocktime";
    t.setAttribute("data-clock", "time");
    var d = el("div", "clockdate", "");
    d.setAttribute("data-clock", "date");
    host.appendChild(t);
    host.appendChild(d);
  }

  function bodyText(card, host) {
    var t = el("div", "textdata", card.text || "");
    host.appendChild(t);
  }

  function bodyChart(card, host) {
    var legend = el("div", "legend");
    (card.entities || []).forEach(function (id, i) {
      var item = el("span", "");
      var dot = el("i", "");
      dot.style.background = COLORS[i % COLORS.length];
      item.appendChild(dot);
      item.appendChild(document.createTextNode(friendly(id) || id));
      legend.appendChild(item);
    });
    host.appendChild(legend);
    var cvs = document.createElement("canvas");
    cvs.setAttribute("data-chart", card.id);
    host.appendChild(cvs);
  }

  async function drawChart(card) {
    var cvs = document.querySelector('canvas[data-chart="' + card.id + '"]');
    if (!cvs || !(card.entities || []).length) return;
    var hours = card.hours || 24;
    var end = new Date();
    var start = new Date(end.getTime() - hours * 3600 * 1000);
    var query = card.entities.map(encodeURIComponent).join(",");
    var path = "history/period/" + start.toISOString() + "?filter_entity_id=" + query;
    try {
      var data = await api(path);
      var ctx = cvs.getContext("2d");
      var dpr = window.devicePixelRatio || 1;
      var w = cvs.clientWidth, h = cvs.clientHeight;
      cvs.width = Math.max(1, Math.floor(w * dpr));
      cvs.height = Math.max(1, Math.floor(h * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      var series = [];
      var allTimes = [];
      (data || []).forEach(function (points) {
        var vals = [];
        (points || []).forEach(function (p) {
          var n = parseFloat(p.state);
          if (!isNaN(n)) {
            var t = new Date(p.last_changed).getTime();
            vals.push({ t: t, v: n });
            allTimes.push(t);
          }
        });
        series.push(vals);
      });
      var any = series.some(function (s) { return s.length > 0; });
      if (!any) {
        ctx.fillStyle = "#9fb0c4";
        ctx.font = "14px sans-serif";
        ctx.fillText("No numeric history yet for these entities", 8, 22);
        return;
      }
      var tMin = Math.min.apply(null, allTimes);
      var tMax = Math.max.apply(null, allTimes);
      if (tMax === tMin) tMax = tMin + 1000;

      ctx.strokeStyle = "#2b3542";
      ctx.lineWidth = 1;
      for (var g = 0; g <= 4; g++) {
        var gy = 8 + (h - 24) * g / 4;
        ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(w, gy); ctx.stroke();
      }
      series.forEach(function (vals, i) {
        if (!vals.length) return;
        var lo = Infinity, hi = -Infinity;
        vals.forEach(function (p) { lo = Math.min(lo, p.v); hi = Math.max(hi, p.v); });
        if (hi === lo) hi = lo + 1;
        var span = hi - lo;
        ctx.strokeStyle = COLORS[i % COLORS.length];
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        vals.forEach(function (p, idx) {
          var x = 6 + (w - 12) * (p.t - tMin) / (tMax - tMin);
          var y = 8 + (h - 24) * (1 - (p.v - lo) / span);
          if (idx === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.stroke();
      });
      ctx.fillStyle = "#9fb0c4";
      ctx.font = "12px sans-serif";
      ctx.fillText(new Date(tMin).toLocaleString(), 6, h - 4);
      var right = new Date(tMax).toLocaleString();
      ctx.fillText(right, w - ctx.measureText(right).width - 6, h - 4);
    } catch (e) {
      var ctx2 = cvs.getContext("2d");
      ctx2.fillStyle = "#ffb454";
      ctx2.font = "13px sans-serif";
      ctx2.fillText("history unavailable: " + e.message, 8, 22);
    }
  }

  function refreshCharts() {
    S.layout.cards.forEach(function (c) { if (c.type === "chart") drawChart(c); });
  }

  function tickClock() {
    var now = new Date();
    document.querySelectorAll("[data-clock='time']").forEach(function (n) {
      n.textContent = now.toLocaleTimeString();
    });
    document.querySelectorAll("[data-clock='date']").forEach(function (n) {
      n.textContent = now.toLocaleDateString(undefined, { weekday: "long", year: "numeric", month: "short", day: "numeric" });
    });
  }

  /* ---------- layout / interaction ---------- */

  function makeInteractive(node, card) {
    var head = node.querySelector(".card-head");
    var handle = node.querySelector(".resize");
    head.addEventListener("pointerdown", function (e) {
      if (!S.editing || e.target.closest("button") || S.phone) return;
      e.preventDefault();
      var sx = e.clientX, sy = e.clientY, ox = card.x, oy = card.y;
      head.setPointerCapture(e.pointerId);
      function move(ev) {
        var nx = ox + ev.clientX - sx, ny = oy + ev.clientY - sy;
        if (S.snap) { nx = Math.round(nx / 8) * 8; ny = Math.round(ny / 8) * 8; }
        card.x = Math.max(0, nx); card.y = Math.max(0, ny);
        node.style.left = card.x + "px";
        node.style.top = card.y + "px";
      }
      function up() {
        head.removeEventListener("pointermove", move);
        head.removeEventListener("pointerup", up);
        saveLayout();
      }
      head.addEventListener("pointermove", move);
      head.addEventListener("pointerup", up);
    });
    handle.addEventListener("pointerdown", function (e) {
      if (!S.editing || S.phone) return;
      e.preventDefault();
      var sx = e.clientX, sy = e.clientY, ow = card.w, oh = card.h;
      handle.setPointerCapture(e.pointerId);
      function move(ev) {
        var nw = ow + ev.clientX - sx, nh = oh + ev.clientY - sy;
        if (S.snap) { nw = Math.round(nw / 8) * 8; nh = Math.round(nh / 8) * 8; }
        card.w = Math.max(180, nw); card.h = Math.max(110, nh);
        node.style.width = card.w + "px";
        node.style.height = card.h + "px";
        if (card.type === "chart") drawChart(card);
      }
      function up() {
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", up);
        saveLayout();
      }
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", up);
    });
  }

  function render() {
    canvas.innerHTML = "";
    S.layout.cards.forEach(function (card) {
      var node = el("div", "card");
      node.setAttribute("data-type", card.type);
      node.style.left = card.x + "px";
      node.style.top = card.y + "px";
      node.style.width = card.w + "px";
      node.style.height = card.h + "px";

      var head = el("div", "card-head");
      head.appendChild(el("span", "title", card.title || card.type));
      var del = el("button", "mini delflag", "X");
      del.title = "Delete card";
      del.addEventListener("click", function () {
        if (!window.confirm("Delete this card?")) return;
        S.layout.cards = S.layout.cards.filter(function (c) { return c.id !== card.id; });
        saveLayout(); render(); refreshStates(); refreshCharts();
      });
      head.appendChild(del);
      node.appendChild(head);

      var body = el("div", "card-body");
      if (card.type === "state") bodyState(card, body);
      else if (card.type === "media") bodyMedia(card, body);
      else if (card.type === "group") bodyGroup(card, body);
      else if (card.type === "clock") bodyClock(card, body);
      else if (card.type === "text") bodyText(card, body);
      else if (card.type === "chart") bodyChart(card, body);
      node.appendChild(body);

      var resize = el("div", "resize");
      resize.title = "Resize";
      node.appendChild(resize);

      makeInteractive(node, card);
      canvas.appendChild(node);
    });
    tickClock();
    updateBindings();
    refreshCharts();
  }

  function setEditing(on) {
    S.editing = on;
    document.body.classList.toggle("editing", on);
    document.getElementById("editBtn").classList.toggle("active", on);
    document.getElementById("editBtn").textContent = on ? "DONE" : "EDIT";
  }

  function setPhone(on) {
    S.phone = on;
    document.body.classList.toggle("phone", on);
    document.getElementById("phoneBtn").classList.toggle("active", on);
    if (!on) render();
  }

  function setTheme(name, persist) {
    var lc = name === "lcars";
    document.body.classList.toggle("lcars", lc);
    var b = document.getElementById("themeBtn");
    b.classList.toggle("active", lc);
    b.textContent = lc ? "STANDARD" : "LCARS";
    if (persist) {
      S.layout.theme = lc ? "lcars" : "standard";
      saveLayout();
    }
  }

  /* ---------- add-card panel ---------- */

  function togglePanel(show) {
    var p = document.getElementById("addPanel");
    p.hidden = !show;
    if (show) document.getElementById("newTitle").focus();
  }

  function syncTypeFields() {
    var t = document.getElementById("newType").value;
    var single = ["state", "media"].indexOf(t) !== -1;
    var multi = t === "chart" || t === "group";
    document.getElementById("entityLabel").hidden = !single;
    document.getElementById("entitiesLabel").hidden = !multi;
  }

  function addCard() {
    var type = document.getElementById("newType").value;
    var title = document.getElementById("newTitle").value.trim() || type.toUpperCase();
    var card = {
      id: "c" + Date.now().toString(36),
      type: type, title: title,
      x: 40 + (S.layout.cards.length % 4) * 40,
      y: 40 + (S.layout.cards.length % 6) * 30,
      w: type === "chart" ? 620 : 320,
      h: type === "chart" ? 300 : 170
    };
    if (type === "state" || type === "media") {
      card.entity = document.getElementById("newEntity").value.trim();
    } else if (type === "chart" || type === "group") {
      card.entities = document.getElementById("newEntities").value.split(",")
        .map(function (s) { return s.trim(); }).filter(Boolean);
      if (type === "chart") card.hours = 24;
    } else if (type === "text") {
      card.text = "New text - turn on EDIT to move or resize this card.";
    }
    S.layout.cards.push(card);
    togglePanel(false);
    saveLayout(); render();
    document.getElementById("newTitle").value = "";
    document.getElementById("newEntity").value = "";
    document.getElementById("newEntities").value = "";
  }

  /* ---------- boot ---------- */

  async function boot() {
    document.getElementById("editBtn").addEventListener("click", function () { setEditing(!S.editing); });
    document.getElementById("phoneBtn").addEventListener("click", function () { setPhone(!S.phone); });
    document.getElementById("themeBtn").addEventListener("click", function () {
      setTheme(document.body.classList.contains("lcars") ? "standard" : "lcars", true);
    });
    document.getElementById("addBtn").addEventListener("click", function () { togglePanel(true); });
    document.getElementById("addCancel").addEventListener("click", function () { togglePanel(false); });
    document.getElementById("addConfirm").addEventListener("click", addCard);
    document.getElementById("newType").addEventListener("change", syncTypeFields);
    document.getElementById("resetBtn").addEventListener("click", function () {
      if (!window.confirm("Replace the current layout with the starter layout?")) return;
      var keepTheme = S.layout.theme || "lcars";
      S.layout = defaultLayout();
      S.layout.theme = keepTheme;
      saveLayout(); render(); refreshStates();
    });
    document.addEventListener("keydown", function (e) {
      var t = e.target.tagName;
      if (t === "INPUT" || t === "TEXTAREA" || t === "SELECT") return;
      if (e.key === "e" || e.key === "E") setEditing(!S.editing);
      if (e.key === "Escape") togglePanel(false);
    });
    window.addEventListener("resize", function () {
      document.querySelectorAll('canvas[data-chart]').forEach(function (c) {
        var card = S.layout.cards.filter(function (x) { return x.id === c.getAttribute("data-chart"); })[0];
        if (card) drawChart(card);
      });
    });

    if (DISPLAY) document.body.classList.add("display");
    try {
      var r = await fetch("/layout" + (DISPLAY ? "?display=1" : ""));
      var saved = await r.json();
      if (saved && Array.isArray(saved.cards) && saved.cards.length) {
        S.layout = saved;
      } else {
        S.layout = defaultLayout();
        saveLayout();
      }
    } catch (e) {
      S.layout = defaultLayout();
    }
    if (window.matchMedia && window.matchMedia("(max-width: 700px)").matches) setPhone(true);
    setTheme(S.layout.theme || "lcars", false);
    syncTypeFields();
    render();
    // Tell the local server the real viewport so a wall display can get a
    // layout sized to its screen. Best-effort, never blocks the dashboard.
    try {
      fetch("/viewport", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ w: window.innerWidth, h: window.innerHeight,
          dpr: window.devicePixelRatio || 1, ua: navigator.userAgent })
      }).catch(function () {});
    } catch (e) {}
    await refreshStates();
    refreshCharts();
    setInterval(refreshStates, 10000);
    setInterval(refreshCharts, 120000);
    setInterval(tickClock, 1000);
  }

  boot();
})();
