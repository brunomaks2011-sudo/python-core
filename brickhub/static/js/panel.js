/* BRICK HUB admin panel helpers */
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const csrf = () => ($("input[name=csrfmiddlewaretoken]") || {}).value || "";

  // sidebar on small screens
  const side = $("[data-panel-side]");
  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-panel-toggle]")) side && side.classList.toggle("is-open");
    else if (side && side.classList.contains("is-open") && !e.target.closest("[data-panel-side]")) side.classList.remove("is-open");
  });

  // inline price / stock editing
  $$("[data-quick]").forEach((input) => {
    let initial = input.value;
    const save = async () => {
      if (input.value === initial) return;
      const body = new FormData();
      body.append(input.dataset.field, input.value);
      body.append("csrfmiddlewaretoken", csrf());
      input.classList.remove("is-saved", "is-error");
      try {
        const r = await fetch(input.dataset.quick, { method: "POST", body, headers: { "X-Requested-With": "fetch" } });
        const data = await r.json();
        if (!r.ok || !data.ok) throw new Error(Object.values(data.errors || {})[0] || "Помилка");
        input.value = input.dataset.field === "price" ? data.price : data.quantity;
        initial = input.value;
        input.classList.add("is-saved");
        setTimeout(() => input.classList.remove("is-saved"), 1200);
      } catch (err) {
        input.classList.add("is-error");
        window.bhToast && window.bhToast(err.message || "Не вдалося зберегти", "error");
      }
    };
    input.addEventListener("change", save);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); input.blur(); save(); } });
  });

  // bulk selection
  const all = $("[data-check-all]");
  if (all) all.addEventListener("change", () => $$("input[name=ids]").forEach((c) => { c.checked = all.checked; }));
  const bulk = $("[data-bulk]");
  if (bulk) bulk.addEventListener("submit", (e) => {
    const action = bulk.querySelector("select[name=action]").value;
    const n = $$("input[name=ids]:checked").length;
    if (!action || !n) { e.preventDefault(); window.bhToast && window.bhToast("Оберіть товари та дію", "info"); return; }
    if (action === "delete" && !confirm(`Видалити ${n} товар(ів)?`)) e.preventDefault();
  });
  const importBtn = $("[data-confirm-import]");
  if (importBtn) importBtn.addEventListener("click", (e) => { if (!confirm("Записати дані у базу? Рекомендуємо спершу зробити перевірку.")) e.preventDefault(); });

  // product form: show fields for the chosen kind + catalogue lookup
  const pf = $("[data-product-form]");
  if (pf) {
    const kind = $("#id_kind", pf);
    const sync = () => $$("[data-kind-section]", pf).forEach((s) => { s.hidden = !s.dataset.kindSection.split(" ").includes(kind.value); });
    kind.addEventListener("change", sync);
    sync();
    const lookup = async (type) => {
      const input = type === "set" ? $("#id_set_number", pf) : type === "part" ? $("#id_design_id", pf) : $("#id_fig_number", pf);
      const out = $(`[data-lookup-out="${type}"]`, pf);
      const q = input.value.trim();
      if (!q) return;
      const k = type === "set" && kind.value === "accessory" ? "accessory" : type;
      const r = await fetch(`${pf.dataset.lookup}?kind=${k}&q=${encodeURIComponent(q)}`);
      const d = await r.json();
      out.className = "lookup-result " + (d.found ? "is-ok" : "is-bad");
      if (!d.found) { out.textContent = d.message || "Не знайдено в каталозі"; return; }
      const title = $("#id_title", pf);
      if (type === "set") {
        out.textContent = `✓ ${d.name} · ${d.year || "—"} · ${d.pieces || "?"} дет. · мініфігурок: ${d.minifigs ?? "?"}${d.theme ? " · " + d.theme : ""}` +
          (d.listings && d.listings.length ? ` · вже є лоти: ${d.listings.map((l) => l.sku).join(", ")}` : "");
        if (title && !title.value) title.placeholder = d.name;
        const set = (id, v) => { const el = $(id, pf); if (el && !el.value && v != null) el.value = v; };
        set("#id_year", d.year); set("#id_pieces", d.pieces); set("#id_minifigs_count", d.minifigs); set("#id_age_min", d.age);
        const theme = $("#id_theme", pf);
        if (theme && !theme.value && d.theme_id) theme.value = d.theme_id;
      } else if (type === "part") {
        out.textContent = `✓ ${d.design_id} — ${d.name}${d.name_uk ? " (" + d.name_uk + ")" : ""}` +
          (d.listings && d.listings.length ? ` · вже є: ${d.listings.length} лот(ів)` : "");
        if (title && !title.value) title.placeholder = d.name_uk || d.name;
        if (d.design_id && d.design_id !== q) $("#id_design_id", pf).value = d.design_id;
        if (d.color_id) $("#id_color", pf).value = d.color_id;
        const cat = $("#id_category", pf);
        if (cat && !cat.value && d.category_id) cat.value = d.category_id;
      } else {
        out.textContent = `✓ ${d.name}${d.year ? " · " + d.year : ""}`;
        if (title && !title.value) title.placeholder = d.name;
        const theme = $("#id_theme", pf);
        if (theme && !theme.value && d.theme_id) theme.value = d.theme_id;
      }
    };
    $$("[data-lookup-btn]", pf).forEach((b) => b.addEventListener("click", () => lookup(b.dataset.lookupBtn)));
    ["#id_set_number", "#id_design_id", "#id_fig_number"].forEach((sel, i) => {
      const el = $(sel, pf);
      el && el.addEventListener("change", () => lookup(["set", "part", "minifig"][i]));
    });
  }

  // drag & drop zones
  $$("[data-dropzone]").forEach((z) => {
    const input = z.querySelector("input[type=file]");
    ["dragenter", "dragover"].forEach((ev) => z.addEventListener(ev, (e) => { e.preventDefault(); z.classList.add("is-over"); }));
    ["dragleave", "drop"].forEach((ev) => z.addEventListener(ev, () => z.classList.remove("is-over")));
    z.addEventListener("drop", (e) => {
      e.preventDefault();
      if (input && e.dataTransfer.files.length) { input.files = e.dataTransfer.files; input.dispatchEvent(new Event("change")); }
    });
  });
})();
