// Админка: расписание, записи, закрытое время, услуги, статистика.
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const WEEKDAYS = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];
const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
const DAY_START = 9; // часы, видимые в дневном расписании
const DAY_END = 22;
const HOUR_PX = 64;

const store = {
  get auth() { try { return sessionStorage.getItem("auth"); } catch { return null; } },
  set auth(v) { try { v ? sessionStorage.setItem("auth", v) : sessionStorage.removeItem("auth"); } catch {} },
};
const ui = { view: "day", date: isoDate(new Date()), masters: [], services: [] };

function isoDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function addDays(iso, n) {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + n);
  return isoDate(d);
}
function mondayOf(iso) {
  const d = new Date(`${iso}T00:00:00`);
  return addDays(iso, -((d.getDay() + 6) % 7));
}
function human(iso) {
  const d = new Date(iso.length > 10 ? iso : `${iso}T00:00:00`);
  return `${WEEKDAYS[d.getDay()]}, ${d.getDate()} ${MONTHS[d.getMonth()]}`;
}
const hhmm = (iso) => iso.slice(11, 16);
const minutes = (iso) => +iso.slice(11, 13) * 60 + +iso.slice(14, 16);

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "style") node.style.cssText = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  node.append(...children.flat().filter((c) => c !== null && c !== undefined));
  return node;
}

