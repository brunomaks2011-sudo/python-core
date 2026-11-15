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
  if (bulk) {
    const actionSel = bulk.querySelector("select[name=action]");
    const extras = $$("[data-bulk-extra]", bulk);  // a second select for actions that need a value
    const syncExtra = () => extras.forEach((el) => { el.hidden = el.dataset.bulkExtra !== actionSel.value; });
    actionSel.addEventListener("change", syncExtra);
    syncExtra();
    bulk.addEventListener("submit", (e) => {
      const action = actionSel.value;
      const n = $$("input[name=ids]:checked").length;
      if (!action || !n) { e.preventDefault(); window.bhToast && window.bhToast("Оберіть товари та дію", "info"); return; }
      const extra = extras.find((el) => el.dataset.bulkExtra === action);
      if (extra && !extra.value) {
        e.preventDefault(); window.bhToast && window.bhToast(extra.getAttribute("aria-label") + ": оберіть значення", "info"); extra.focus(); return;
      }
      if (action === "delete" && !confirm(`Видалити ${n} товар(ів)?`)) e.preventDefault();
    });
  }
  const importBtn = $("[data-confirm-import]");
  if (importBtn) importBtn.addEventListener("click", (e) => { if (!confirm("Записати дані у базу? Рекомендуємо спершу зробити перевірку.")) e.preventDefault(); });

  // product form: show fields for the chosen kind + catalogue lookup
  const pf = $("[data-product-form]");
  if (pf) {
    const kind = $("#id_kind", pf);
    const category = $("#id_category", pf);
    const sync = () => {
      $$("[data-kind-section]", pf).forEach((s) => { s.hidden = !s.dataset.kindSection.split(" ").includes(kind.value); });
      if (category) category.dataset.preferKind = kind.value;  // categories of this type are listed first
    };
    kind.addEventListener("change", sync);
    sync();
    const elInput = $("#id_element_id", pf), colorInput = $("#id_color", pf);
    const lookup = async (type, typed) => {
      const input = type === "set" ? $("#id_set_number", pf) : type === "part" ? $("#id_design_id", pf) : $("#id_fig_number", pf);
      const out = $(`[data-lookup-out="${type}"]`, pf);
      const q = (typed || input.value).trim();
      if (!q) return;
      const k = type === "set" && kind.value === "accessory" ? "accessory" : type;
      let extra = type === "part" && colorInput && colorInput.value ? `&color=${encodeURIComponent(colorInput.value)}` : "";
      if (typed) extra += "&by=element";
      const r = await fetch(`${pf.dataset.lookup}?kind=${k}&q=${encodeURIComponent(q)}${extra}`);
      const d = await r.json();
      out.className = "lookup-result " + (d.found ? "is-ok" : "is-bad");
      if (!d.found) { out.textContent = d.message || "Не знайдено в каталозі"; return; }
      const title = $("#id_title", pf);
      if (type === "set") {
        // pieces and minifigure counts are shown (and filled in) only for sets
        const isSet = kind.value === "set";
        const bits = [d.name];
        if (d.year) bits.push(d.year);
        if (isSet) bits.push(`${d.pieces || "?"} дет.`, `мініфігурок: ${d.minifigs ?? "?"}`);
        if (d.theme) bits.push(d.theme);
        out.textContent = "✓ " + bits.join(" · ") +
          (d.listings && d.listings.length ? ` · вже є лоти: ${d.listings.map((l) => l.sku).join(", ")}` : "");
        if (title && !title.value) title.placeholder = d.name;
        const set = (id, v) => { const el = $(id, pf); if (el && !el.value && v != null) el.value = v; };
        if (isSet) { set("#id_year", d.year); set("#id_pieces", d.pieces); set("#id_minifigs_count", d.minifigs); set("#id_age_min", d.age); }
        const theme = $("#id_theme", pf);
        if (theme && !theme.value && d.theme_id) { theme.value = d.theme_id; theme.dispatchEvent(new Event("change")); }
      } else if (type === "part") {
        out.textContent = `✓ ${d.design_id} — ${d.name}${d.name_uk ? " (" + d.name_uk + ")" : ""}${d.note ? " · " + d.note : ""}` +
          (d.listings && d.listings.length ? ` · вже є: ${d.listings.length} лот(ів)` : "");
        if (title && !title.value) title.placeholder = d.name_uk || d.name;
        if (d.design_id && d.design_id !== input.value.trim()) input.value = d.design_id;
        // the Element ID of this part in the chosen colour comes from the catalogue
        if (elInput && d.element_id && (!elInput.value || elInput.dataset.auto)) {
          elInput.value = d.element_id; elInput.dataset.auto = "1"; elInput.dispatchEvent(new Event("change"));
        }
        if (d.color_id && colorInput && String(colorInput.value) !== String(d.color_id)) {
          colorInput.value = d.color_id; colorInput.dispatchEvent(new Event("change"));
        }
        const cat = $("#id_category", pf);
        if (cat && !cat.value && d.category_id) { cat.value = d.category_id; cat.dispatchEvent(new Event("change")); }
        // printed minifigure parts (torsos, heads ...) are separate items by default when adding a new one
        const own = $("#id_standalone", pf);
        if (own && d.separate && location.pathname.endsWith("/novyi/")) own.checked = true;
      } else {
        out.textContent = `✓ ${d.name}${d.year ? " · " + d.year : ""}${d.note ? " · " + d.note : ""}`;
        if (title && !title.value && kind.value === "minifig") title.placeholder = d.name;
        const theme = $("#id_theme", pf);
        if (theme && !theme.value && d.theme_id) { theme.value = d.theme_id; theme.dispatchEvent(new Event("change")); }
      }
    };
    $$("[data-lookup-btn]", pf).forEach((b) => b.addEventListener("click", () => lookup(b.dataset.lookupBtn)));
    ["#id_set_number", "#id_design_id", "#id_fig_number"].forEach((sel, i) => {
      const el = $(sel, pf);
      el && el.addEventListener("change", () => lookup(["set", "part", "minifig"][i]));
    });
    if (elInput) {
      // an Element ID typed by hand fills the Design ID, colour, name and section
      elInput.addEventListener("input", () => { delete elInput.dataset.auto; });
      elInput.addEventListener("change", () => {
        if (!elInput.dataset.auto && elInput.value.trim()) lookup("part", elInput.value);
      });
    }
    if (colorInput) {
      // another colour: its own Element ID, unless one was typed by hand
      colorInput.addEventListener("change", () => {
        const design = $("#id_design_id", pf);
        if (!design || !design.value.trim() || (elInput && elInput.value && !elInput.dataset.auto)) return;
        if (elInput && elInput.dataset.auto) { elInput.value = ""; }
        lookup("part");
      });
    }
  }

  // BrickLink check page: every row is judged by whether BrickLink has a picture for it
  const blTable = $("[data-bl-check]");
  if (blTable) {
    const rows = $$("[data-bl-row]", blTable);
    const onlyBad = $("[data-bl-only-bad]");
    const summary = $("[data-bl-summary]");
    const BAD = "BrickLink не має такої позиції — перевірте номер і колір";
    const refresh = () => {
      const bad = rows.filter((r) => r.classList.contains("is-bad")).length;
      const done = rows.filter((r) => r.dataset.state).length;
      summary.textContent = done < rows.length ? `Перевірено ${done} з ${rows.length}` : `Проблемних: ${bad} з ${rows.length}`;
      rows.forEach((r) => { r.hidden = Boolean(onlyBad && onlyBad.checked && !r.classList.contains("is-bad")); });
    };
    const mark = (row, ok, text) => {
      row.dataset.state = ok ? "ok" : "bad";
      row.classList.toggle("is-bad", !ok);
      const cell = $("[data-bl-status]", row);
      cell.textContent = text;
      cell.className = ok ? "bl-ok" : "bl-bad";
      refresh();
    };
    const watch = (row, img) => {
      img.addEventListener("load", () => mark(row, true, "Є на BrickLink"));
      img.addEventListener("error", () => mark(row, false, BAD));
      if (img.complete && img.getAttribute("src")) {
        if (img.naturalWidth) mark(row, true, "Є на BrickLink"); else mark(row, false, BAD);
      }
    };
    rows.forEach((row) => {
      const img = $("[data-bl-img]", row);
      if (img) watch(row, img);
      else if (row.dataset.kind === "minifig") mark(row, false, "Не вказано номер BrickLink");
      else if (row.dataset.kind === "part" && !row.dataset.color) mark(row, false, "Колір без номера BrickLink");
      else mark(row, false, "Немає номера BrickLink");
      const el = $("[data-el-img]", row);
      if (el) el.addEventListener("error", () => { el.hidden = true; });
      const number = $("input[name=bricklink_no]", row);
      if (number && row.dataset.color) {
        number.addEventListener("change", () => {
          let pic = $("[data-bl-img]", row);
          if (!pic) {
            pic = document.createElement("img");
            pic.className = "bl-img";
            pic.width = 64;
            pic.height = 64;
            pic.setAttribute("data-bl-img", "");
            const empty = $("[data-bl-img-empty]", row);
            if (empty) empty.replaceWith(pic);
            watch(row, pic);
          }
          delete row.dataset.state;
          pic.src = "https://img.bricklink.com/ItemImage/PN/" + row.dataset.color + "/" + encodeURIComponent(number.value.trim()) + ".png";
        });
      }
      const save = $("[data-bl-save]", row);
      if (save) save.addEventListener("click", async () => {
        const body = new FormData();
        body.append("csrfmiddlewaretoken", csrf());
        $$("input", row).forEach((i) => body.append(i.name, i.value));
        save.disabled = true;
        try {
          const r = await fetch(row.dataset.save, { method: "POST", body, headers: { "X-Requested-With": "fetch" } });
          const d = await r.json();
          if (!d.ok) { if (window.bhToast) window.bhToast(d.error || "Не вдалося зберегти", "error"); return; }
          if (window.bhToast) window.bhToast("Збережено", "success");
          const pic = $("[data-bl-img]", row);
          if (pic && d.image && pic.src !== d.image) { delete row.dataset.state; pic.src = d.image; }
          const link = $("[data-bl-link]", row);
          if (link && d.url) link.href = d.url;
        } finally { save.disabled = false; }
      });
    });
    if (onlyBad) onlyBad.addEventListener("change", refresh);
    refresh();
  }

  // the picture the shop will show for a part without its own photo: BrickLink (number + colour), then the
  // LEGO photo of the element, so a picture appears as soon as an Element ID is typed
  const blBox = $("[data-bl-preview]");
  if (blBox) {
    const form = blBox.closest("form");
    const img = $("[data-bl-img]", blBox), note = $("[data-bl-note]", blBox), link = $("[data-bl-link]", blBox);
    let queue = [];
    const show = () => {
      const next = queue.shift();
      if (!next) {
        blBox.classList.add("is-missing");
        note.textContent = "Ні BrickLink, ні LEGO не мають картинки для цього номера, кольору та Element ID. Перевірте їх.";
        return;
      }
      note.textContent = next.note;
      img.src = next.src;
    };
    img.addEventListener("error", show);
    const update = () => {
      const kindSel = $("#id_kind", form);
      const number = ($("#id_bricklink_no", form).value || $("#id_design_id", form).value || "").trim();
      const opt = $("#id_color", form).selectedOptions[0];
      const color = opt ? opt.dataset.bl : "";
      const element = ($("#id_element_id", form).value || "").trim();
      queue = [];
      if (number && color) {
        queue.push({ src: "https://img.bricklink.com/ItemImage/PN/" + color + "/" + encodeURIComponent(number) + ".png",
                     note: "Картинка BrickLink — так деталь виглядатиме на сайті, якщо не додати своє фото." });
        link.href = "https://www.bricklink.com/v2/catalog/catalogitem.page?P=" + encodeURIComponent(number) + "&idColor=" + color;
        link.hidden = false;
      } else {
        link.hidden = true;
      }
      if (element) {
        queue.push({ src: "https://www.lego.com/cdn/product-assets/element.img.lod5photo.192_192/" + encodeURIComponent(element) + ".jpg",
                     note: "Фото елемента " + element + " з сайту LEGO — так деталь виглядатиме на сайті." });
      }
      if (kindSel.value !== "part" || !queue.length) { blBox.hidden = true; return; }
      blBox.hidden = false;
      blBox.classList.remove("is-missing");
      show();
    };
    ["#id_design_id", "#id_bricklink_no", "#id_color", "#id_kind", "#id_element_id"].forEach((sel) => {
      const el = $(sel, form);
      if (el) el.addEventListener("change", update);
    });
    update();
  }

  // photos that cannot be opened are flagged in the product form
  $$("img[data-photo-check]").forEach((img) => {
    const flag = () => {
      img.classList.add("is-broken");
      const note = img.nextElementSibling;
      if (note && note.classList.contains("img-broken")) note.hidden = false;
    };
    if (img.complete && img.naturalWidth === 0 && img.getAttribute("src")) flag();
    img.addEventListener("error", flag);
  });

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
