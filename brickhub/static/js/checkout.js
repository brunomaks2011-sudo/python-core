/* Checkout: delivery fields + Nova Poshta autocomplete (only when the API key is configured). */
(() => {
  "use strict";
  const form = document.querySelector("[data-checkout]");
  if (!form) return;
  const live = form.dataset.npLive === "1";
  const $ = (s, r = form) => r.querySelector(s);

  function syncDelivery() {
    const method = (form.querySelector("input[name=delivery_method]:checked") || {}).value || "";
    form.querySelectorAll("[data-show-for]").forEach((el) => {
      el.hidden = !el.dataset.showFor.split(" ").includes(method);
    });
    const wh = $("#id_np_warehouse");
    if (wh) wh.placeholder = method === "np_postomat" ? "Номер або адреса поштомата" : "Номер або адреса відділення";
  }
  form.addEventListener("change", (e) => {
    if (e.target.name === "delivery_method") {
      syncDelivery();
      const wh = $("#id_np_warehouse"), ref = $("#id_np_warehouse_ref");
      if (wh && ref && ref.value) { wh.value = ""; ref.value = ""; }
    }
    if (e.target.id === "id_create_account") syncAccount();
  });
  function syncAccount() {
    const box = form.querySelector("[data-show-if=id_create_account]");
    const cb = $("#id_create_account");
    if (box && cb) box.hidden = !cb.checked;
  }
  syncDelivery();
  syncAccount();

  if (!live) return;

  function autocomplete(wrapper, fetcher, onPick) {
    const input = wrapper.querySelector("input:not([type=hidden])");
    const list = wrapper.querySelector(".ac-list");
    let timer, ctl, items = [], active = -1;
    const close = () => { list.hidden = true; active = -1; };
    const render = () => {
      list.innerHTML = "";
      if (!items.length) { close(); return; }
      items.forEach((it, i) => {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = it.label;
        if (it.hint) { const s = document.createElement("small"); s.textContent = it.hint; b.appendChild(s); }
        b.addEventListener("click", () => { onPick(it); close(); });
        if (i === active) b.classList.add("is-active");
        list.appendChild(b);
      });
      list.hidden = false;
    };
    input.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        ctl && ctl.abort();
        ctl = new AbortController();
        try { items = await fetcher(input.value.trim(), ctl.signal); } catch (_) { items = []; }
        active = -1;
        render();
      }, 220);
    });
    input.addEventListener("keydown", (e) => {
      if (list.hidden || !items.length) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        active = (active + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
        render();
      } else if (e.key === "Enter" && active >= 0) { e.preventDefault(); onPick(items[active]); close(); }
      else if (e.key === "Escape") close();
    });
    document.addEventListener("click", (e) => { if (!wrapper.contains(e.target)) close(); });
  }

  const cityWrap = form.querySelector("[data-ac=city]");
  const whWrap = form.querySelector("[data-ac=warehouse]");
  const cityRef = $("#id_city_ref"), whRef = $("#id_np_warehouse_ref");

  autocomplete(cityWrap, async (q, signal) => {
    if (q.length < 2) return [];
    const r = await fetch(`/api/np/mista/?q=${encodeURIComponent(q)}`, { signal });
    const data = await r.json();
    return (data.items || []).map((c) => ({ ...c, hint: c.warehouses ? `${c.warehouses} відділень` : "" }));
  }, (it) => {
    $("#id_city").value = it.name;
    cityRef.value = it.ref;
    $("#id_np_warehouse").value = "";
    whRef.value = "";
    $("#id_np_warehouse").focus();
  });
  $("#id_city").addEventListener("input", () => { cityRef.value = ""; });

  autocomplete(whWrap, async (q, signal) => {
    if (!cityRef.value) return [];
    const method = (form.querySelector("input[name=delivery_method]:checked") || {}).value;
    const type = method === "np_postomat" ? "postomat" : "branch";
    const r = await fetch(`/api/np/viddilennia/?city_ref=${encodeURIComponent(cityRef.value)}&type=${type}&q=${encodeURIComponent(q)}`, { signal });
    const data = await r.json();
    return data.items || [];
  }, (it) => {
    $("#id_np_warehouse").value = it.label;
    whRef.value = it.ref;
  });
  $("#id_np_warehouse").addEventListener("focus", (e) => { if (cityRef.value && !e.target.value) e.target.dispatchEvent(new Event("input")); });
})();
