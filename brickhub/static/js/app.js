/* BRICK HUB storefront — progressive enhancement, no dependencies. */
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");
  const compact = window.matchMedia("(max-width: 1080px)");

  /* ---------- broken external photos → generated illustration ---------- */
  document.addEventListener("error", (e) => {
    const img = e.target;
    if (img.tagName === "IMG" && img.dataset.fallback && img.src !== new URL(img.dataset.fallback, location.href).href) {
      img.src = img.dataset.fallback;
      img.removeAttribute("srcset");
    }
  }, true);
  // images that failed before JS loaded
  $$("img[data-fallback]").forEach((img) => {
    if (img.complete && img.naturalWidth === 0) img.src = img.dataset.fallback;
  });

  /* ---------- toasts ---------- */
  const toasts = $("[data-toasts]");
  const ICON = { error: "i-alert", warning: "i-alert", success: "i-check", info: "i-info" };
  function dismiss(t) {
    if (!t || t.classList.contains("is-leaving")) return;
    t.classList.add("is-leaving");
    setTimeout(() => t.remove(), 220);
  }
  function arm(t) {
    let left = 4500, started = Date.now(), timer = null;
    const run = () => { started = Date.now(); timer = setTimeout(() => dismiss(t), left); };
    const pause = () => { clearTimeout(timer); left -= Date.now() - started; };
    run();
    t.addEventListener("pointerenter", pause);
    t.addEventListener("pointerleave", run);
    document.addEventListener("visibilitychange", () => (document.hidden ? pause() : run()));
  }
  function toast(message, type = "success") {
    if (!toasts || !message) return;
    const t = document.createElement("div");
    t.className = `toast ${type}`;
    t.innerHTML = `<svg class="ic"><use href="#${ICON[type] || "i-info"}"/></svg><span></span><button class="toast-close" type="button" aria-label="Закрити">×</button>`;
    t.querySelector("span").textContent = message;
    toasts.appendChild(t);
    while (toasts.children.length > 3) toasts.firstElementChild.remove();
    arm(t);
  }
  window.bhToast = toast;
  $$("[data-autohide]").forEach(arm);
  document.addEventListener("click", (e) => {
    const b = e.target.closest(".toast-close");
    if (b) dismiss(b.closest(".toast"));
  });

  /* ---------- drawers ---------- */
  const backdrop = $("[data-backdrop]");
  let openDrawer = null, lastFocus = null;
  function open(el) {
    if (!el) return;
    if (openDrawer && openDrawer !== el) close();
    lastFocus = document.activeElement;
    openDrawer = el;
    el.classList.add("is-open");
    el.setAttribute("aria-hidden", "false");
    backdrop && backdrop.classList.add("is-open");
    document.documentElement.style.overflow = "hidden";
    const f = el.querySelector("button, a, input");
    f && setTimeout(() => f.focus({ preventScroll: true }), 50);
  }
  function close() {
    if (!openDrawer) return;
    openDrawer.classList.remove("is-open");
    openDrawer.setAttribute("aria-hidden", "true");
    backdrop && backdrop.classList.remove("is-open");
    document.documentElement.style.overflow = "";
    openDrawer = null;
    lastFocus && lastFocus.focus && lastFocus.focus({ preventScroll: true });
  }
  window.bhOpenDrawer = open;
  document.addEventListener("click", (e) => {
    const opener = e.target.closest("[data-open-drawer]");
    if (opener) { e.preventDefault(); open(document.getElementById(opener.dataset.openDrawer)); return; }
    if (e.target.closest("[data-close-drawer]") || e.target === backdrop) close();
    if (e.target.closest("[data-open-filters]")) open($("[data-filters]"));
    if (e.target.closest("[data-close-filters]")) close();
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { close(); closeMenus(); closeSearch(); } });

  /* ---------- mega menu ---------- */
  const menus = $$("[data-menu]");
  let hoverTimer = null;
  function closeMenus(except) {
    menus.forEach((m) => {
      if (m !== except) { m.classList.remove("is-open"); const b = m.querySelector(".nav-link"); b && b.setAttribute("aria-expanded", "false"); }
    });
  }
  menus.forEach((m) => {
    const btn = m.querySelector(".nav-link");
    btn.addEventListener("click", () => {
      const willOpen = !m.classList.contains("is-open");
      closeMenus(m);
      m.classList.toggle("is-open", willOpen);
      btn.setAttribute("aria-expanded", String(willOpen));
    });
    m.addEventListener("pointerenter", (e) => {
      if (e.pointerType !== "mouse") return;
      clearTimeout(hoverTimer);
      const anyOpen = menus.some((x) => x.classList.contains("is-open"));
      hoverTimer = setTimeout(() => { closeMenus(m); m.classList.add("is-open"); btn.setAttribute("aria-expanded", "true"); }, anyOpen ? 0 : 120);
    });
    m.addEventListener("pointerleave", (e) => {
      if (e.pointerType !== "mouse") return;
      clearTimeout(hoverTimer);
      hoverTimer = setTimeout(() => { m.classList.remove("is-open"); btn.setAttribute("aria-expanded", "false"); }, 180);
    });
  });
  document.addEventListener("click", (e) => { if (!e.target.closest("[data-menu]")) closeMenus(); });

  /* ---------- search suggestions ---------- */
  const searchBox = $("[data-search]");
  const input = $("[data-search-input]");
  const panel = $("[data-search-panel]");
  let searchCtl = null, searchTimer = null, active = -1;
  const fmt = (v) => new Intl.NumberFormat("uk-UA", { maximumFractionDigits: 2, minimumFractionDigits: Number(v) % 1 ? 2 : 0 }).format(Number(v)) + " ₴";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  function closeSearch() { panel && panel.classList.remove("is-open"); active = -1; }
  function renderSuggest(data) {
    if (!panel) return;
    if (!data.items.length && !data.design) {
      panel.innerHTML = `<div class="sp-empty">Нічого не знайдено за «${esc(data.query)}». Спробуйте номер набору чи деталі.</div>`;
    } else {
      let html = "";
      if (data.design) {
        html += `<a class="sp-design" href="${data.design.url}"><svg class="ic"><use href="#i-brick"/></svg>Деталь ${esc(data.design.id)} — ${esc(data.design.name)} · ${data.design.colors} кол.</a>`;
      }
      html += data.items.map((it) => `
        <a class="sp-item" href="${it.url}" role="option">
          <img src="${esc(it.img)}" alt="" ${it.fallback ? `data-fallback="${esc(it.fallback)}"` : ""} loading="lazy">
          <span><span class="t">${esc(it.title)}</span>
            <span class="m">${esc(it.kind)}${it.number ? ` · <b class="mono">${esc(it.number)}</b>` : ""}${it.color ? ` · <span class="swatch" style="--c:${esc(it.hex)}"></span>${esc(it.color)}` : ""}${it.stock > 0 ? "" : " · немає"}</span></span>
          <span class="p">${fmt(it.price)}</span>
        </a>`).join("");
      if (data.total > data.items.length) html += `<a class="sp-all" href="${data.all_url}">Усі результати (${data.total}) →</a>`;
      panel.innerHTML = html;
    }
    panel.classList.add("is-open");
    active = -1;
  }
  if (input && panel) {
    input.addEventListener("input", () => {
      clearTimeout(searchTimer);
      const q = input.value.trim();
      if (q.length < 2) { closeSearch(); return; }
      searchTimer = setTimeout(async () => {
        searchCtl && searchCtl.abort();
        searchCtl = new AbortController();
        try {
          const r = await fetch(`/api/poshuk/?q=${encodeURIComponent(q)}`, { signal: searchCtl.signal, headers: { Accept: "application/json" } });
          if (r.ok) renderSuggest(await r.json());
        } catch (_) { /* aborted */ }
      }, 160);
    });
    input.addEventListener("keydown", (e) => {
      const items = $$(".sp-item, .sp-design, .sp-all", panel);
      if (!panel.classList.contains("is-open") || !items.length) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        active = (active + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
        items.forEach((it, i) => it.classList.toggle("is-active", i === active));
      } else if (e.key === "Enter" && active >= 0) {
        e.preventDefault();
        location.href = items[active].href;
      }
    });
    input.addEventListener("focus", () => { if (panel.innerHTML.trim() && input.value.trim().length >= 2) panel.classList.add("is-open"); });
    document.addEventListener("click", (e) => { if (!e.target.closest("[data-search]")) closeSearch(); });
  }

  /* ---------- fetch helpers ---------- */
  async function post(form) {
    const r = await fetch(form.action, { method: "POST", body: new FormData(form), headers: { "X-Requested-With": "fetch", Accept: "application/json" }, credentials: "same-origin" });
    let data = {};
    try { data = await r.json(); } catch (_) { /* not json */ }
    return { ok: r.ok, data };
  }
  function setCount(sel, n) {
    $$(sel).forEach((el) => {
      el.textContent = n;
      el.dataset.count = n;
      el.classList.remove("bump");
      void el.offsetWidth;
      el.classList.add("bump");
    });
  }

  /* ---------- add to cart ---------- */
  document.addEventListener("submit", async (e) => {
    const form = e.target;
    if (form.matches("[data-add-to-cart]")) {
      e.preventDefault();
      const btn = form.querySelector("[type=submit]");
      btn && btn.classList.add("is-loading");
      try {
        const { ok, data } = await post(form);
        if (data.count !== undefined) setCount("[data-cart-count]", data.count);
        if (ok) {
          if (btn) {
            btn.classList.add("is-done");
            const use = btn.querySelector("use");
            const prev = use && use.getAttribute("href");
            use && use.setAttribute("href", "#i-check");
            setTimeout(() => { btn.classList.remove("is-done"); use && prev && use.setAttribute("href", prev); }, 1400);
          }
          const mini = $("[data-mini-cart]");
          if (mini && data.mini) { mini.innerHTML = data.mini; open($("#cart-drawer")); }
          else toast(data.message);
        } else {
          toast(data.message || "Не вдалося додати товар", "error");
        }
      } catch (_) {
        form.submit();
      } finally {
        btn && btn.classList.remove("is-loading");
      }
      return;
    }
    if (form.matches("[data-toggle]")) {
      e.preventDefault();
      const kind = form.dataset.toggle;
      try {
        const { ok, data } = await post(form);
        if (!ok) throw new Error();
        const btn = form.querySelector("button");
        btn.classList.toggle("is-active", data.active);
        btn.setAttribute("aria-pressed", String(data.active));
        const label = btn.querySelector("[data-label-on]");
        if (label) label.textContent = data.active ? label.dataset.labelOn : label.dataset.labelOff;
        // keep every button for the same product in sync
        const id = btn.dataset.fav || btn.dataset.compare;
        $$(`[data-${kind === "fav" ? "fav" : "compare"}="${id}"]`).forEach((b) => { b.classList.toggle("is-active", data.active); b.setAttribute("aria-pressed", String(data.active)); });
        setCount(kind === "fav" ? "[data-fav-count]" : "[data-compare-count]", data.count);
        if (data.message) toast(data.message, "info");
        else if (kind === "compare" && data.active) toast("Додано до порівняння");
      } catch (_) { form.submit(); }
      return;
    }
    if (form.matches("[data-notify]")) {
      e.preventDefault();
      const { ok, data } = await post(form);
      toast(data.message || (ok ? "Готово" : "Помилка"), ok ? "success" : "error");
      if (ok) form.reset();
    }
  });

  /* ---------- quantity steppers ---------- */
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-step]");
    if (!b) return;
    const box = b.closest("[data-stepper]");
    const inp = box && box.querySelector("input");
    if (!inp) return;
    const min = Number(inp.min || 1), max = Number(inp.max || 999999);
    const big = e.shiftKey ? 10 : 1;
    inp.value = Math.min(max, Math.max(min, (Number(inp.value) || min) + Number(b.dataset.step) * big));
    inp.dispatchEvent(new Event("change", { bubbles: true }));
  });
  document.addEventListener("change", (e) => {
    const inp = e.target;
    if (inp.matches("[data-stepper] input")) {
      const min = Number(inp.min || 1), max = Number(inp.max || 999999);
      if (Number(inp.value) > max) { inp.value = max; toast(`Доступно лише ${max} шт.`, "info"); }
      if (Number(inp.value) < min || !inp.value) inp.value = min;
      const auto = inp.closest("[data-auto-update]");
      if (auto) { clearTimeout(auto._t); auto._t = setTimeout(() => auto.requestSubmit(), 450); }
    }
  });

  /* ---------- copy to clipboard ---------- */
  document.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-copy]");
    if (!b) return;
    try {
      await navigator.clipboard.writeText(b.dataset.copy);
      b.classList.add("is-done");
      const use = b.querySelector("use");
      use && use.setAttribute("href", "#i-check");
      setTimeout(() => { b.classList.remove("is-done"); use && use.setAttribute("href", "#i-copy"); }, 1200);
    } catch (_) { toast(b.dataset.copy, "info"); }
  });

  /* ---------- gallery ---------- */
  $$("[data-gallery]").forEach((g) => {
    const main = g.querySelector("[data-gallery-main]");
    const thumbs = () => Array.from(g.querySelectorAll("[data-src]"));
    const show = (t) => {
      if (!t || !main) return;
      thumbs().forEach((x) => x.classList.toggle("is-active", x === t));
      if (t.dataset.fallback) main.dataset.fallback = t.dataset.fallback; else delete main.dataset.fallback;
      main.src = t.dataset.src;
    };
    g.addEventListener("click", (e) => {
      const step = e.target.closest("[data-gallery-step]");
      if (step) {
        const list = thumbs();
        const i = list.findIndex((x) => x.classList.contains("is-active"));
        show(list[(i + Number(step.dataset.galleryStep) + list.length) % list.length]);
        return;
      }
      show(e.target.closest("[data-src]"));
    });
  });

  /* ---------- colour / variant picker: each colour is its own listing ---------- */
  $$("[data-variant-select]").forEach((sel) => {
    sel.addEventListener("change", () => { if (sel.value) location.href = sel.value; });
  });

  /* ---------- rails ---------- */
  $$("[data-rail]").forEach((rail) => {
    const track = rail.querySelector("[data-rail-track]");
    const prev = rail.querySelector("[data-rail-prev]");
    const next = rail.querySelector("[data-rail-next]");
    const sync = () => {
      prev.disabled = track.scrollLeft < 8;
      next.disabled = track.scrollLeft + track.clientWidth >= track.scrollWidth - 8;
    };
    prev.addEventListener("click", () => track.scrollBy({ left: -track.clientWidth * 0.9, behavior: "smooth" }));
    next.addEventListener("click", () => track.scrollBy({ left: track.clientWidth * 0.9, behavior: "smooth" }));
    track.addEventListener("scroll", sync, { passive: true });
    window.addEventListener("resize", sync);
    sync();
  });

  /* ---------- filters & sorting ---------- */
  document.addEventListener("change", (e) => {
    const el = e.target;
    if (!el.matches("[data-autosubmit]")) return;
    const form = el.form;
    if (!form) return;
    // inside the mobile filter drawer we wait for the "Показати" button
    if (compact.matches && form.matches("[data-filter-form]")) return;
    form.requestSubmit ? form.requestSubmit() : form.submit();
  });
  $$("[data-filter-form]").forEach((form) => {
    form.addEventListener("submit", () => {
      $$("input", form).forEach((i) => { if ((i.type === "number" || i.type === "hidden") && !i.value) i.disabled = true; });
    });
  });
})();