async function api(path, options = {}) {
  const r = await fetch(`/api/admin${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", Authorization: `Basic ${store.auth}`, ...options.headers },
  });
  if (r.status === 401) {
    logout();
    throw new Error("Требуется вход");
  }
  if (r.status === 204) return null;
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(Array.isArray(data.detail) ? "Проверьте поля формы" : data.detail || "Ошибка");
  return data;
}

// --- вход ------------------------------------------------------------------

async function login(event) {
  event.preventDefault();
  const f = event.target;
  store.auth = btoa(unescape(encodeURIComponent(`${f.user.value}:${f.password.value}`)));
  try {
    await api("/check");
    start();
  } catch {
    $("#login-error").classList.remove("hidden");
  }
}

function logout() {
  store.auth = null;
  $("#app").classList.add("hidden");
  $("#login").classList.remove("hidden");
}

async function start() {
  $("#login").classList.add("hidden");
  $("#app").classList.remove("hidden");
  ui.masters = await api("/masters");
  openTab(location.hash.slice(1) || "schedule");
}

const loaders = { schedule: loadSchedule, bookings: loadBookings, timeoff: loadTimeOff, services: loadServices, stats: loadStats };

function openTab(name) {
  if (!loaders[name]) name = "schedule";
  history.replaceState(null, "", `#${name}`);
  $$("[data-tab]").forEach((b) => b.setAttribute("aria-current", b.dataset.tab === name ? "page" : "false"));
  $$("[data-panel]").forEach((p) => p.classList.toggle("hidden", p.dataset.panel !== name));
  loaders[name]();
}

// --- расписание ------------------------------------------------------------

async function loadSchedule() {
  $$("[data-view]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === ui.view)));
  $("#sched-date").value = ui.date;
  const from = ui.view === "day" ? ui.date : mondayOf(ui.date);
  const data = await api(`/schedule?day=${from}&days=${ui.view === "day" ? 1 : 7}`);
  $("#schedule").replaceChildren(ui.view === "day" ? dayGrid(data, from) : weekGrid(data, from));
}

function workFor(master, iso) {
  const wd = (new Date(`${iso}T00:00:00`).getDay() + 6) % 7; // 0 — понедельник, как в API
  return master.hours.filter((h) => h.weekday === wd);
}

function dayGrid(data, iso) {
  const height = (DAY_END - DAY_START) * HOUR_PX;
  const top = (min) => ((min - DAY_START * 60) / 60) * HOUR_PX;
  const hours = el("div", { class: "relative w-14 shrink-0", style: `height:${height}px` });
  for (let h = DAY_START; h <= DAY_END; h++) {
    hours.append(el("span", { class: "absolute -translate-y-1/2 text-xs text-mute", style: `top:${top(h * 60)}px` }, `${h}:00`));
  }
  const columns = data.masters.map((m) => {
    const col = el("div", { class: "relative overflow-hidden rounded-xl border border-line bg-smoke", style: `height:${height}px` });
    for (let h = DAY_START; h < DAY_END; h++) {
      col.append(el("div", { class: "absolute inset-x-0 border-t border-line/50", style: `top:${top(h * 60)}px` }));
    }
    for (const w of workFor(m, iso)) {
      const [a, b] = [w.start, w.end].map((t) => +t.slice(0, 2) * 60 + +t.slice(3, 5));
      col.append(el("div", { class: "absolute inset-x-0 bg-ink", style: `top:${top(a)}px;height:${top(b) - top(a)}px` }));
    }
    for (const t of data.time_off.filter((t) => t.master_id === m.id)) {
      const a = t.start_at.slice(0, 10) < iso ? DAY_START * 60 : minutes(t.start_at);
      const b = t.end_at.slice(0, 10) > iso ? DAY_END * 60 : minutes(t.end_at);
      col.append(el("div", {
        class: "absolute inset-x-1 rounded-lg border border-dashed border-mute/40 bg-[repeating-linear-gradient(-45deg,transparent_0_6px,rgba(168,159,146,.12)_6px_12px)] p-2 text-xs text-mute",
        style: `top:${top(a)}px;height:${top(b) - top(a)}px`,
      }, t.reason));
    }
    for (const b of data.bookings.filter((b) => b.master_id === m.id)) {
      const a = minutes(b.start_at), z = minutes(b.end_at);
      col.append(el("div", {
        class: "absolute inset-x-1 overflow-hidden rounded-lg border-l-4 border-brass bg-brass/15 p-2 text-xs",
        style: `top:${top(a) + 1}px;height:${top(z) - top(a) - 2}px`,
        title: `${b.client_name ?? "—"} ${b.client_phone ?? ""}`,
      },
        el("p", { class: "font-semibold text-cream" }, `${hhmm(b.start_at)} ${b.service}`),
        el("p", { class: "text-mute" }, `${b.client_name ?? "данные удалены"} · ${b.client_phone ?? ""}`),
      ));
    }
    return el("div", { class: "min-w-44 flex-1" }, el("p", { class: "mb-2 text-center text-sm font-semibold" }, m.name), col);
  });
  // Пустой заголовок выравнивает шкалу часов с колонками мастеров.
  const scale = el("div", { class: "shrink-0" }, el("p", { class: "invisible mb-2 text-sm" }, "·"), hours);
  return el("div", { class: "flex gap-3 pt-2" }, scale, el("div", { class: "flex flex-1 gap-3" }, columns));
}

function weekGrid(data, monday) {
  const days = [...Array(7)].map((_, i) => addDays(monday, i));
  const head = el("tr", {}, el("th", { class: "p-3" }), days.map((d) => el("th", { class: `p-3 text-left font-semibold ${d === isoDate(new Date()) ? "text-brass" : ""}` }, human(d))));
  const rows = data.masters.map((m) => el("tr", { class: "align-top" },
    el("th", { class: "whitespace-nowrap p-3 text-left font-semibold" }, m.name),
    days.map((d) => {
      const cell = el("td", { class: "min-w-36 border-l border-line p-2" });
      if (!workFor(m, d).length) cell.append(el("p", { class: "text-xs text-mute/60" }, "выходной"));
      for (const t of data.time_off.filter((t) => t.master_id === m.id && t.start_at.slice(0, 10) <= d && t.end_at.slice(0, 10) >= d && t.end_at !== `${d}T00:00:00`)) {
        cell.append(el("p", { class: "mb-1 rounded bg-smoke px-2 py-1 text-xs text-mute" }, `⛔ ${t.reason}`));
      }
      for (const b of data.bookings.filter((b) => b.master_id === m.id && b.start_at.startsWith(d))) {
        cell.append(el("p", { class: "mb-1 rounded border-l-2 border-brass bg-brass/10 px-2 py-1 text-xs", title: b.client_phone ?? "" },
          el("b", {}, hhmm(b.start_at)), ` ${b.service} · ${b.client_name ?? "—"}`));
      }
      return cell;
    }),
  ));
  return el("table", { class: "w-full rounded-2xl border border-line text-sm" }, el("thead", { class: "bg-coal" }, head), el("tbody", { class: "divide-y divide-line" }, rows));
}

function shiftDate(dir) {
  ui.date = addDays(ui.date, dir * (ui.view === "day" ? 1 : 7));
  loadSchedule();
}

// --- записи ----------------------------------------------------------------

async function loadBookings() {
  if (!$("#b-from").value) {
    $("#b-from").value = isoDate(new Date());
    $("#b-to").value = addDays(isoDate(new Date()), 14);
  }
  const q = new URLSearchParams({ date_from: $("#b-from").value, date_to: $("#b-to").value });
  if ($("#b-status").value) q.set("status", $("#b-status").value);
  const items = await api(`/bookings?${q}`);
  const body = $("#bookings-body");
  body.replaceChildren();
  if (!items.length) body.append(el("tr", {}, el("td", { class: "p-6 text-mute", colspan: 7 }, "Записей нет")));
  for (const b of items) {
    const cancelled = b.status === "cancelled";
    body.append(el("tr", { class: cancelled ? "text-mute line-through" : "" },
      el("td", { class: "whitespace-nowrap p-3" }, `${human(b.start_at)}, ${hhmm(b.start_at)}`),
      el("td", { class: "p-3" }, b.master),
      el("td", { class: "p-3" }, b.service),
      el("td", { class: "p-3" }, b.client_name ?? "данные удалены", el("br"), el("span", { class: "text-xs text-mute" }, `${b.client_phone ?? ""}${b.telegram ? " · Telegram" : ""}`)),
      el("td", { class: "p-3" }, b.source === "site" ? "сайт" : "бот"),
      el("td", { class: "p-3 text-right" }, `${b.price} ₽`),
      el("td", { class: "p-3 text-right no-underline" }, cancelled ? "отменена" : el("button", {
        class: "text-xs text-blood hover:underline",
        onclick: async () => {
          if (!confirm(`Отменить запись ${b.client_name ?? ""} на ${human(b.start_at)} ${hhmm(b.start_at)}?`)) return;
          await api(`/bookings/${b.id}/cancel`, { method: "POST" });
          loadBookings();
        },
      }, "Отменить")),
    ));
  }
}

// --- закрытое время --------------------------------------------------------

async function loadTimeOff() {
  const form = $("#timeoff-form");
  form.master_id.replaceChildren(...ui.masters.map((m) => el("option", { value: m.id }, m.name)));
  if (!form.day.value) form.day.value = isoDate(new Date());
  const items = await api("/time-off");
  const list = $("#timeoff-list");
  list.replaceChildren();
  if (!items.length) list.append(el("p", { class: "text-mute" }, "Закрытого времени нет"));
  for (const t of items) {
    const master = ui.masters.find((m) => m.id === t.master_id)?.name ?? "";
    const whole = hhmm(t.start_at) === "00:00" && hhmm(t.end_at) === "00:00";
    list.append(el("div", { class: "flex items-center gap-4 rounded-2xl border border-line bg-coal px-5 py-3" },
      el("div", { class: "flex-1" },
        el("p", { class: "font-semibold" }, `${master} · ${t.reason}`),
        el("p", { class: "text-sm text-mute" }, `${human(t.start_at)}${whole ? ", весь день" : `, ${hhmm(t.start_at)}–${hhmm(t.end_at)}`}`)),
      el("button", {
        class: "text-sm text-mute hover:text-blood",
        onclick: async () => { await api(`/time-off/${t.id}`, { method: "DELETE" }); loadTimeOff(); },
      }, "Открыть"),
    ));
  }
}

async function saveTimeOff(event) {
  event.preventDefault();
  const f = event.target;
  const err = $("#timeoff-error");
  err.classList.add("hidden");
  try {
    await api("/time-off", {
      method: "POST",
      body: JSON.stringify({
        master_id: +f.master_id.value,
        day: f.day.value,
        start: f.whole.checked ? null : f.start.value,
        end: f.whole.checked ? null : f.end.value,
        reason: f.reason.value || (f.whole.checked ? "Выходной" : "Обед"),
      }),
    });
    f.reason.value = "";
    loadTimeOff();
  } catch (e) {
    err.textContent = e.message;
    err.classList.remove("hidden");
  }
}

// --- услуги ----------------------------------------------------------------

async function loadServices() {
  ui.services = await api("/services");
  const body = $("#services-body");
  body.replaceChildren(...ui.services.map((s) => el("div", { class: `flex flex-wrap items-center gap-4 rounded-2xl border border-line bg-coal px-5 py-4 ${s.is_active ? "" : "opacity-50"}` },
    el("div", { class: "min-w-48 flex-1" },
      el("p", { class: "font-semibold" }, s.name, s.is_active ? null : el("span", { class: "ml-2 text-xs text-mute" }, "скрыта")),
      el("p", { class: "text-sm text-mute" }, s.master_ids.map((id) => ui.masters.find((m) => m.id === id)?.name).filter(Boolean).join(", ") || "нет мастеров")),
    el("p", { class: "text-sm text-mute" }, `${s.duration_min} мин`),
    el("p", { class: "w-24 text-right font-display text-brass" }, `${s.price} ₽`),
    el("button", { class: "btn-ghost !px-4 !py-1.5", onclick: () => editService(s) }, "Изменить"),
  )));
}

function editService(s = null) {
  const f = $("#service-form");
  f.dataset.id = s?.id ?? "";
  $("#service-title").textContent = s ? "Изменить услугу" : "Новая услуга";
  f.name.value = s?.name ?? "";
  f.description.value = s?.description ?? "";
  f.price.value = s?.price ?? 1500;
  f.duration_min.value = s?.duration_min ?? 60;
  f.is_active.checked = s?.is_active ?? true;
  $("#service-masters").replaceChildren(...ui.masters.map((m) => el("label", { class: "flex items-center gap-2" },
    el("input", { type: "checkbox", value: m.id, class: "accent-[#c9a266]", ...(!s || s.master_ids.includes(m.id) ? { checked: "" } : {}) }), m.name)));
  $("#service-error").classList.add("hidden");
  $("#service-dialog").showModal();
}

async function saveService(event) {
  event.preventDefault();
  const f = event.target;
  const payload = {
    name: f.name.value.trim(),
    description: f.description.value.trim(),
    price: +f.price.value,
    duration_min: +f.duration_min.value,
    is_active: f.is_active.checked,
    master_ids: $$("#service-masters input:checked").map((i) => +i.value),
  };
  try {
    await api(f.dataset.id ? `/services/${f.dataset.id}` : "/services", {
      method: f.dataset.id ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    $("#service-dialog").close();
    loadServices();
  } catch (e) {
    $("#service-error").textContent = e.message;
    $("#service-error").classList.remove("hidden");
  }
}

// --- статистика ------------------------------------------------------------

async function loadStats() {
  const s = await api("/stats");
  const kpi = (label, value) => el("div", { class: "rounded-3xl border border-line bg-coal p-6" },
    el("p", { class: "font-display text-3xl font-bold text-brass" }, value), el("p", { class: "mt-1 text-sm text-mute" }, label));
  $("#stats-kpi").replaceChildren(
    kpi("Записей за 7 дней", s.week_total),
    kpi("Выручка за 7 дней", `${s.week_revenue.toLocaleString("ru-RU")} ₽`),
    kpi("Отмен за 7 дней", s.week_cancelled),
  );
  const max = Math.max(1, ...s.week.map((d) => d.count));
  $("#stats-week").replaceChildren(...s.week.map((d) => el("div", { class: "flex h-full flex-1 flex-col items-center justify-end gap-2" },
    el("span", { class: "text-xs text-mute" }, d.count),
    el("div", { class: "w-full rounded-t-lg bg-brass", style: `height:${(d.count / max) * 100}%;min-height:2px` }),
    el("span", { class: "text-xs text-mute" }, human(d.day).split(",")[0]),
  )));
  const top = Math.max(1, ...s.services_30d.map((x) => x.count));
  $("#stats-services").replaceChildren(...(s.services_30d.length ? s.services_30d.map((x) => el("div", {},
    el("div", { class: "mb-1 flex justify-between text-sm" }, el("span", {}, x.name), el("span", { class: "text-mute" }, x.count)),
    el("div", { class: "h-2 rounded-full bg-smoke" }, el("div", { class: "h-2 rounded-full bg-brass", style: `width:${(x.count / top) * 100}%` })),
  )) : [el("p", { class: "text-mute" }, "Пока нет записей")]));
}

// --- события ---------------------------------------------------------------

$("#login-form").addEventListener("submit", login);
$("#logout").addEventListener("click", logout);
$$("[data-tab]").forEach((b) => b.addEventListener("click", () => openTab(b.dataset.tab)));
$$("[data-view]").forEach((b) => b.addEventListener("click", () => { ui.view = b.dataset.view; loadSchedule(); }));
$("#prev").addEventListener("click", () => shiftDate(-1));
$("#next").addEventListener("click", () => shiftDate(1));
$("#today").addEventListener("click", () => { ui.date = isoDate(new Date()); loadSchedule(); });
$("#sched-date").addEventListener("change", (e) => { ui.date = e.target.value; loadSchedule(); });
["#b-from", "#b-to", "#b-status"].forEach((s) => $(s).addEventListener("change", loadBookings));
$("#timeoff-form").addEventListener("submit", saveTimeOff);
$("#timeoff-form").whole.addEventListener("change", (e) => $("#timeoff-times").classList.toggle("hidden", e.target.checked));
$("#add-service").addEventListener("click", () => editService());
$("#service-form").addEventListener("submit", saveService);

if (store.auth) api("/check").then(start).catch(logout);
