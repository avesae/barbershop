// Лендинг: прайс, мастера и окно записи. Данные приходят из /api.
const $ = (s, root = document) => root.querySelector(s);
const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
const WEEKDAYS = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];

const state = { services: [], masters: [], service: null, master: null, date: null, time: null };

async function api(path, options) {
  const r = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const detail = Array.isArray(data.detail) ? "Проверьте заполнение полей" : data.detail;
    throw new Error(detail || "Что-то пошло не так, попробуйте ещё раз");
  }
  return data;
}

function el(tag, attrs = {}, text = "") {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  node.textContent = text;
  return node;
}

function initials(name) {
  return name.slice(0, 1).toUpperCase();
}

function renderCatalog() {
  const list = $("#services-list");
  list.replaceChildren();
  for (const s of state.services) {
    const row = el("div", { class: "group flex flex-wrap items-center gap-4 p-6 transition hover:bg-smoke/60" });
    const text = el("div", { class: "min-w-0 flex-1" });
    text.append(el("p", { class: "font-semibold" }, s.name), el("p", { class: "text-sm text-mute" }, s.description));
    const meta = el("p", { class: "text-sm text-mute" }, `${s.duration_min} мин`);
    const price = el("p", { class: "w-24 text-right font-display text-lg text-brass" }, `${s.price} ₽`);
    const btn = el("button", { class: "btn-ghost !py-2 !px-4" }, "Выбрать");
    btn.addEventListener("click", () => openBooking({ service: s.id }));
    row.append(text, meta, price, btn);
    list.append(row);
  }

  const masters = $("#masters-list");
  masters.replaceChildren();
  for (const m of state.masters) {
    const card = el("article", { class: "flex flex-col rounded-3xl border border-line bg-ink p-6" });
    const avatar = el("div", { class: "mb-6 grid size-20 place-items-center rounded-full border border-brass/50 bg-brass/10 font-display text-3xl text-brass" }, initials(m.name));
    const btn = el("button", { class: "btn-ghost mt-6 self-start !py-2 !px-4" }, "Записаться");
    btn.addEventListener("click", () => openBooking({ master: m.id }));
    card.append(
      avatar,
      el("p", { class: "eyebrow" }, m.title),
      el("h3", { class: "mt-2 font-display text-2xl font-bold" }, m.name),
      el("p", { class: "mt-3 flex-1 text-sm text-mute" }, m.bio),
      btn,
    );
    masters.append(card);
  }
  $("[data-count-masters]").textContent = state.masters.length;
}

function chips(container, items, selected, onPick) {
  container.replaceChildren();
  if (!items.length) {
    container.append(el("span", { class: "text-sm text-mute/60" }, "Нет свободного времени"));
    return;
  }
  for (const item of items) {
    const chip = el("button", { type: "button", class: "chip", "aria-pressed": String(item.value === selected) }, item.label);
    chip.addEventListener("click", () => onPick(item.value));
    container.append(chip);
  }
}

function hint(container, text) {
  container.replaceChildren(el("span", { class: "text-sm text-mute/60" }, text));
}

function formatDate(iso) {
  const d = new Date(`${iso}T00:00:00`);
  return `${WEEKDAYS[d.getDay()]}, ${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

function renderServices() {
  chips($("#pick-service"), state.services.map((s) => ({ value: s.id, label: `${s.name} · ${s.price} ₽` })), state.service, (id) => {
    state.service = id;
    if (state.master && !state.services.find((s) => s.id === id).master_ids.includes(state.master)) state.master = null;
    renderServices();
    renderMasters();
  });
}

function renderMasters() {
  const box = $("#pick-master");
  if (!state.service) return hint(box, "Сначала выберите услугу");
  const ids = state.services.find((s) => s.id === state.service).master_ids;
  const list = state.masters.filter((m) => ids.includes(m.id));
  chips(box, list.map((m) => ({ value: m.id, label: m.name })), state.master, (id) => {
    state.master = id;
    renderMasters();
    loadDates();
  });
  if (state.master) loadDates();
  else {
    hint($("#pick-date"), "Выберите мастера");
    hint($("#pick-time"), "Выберите дату");
  }
}

async function loadDates() {
  state.date = null;
  state.time = null;
  updateSubmit();
  hint($("#pick-date"), "Загружаем…");
  hint($("#pick-time"), "Выберите дату");
  const dates = await api(`/dates?master_id=${state.master}&service_id=${state.service}`);
  const render = () => chips($("#pick-date"), dates.map((d) => ({ value: d, label: formatDate(d) })), state.date, (d) => {
    state.date = d;
    render();
    loadTimes();
  });
  render();
}

async function loadTimes() {
  state.time = null;
  updateSubmit();
  hint($("#pick-time"), "Загружаем…");
  const times = await api(`/slots?master_id=${state.master}&service_id=${state.service}&day=${state.date}`);
  const render = () => chips($("#pick-time"), times.map((t) => ({ value: t, label: t })), state.time, (t) => {
    state.time = t;
    render();
    updateSubmit();
  });
  render();
}

function updateSubmit() {
  $("#submit").disabled = !(state.service && state.master && state.date && state.time);
}

function openBooking(preset = {}) {
  Object.assign(state, { service: null, master: null, date: null, time: null }, preset);
  if (preset.master && !preset.service) {
    // Записались к мастеру — предлагаем первую его услугу.
    state.service = state.services.find((s) => s.master_ids.includes(preset.master))?.id ?? null;
  }
  $("#step-form").classList.remove("hidden");
  $("#step-done").classList.add("hidden");
  $("#form-error").classList.add("hidden");
  renderServices();
  renderMasters();
  updateSubmit();
  $("#booking").showModal();
}

async function submit(event) {
  event.preventDefault();
  const form = event.target;
  const error = $("#form-error");
  error.classList.add("hidden");
  $("#submit").disabled = true;
  try {
    const result = await api("/bookings", {
      method: "POST",
      body: JSON.stringify({
        service_id: state.service,
        master_id: state.master,
        start_at: `${state.date}T${state.time}:00`,
        name: form.name.value.trim(),
        phone: form.phone.value,
        consent: form.consent.checked,
      }),
    });
    $("#done-summary").textContent = result.summary;
    $("#done-bot").classList.toggle("hidden", !result.bot_link);
    if (result.bot_link) $("#done-bot-link").href = result.bot_link;
    $("#step-form").classList.add("hidden");
    $("#step-done").classList.remove("hidden");
    form.reset();
  } catch (e) {
    error.textContent = e.message;
    error.classList.remove("hidden");
    if (/занято/.test(e.message)) loadTimes();
    else updateSubmit();
  }
}

async function init() {
  $("[data-year]").textContent = new Date().getFullYear();
  document.querySelectorAll("[data-book]").forEach((b) => b.addEventListener("click", () => openBooking()));
  $("#contact-form").addEventListener("submit", submit);
  try {
    const [services, masters, info] = await Promise.all([api("/services"), api("/masters"), api("/info")]);
    Object.assign(state, { services, masters });
    renderCatalog();
    $('[data-info="address"]').textContent = info.address;
    const phone = $('[data-info="phone"]');
    phone.textContent = info.phone;
    phone.href = `tel:${info.phone.replace(/[^\d+]/g, "")}`;
    if (info.bot_username) {
      document.querySelectorAll("[data-bot-link]").forEach((a) => {
        a.href = `https://t.me/${info.bot_username}`;
        a.classList.remove("hidden");
      });
    }
  } catch {
    $("#services-list").replaceChildren(el("p", { class: "p-6 text-mute" }, "Не удалось загрузить прайс. Позвоните нам — запишем по телефону."));
  }
}

init();