/* LiqPay hand-off: submit automatically, keep the button as a fallback. */
(() => {
  const f = document.querySelector("[data-autopay]");
  if (f) setTimeout(() => f.submit(), 600);
})();

/* Confirm destructive form submissions. */
document.addEventListener("submit", (e) => {
  const f = e.target.closest("form[data-confirm]");
  if (f && !window.confirm(f.dataset.confirm)) { e.preventDefault(); e.stopImmediatePropagation(); }
}, true);

/* Searchable selects: type to filter long lists (colours, series, categories).
   The native <select> stays in the form and keeps the value. */
(() => {
  "use strict";
  const norm = (s) => (s || "").toLowerCase().replace(/[’'ʼ`]/g, "").replace(/\s+/g, " ").trim();
  let uid = 0;

  function enhance(sel) {
    if (sel.dataset.comboReady) return;
    sel.dataset.comboReady = "1";
    const id = `combo-${++uid}`;
    const wrap = document.createElement("div");
    wrap.className = "combo";
    const field = document.createElement("div");
    field.className = "combo-field";
    const chip = document.createElement("span");
    chip.className = "combo-chip";
    chip.hidden = true;
    const input = document.createElement("input");
    input.type = "text";
    input.className = "combo-input";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.placeholder = sel.dataset.placeholder || "Почніть вводити…";
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", id);
    if (sel.getAttribute("aria-label")) input.setAttribute("aria-label", sel.getAttribute("aria-label"));
    const label = sel.id ? document.querySelector(`label[for="${sel.id}"]`) : null;
    if (label) {
      label.id = label.id || `${id}-label`;
      input.setAttribute("aria-labelledby", label.id);
      label.addEventListener("click", (e) => { e.preventDefault(); input.focus(); });
    }
    const list = document.createElement("div");
    list.className = "combo-list";
    list.id = id;
    list.setAttribute("role", "listbox");
    list.hidden = true;
    sel.parentNode.insertBefore(wrap, sel);
    field.append(chip, input);
    wrap.append(sel, field, list);
    sel.classList.add("combo-native");
    sel.tabIndex = -1;
    sel.setAttribute("aria-hidden", "true");

    const opts = Array.from(sel.options).map((o) => ({
      value: o.value,
      label: o.value === "" && /^-+$/.test(o.textContent.trim()) ? "— не вибрано —" : o.textContent.trim(),
      hex: o.dataset.hex || "",
      search: norm(`${o.textContent} ${o.dataset.search || ""}`),
    }));
    let shown = [];
    let active = -1;

    const current = () => opts.find((o) => o.value === sel.value);
    function sync() {
      const o = current();
      input.value = o && o.value !== "" ? o.label : "";
      const hex = o && o.value !== "" ? o.hex : "";
      chip.hidden = !hex;
      wrap.classList.toggle("has-chip", Boolean(hex));
      if (hex) chip.style.setProperty("--c", hex);
    }
    function highlight() {
      Array.from(list.children).forEach((el, i) => el.classList.toggle("is-active", i === active));
      const el = list.children[active];
      if (el && el.id) {
        el.scrollIntoView({ block: "nearest" });
        input.setAttribute("aria-activedescendant", el.id);
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    }
    function render(q) {
      const terms = norm(q).split(" ").filter(Boolean);
      shown = opts.filter((o) => terms.every((t) => o.search.includes(t)));
      if (terms.length) {
        const starts = (o) => (norm(o.label).startsWith(terms[0]) ? 1 : 0);
        shown.sort((a, b) => starts(b) - starts(a));
      }
      shown = shown.slice(0, 250);
      list.replaceChildren();
      if (!shown.length) {
        const empty = document.createElement("div");
        empty.className = "combo-empty";
        empty.textContent = "Нічого не знайдено";
        list.append(empty);
      }
      shown.forEach((o, i) => {
        const el = document.createElement("div");
        el.className = "combo-opt";
        el.id = `${id}-${i}`;
        el.setAttribute("role", "option");
        el.setAttribute("aria-selected", String(o.value === sel.value));
        if (o.hex) {
          const sw = document.createElement("span");
          sw.className = "swatch";
          sw.style.setProperty("--c", o.hex);
          el.append(sw);
        }
        const text = document.createElement("span");
        text.textContent = o.label;
        el.append(text);
        el.addEventListener("mousedown", (e) => { e.preventDefault(); choose(o); });
        list.append(el);
      });
      active = !shown.length ? -1 : terms.length ? 0 : Math.max(0, shown.findIndex((o) => o.value === sel.value));
      highlight();
    }
    function open(q) {
      render(q);
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }
    function close() {
      list.hidden = true;
      input.setAttribute("aria-expanded", "false");
      active = -1;
    }
    function choose(o) {
      sel.value = o.value;
      sel.dispatchEvent(new Event("change", { bubbles: true }));
      sync();
      close();
    }

    list.addEventListener("mousedown", (e) => e.preventDefault());
    input.addEventListener("focus", () => { input.select(); open(""); });
    input.addEventListener("click", () => { if (list.hidden) open(""); });
    input.addEventListener("input", () => open(input.value));
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (list.hidden) open("");
        if (!shown.length) return;
        active = (active + (e.key === "ArrowDown" ? 1 : -1) + shown.length) % shown.length;
        highlight();
      } else if (e.key === "Enter") {
        if (!list.hidden && shown[active]) { e.preventDefault(); choose(shown[active]); }
      } else if (e.key === "Escape") {
        if (!list.hidden) { e.preventDefault(); e.stopPropagation(); close(); sync(); }
      } else if (e.key === "Tab") {
        close();
        sync();
      }
    });
    input.addEventListener("blur", () => setTimeout(() => { if (document.activeElement !== input) { close(); sync(); } }, 120));
    sel.addEventListener("change", sync);
    sync();
  }

  document.querySelectorAll("select[data-searchable]").forEach(enhance);
})();
