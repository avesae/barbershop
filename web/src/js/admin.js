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
const ui = { view: "day", date: isoDate(new Date()), masters: [], services: [], period: 7 };
const STATUS = { active: "", done: "пришёл", no_show: "не пришёл", cancelled: "отменена" };

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

async function upload(file) {
  const body = new FormData();
  body.append("file", file);
  const r = await fetch("/api/admin/uploads", { method: "POST", body, headers: { Authorization: `Basic ${store.auth}` } });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Не удалось загрузить фото");
  return data.url;
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

const loaders = {
  schedule: loadSchedule, bookings: loadBookings, clients: loadClients, timeoff: loadTimeOff,
  masters: loadMasters, services: loadServices, works: loadWorks, reviews: loadReviews, stats: loadStats,
};

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
      const tone = b.status === "no_show" ? "border-blood bg-blood/15" : b.status === "done" ? "border-mute bg-smoke" : "border-brass bg-brass/15";
      col.append(el("div", {
        class: `absolute inset-x-1 overflow-hidden rounded-lg border-l-4 ${tone} p-2 text-xs`,
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
      el("td", { class: "whitespace-nowrap p-3 text-right" }, bookingActions(b)),
    ));
  }
}

function bookingActions(b) {
  const started = new Date(b.start_at) <= new Date();
  const action = (label, cls, fn) => el("button", { class: `ml-3 text-xs hover:underline ${cls}`, onclick: async () => { await fn(); loadBookings(); } }, label);
  const setStatus = (status) => api(`/bookings/${b.id}/status`, { method: "POST", body: JSON.stringify({ status }) });
  if (b.status === "cancelled") return "отменена";
  if (!started) {
    return action("Отменить", "text-blood", async () => {
      if (confirm(`Отменить запись ${b.client_name ?? ""} на ${human(b.start_at)} ${hhmm(b.start_at)}?`)) {
        await api(`/bookings/${b.id}/cancel`, { method: "POST" });
      }
    });
  }
  if (b.status !== "active") {
    return el("span", {}, el("span", { class: b.status === "no_show" ? "text-blood" : "text-mute" }, STATUS[b.status]), action("сбросить", "text-mute", () => setStatus("active")));
  }
  return el("span", {}, action("Пришёл", "text-brass", () => setStatus("done")), action("Не пришёл", "text-blood", () => setStatus("no_show")));
}

// --- клиенты ---------------------------------------------------------------

const fmtDate = (iso) => (iso ? `${human(iso)}${iso.length > 10 ? `, ${hhmm(iso)}` : ""}` : "—");
const rub = (n) => `${n.toLocaleString("ru-RU")} ₽`;

async function loadClients() {
  const q = $("#c-search").value.trim();
  const items = await api(`/clients${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  const body = $("#clients-body");
  body.replaceChildren();
  if (!items.length) body.append(el("tr", {}, el("td", { class: "p-6 text-mute", colspan: 6 }, "Никого не нашли")));
  for (const c of items) {
    body.append(el("tr", { class: "cursor-pointer hover:bg-smoke/50", onclick: () => openClient(c.id) },
      el("td", { class: "p-3" }, el("p", { class: "font-semibold" }, c.name ?? "—"), el("p", { class: "text-xs text-mute" }, `${c.phone}${c.telegram ? " · Telegram" : ""}`)),
      el("td", { class: "p-3" }, c.visits),
      el("td", { class: "p-3" }, rub(c.spent)),
      el("td", { class: "p-3" }, fmtDate(c.last_visit)),
      el("td", { class: "p-3" }, fmtDate(c.next_visit)),
      el("td", { class: `p-3 ${c.no_shows ? "text-blood" : "text-mute"}` }, c.no_shows),
    ));
  }
}

async function openClient(id) {
  const c = await api(`/clients/${id}`);
  $("#client-title").textContent = c.name ?? "Клиент";
  const stat = (label, value) => el("div", { class: "rounded-2xl border border-line bg-coal p-4" },
    el("p", { class: "font-display text-xl text-brass" }, value), el("p", { class: "text-xs text-mute" }, label));
  const notes = el("textarea", { class: "field", rows: 3, placeholder: "Предпочтения клиента: «короче на висках», «без воска»…" });
  notes.value = c.notes;
  const saved = el("span", { class: "text-xs text-mute" });
  const consent = c.consent
    ? `Согласие v${c.consent.version} получено ${fmtDate(c.consent.accepted_at)} (${c.consent.source === "bot" ? "бот" : "сайт"})`
    : "Согласие не найдено";
  $("#client-body").replaceChildren(
    el("p", { class: "text-sm text-mute" }, `${c.phone ?? ""}${c.telegram ? " · Telegram подключён" : ""} · ${consent}`),
    el("div", { class: "grid grid-cols-2 gap-3 sm:grid-cols-4" },
      stat("визитов", c.visits), stat("потратил", rub(c.spent)),
      stat("ходит раз в", c.avg_interval_days ? `${c.avg_interval_days} дн.` : "—"), stat("неявок", c.no_shows)),
    el("div", {},
      el("p", { class: "mb-2 text-sm font-semibold" }, "Заметки мастера"), notes,
      el("div", { class: "mt-2 flex items-center gap-3" },
        el("button", { class: "btn-ghost !px-4 !py-1.5", onclick: async () => {
          await api(`/clients/${id}/notes`, { method: "PUT", body: JSON.stringify({ notes: notes.value }) });
          saved.textContent = "Сохранено";
        } }, "Сохранить"), saved)),
    el("div", {},
      el("p", { class: "mb-2 text-sm font-semibold" }, "История"),
      el("div", { class: "divide-y divide-line rounded-2xl border border-line" }, c.history.map((h) =>
        el("div", { class: "flex flex-wrap items-center gap-3 px-4 py-3 text-sm" },
          el("span", { class: "w-40" }, fmtDate(h.start_at)),
          el("span", { class: "flex-1" }, `${h.service} · ${h.master}`),
          h.rating ? el("span", { class: "text-brass" }, "★".repeat(h.rating)) : null,
          el("span", { class: h.status === "no_show" ? "text-blood" : "text-mute" }, STATUS[h.status] || (new Date(h.start_at) > new Date() ? "предстоит" : "")),
          el("span", { class: "w-20 text-right" }, rub(h.price)))))),
  );
  $("#client-dialog").showModal();
}

// --- мастера ---------------------------------------------------------------

const WEEK = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

async function loadMasters() {
  [ui.masters, ui.services] = await Promise.all([api("/masters"), api("/services")]);
  $("#masters-body").replaceChildren(...ui.masters.map((m) => {
    const days = WEEK.map((d, i) => {
      const h = m.hours.filter((x) => x.weekday === i);
      return el("div", { class: "flex justify-between text-xs" }, el("span", { class: "text-mute" }, d),
        el("span", { class: h.length ? "" : "text-mute/60" }, h.length ? h.map((x) => `${x.start}–${x.end}`).join(", ") : "выходной"));
    });
    const invite = el("button", { class: "text-xs text-brass hover:underline", onclick: async () => {
      const r = await api(`/masters/${m.id}/invite`, { method: "POST" });
      prompt("Отправьте мастеру ссылку — она откроет кабинет в боте:", r.link ?? `/start m_${r.code} (укажите BOT_USERNAME в .env, чтобы получить ссылку)`);
    } }, m.telegram ? "Telegram подключён · новая ссылка" : "Пригласить в бот");
    return el("div", { class: `rounded-3xl border border-line bg-coal p-5 ${m.is_active ? "" : "opacity-50"}` },
      el("div", { class: "mb-4 flex items-center gap-4" },
        m.photo ? el("img", { src: m.photo, class: "size-14 rounded-full object-cover", alt: "" })
          : el("div", { class: "grid size-14 place-items-center rounded-full bg-brass/10 font-display text-xl text-brass" }, m.name[0]),
        el("div", { class: "flex-1" }, el("p", { class: "font-semibold" }, m.name), el("p", { class: "text-xs text-mute" }, m.title)),
        el("button", { class: "btn-ghost !px-4 !py-1.5", onclick: () => editMaster(m) }, "Изменить")),
      el("div", { class: "space-y-1" }, days),
      el("div", { class: "mt-4" }, invite));
  }));
}

function hoursRow(h = { weekday: 0, start: "10:00", end: "20:00" }) {
  const row = el("div", { class: "flex items-center gap-2" },
    el("select", { class: "field !w-24 !py-1.5", name: "weekday" }, WEEK.map((d, i) => el("option", { value: i, ...(i === h.weekday ? { selected: "" } : {}) }, d))),
    el("input", { type: "time", class: "field !w-32 !py-1.5", name: "start", value: h.start, step: 900 }),
    el("span", { class: "text-mute" }, "–"),
    el("input", { type: "time", class: "field !w-32 !py-1.5", name: "end", value: h.end, step: 900 }),
    el("button", { type: "button", class: "text-mute hover:text-blood", onclick: () => row.remove(), "aria-label": "Удалить" }, "×"));
  return row;
}

function editMaster(m = null) {
  const f = $("#master-form");
  f.dataset.id = m?.id ?? "";
  f.dataset.photo = m?.photo ?? "";
  $("#master-title").textContent = m ? `Мастер: ${m.name}` : "Новый мастер";
  f.name.value = m?.name ?? "";
  f.title.value = m?.title ?? "Барбер";
  f.bio.value = m?.bio ?? "";
  f.is_active.checked = m?.is_active ?? true;
  showPhoto(f.dataset.photo);
  $("#master-services").replaceChildren(...ui.services.map((s) => el("label", { class: "flex items-center gap-2" },
    el("input", { type: "checkbox", value: s.id, class: "accent-[#c9a266]", ...(!m || m.service_ids.includes(s.id) ? { checked: "" } : {}) }), s.name)));
  const hours = m?.hours ?? [0, 1, 2, 3, 4].map((d) => ({ weekday: d, start: "10:00", end: "20:00" }));
  $("#master-hours").replaceChildren(...hours.map(hoursRow),
    el("button", { type: "button", class: "text-sm text-brass hover:underline", onclick: (e) => e.target.before(hoursRow()) }, "+ интервал"));
  $("#master-error").classList.add("hidden");
  $("#master-dialog").showModal();
}

function showPhoto(url) {
  const img = $("#master-photo-preview");
  img.classList.toggle("hidden", !url);
  $("#master-photo-remove").classList.toggle("hidden", !url);
  if (url) img.src = url;
}

async function saveMaster(event) {
  event.preventDefault();
  const f = event.target;
  const payload = {
    name: f.name.value.trim(), title: f.title.value.trim(), bio: f.bio.value.trim(),
    photo: f.dataset.photo || null, is_active: f.is_active.checked,
    service_ids: $$("#master-services input:checked").map((i) => +i.value),
    hours: $$("#master-hours > div").map((r) => ({ weekday: +r.querySelector("[name=weekday]").value, start: r.querySelector("[name=start]").value, end: r.querySelector("[name=end]").value })),
  };
  try {
    await api(f.dataset.id ? `/masters/${f.dataset.id}` : "/masters", { method: f.dataset.id ? "PUT" : "POST", body: JSON.stringify(payload) });
    $("#master-dialog").close();
    loadMasters();
  } catch (e) {
    $("#master-error").textContent = e.message;
    $("#master-error").classList.remove("hidden");
  }
}

// --- галерея ---------------------------------------------------------------

async function loadWorks() {
  if (!ui.masters.length) ui.masters = await api("/masters");
  const f = $("#work-form");
  f.master_id.replaceChildren(el("option", { value: "" }, "Мастер не указан"), ...ui.masters.map((m) => el("option", { value: m.id }, m.name)));
  const items = await api("/works");
  $("#works-body").replaceChildren(...(items.length ? items.map((w) => el("figure", { class: "group relative overflow-hidden rounded-2xl border border-line" },
    el("img", { src: w.photo, class: "aspect-square w-full object-cover", alt: w.caption }),
    el("figcaption", { class: "p-3 text-sm" }, w.caption || "—", el("span", { class: "block text-xs text-mute" }, ui.masters.find((m) => m.id === w.master_id)?.name ?? "")),
    el("button", { class: "absolute right-2 top-2 rounded-full bg-ink/80 px-3 py-1 text-xs opacity-0 transition group-hover:opacity-100 hover:text-blood",
      onclick: async () => { if (confirm("Удалить фото?")) { await api(`/works/${w.id}`, { method: "DELETE" }); loadWorks(); } } }, "Удалить"),
  )) : [el("p", { class: "col-span-full text-mute" }, "Загрузите первые фото работ — они появятся на лендинге")]));
}

async function saveWork(event) {
  event.preventDefault();
  const f = event.target;
  const err = $("#work-error");
  err.classList.add("hidden");
  try {
    const url = await upload(f.file.files[0]);
    await api("/works", { method: "POST", body: JSON.stringify({ photo: url, caption: f.caption.value.trim(), master_id: f.master_id.value ? +f.master_id.value : null }) });
    f.reset();
    loadWorks();
  } catch (e) {
    err.textContent = e.message;
    err.classList.remove("hidden");
  }
}

// --- отзывы ----------------------------------------------------------------

async function loadReviews() {
  const items = await api("/reviews");
  $("#reviews-body").replaceChildren(...(items.length ? items.map((r) => {
    const low = r.rating <= 3;
    const toggle = el("button", {
      class: r.published ? "btn-ghost !px-4 !py-1.5" : "btn-brass !px-4 !py-1.5",
      ...(r.text ? {} : { disabled: "", title: "Без текста публиковать нечего" }),
      onclick: async () => { await api(`/reviews/${r.id}`, { method: "PUT", body: JSON.stringify({ published: !r.published }) }); loadReviews(); },
    }, r.published ? "Снять с сайта" : "Опубликовать");
    return el("div", { class: `flex flex-wrap items-start gap-4 rounded-2xl border bg-coal px-5 py-4 ${low ? "border-blood/60" : "border-line"}` },
      el("div", { class: "min-w-60 flex-1" },
        el("p", { class: low ? "text-blood" : "text-brass" }, "★".repeat(r.rating) + "☆".repeat(5 - r.rating),
          el("span", { class: "ml-3 text-xs text-mute" }, `${fmtDate(r.created_at)} · ${r.author} · ${r.master} · ${r.service}`)),
        el("p", { class: `mt-2 ${r.text ? "" : "text-mute"}` }, r.text || "Без комментария"),
        r.client_id ? el("button", { class: "mt-2 text-xs text-mute hover:text-cream", onclick: () => openClient(r.client_id) }, "Карточка клиента →") : null),
      r.published ? el("span", { class: "rounded-full bg-brass/15 px-3 py-1 text-xs text-brass" }, "на сайте") : null,
      el("div", { class: "flex items-center gap-3" }, low ? null : toggle,
        el("button", { class: "text-sm text-mute hover:text-blood", onclick: async () => { if (confirm("Удалить отзыв?")) { await api(`/reviews/${r.id}`, { method: "DELETE" }); loadReviews(); } } }, "Удалить")),
    );
  }) : [el("p", { class: "text-mute" }, "Отзывов пока нет")]));
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
  f.rebook_days.value = s?.rebook_days ?? 28;
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
    rebook_days: +f.rebook_days.value,
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

function bar(label, value, max, note = "") {
  return el("div", {},
    el("div", { class: "mb-1 flex justify-between text-sm" }, el("span", {}, label), el("span", { class: "text-mute" }, note || value)),
    el("div", { class: "h-2 rounded-full bg-smoke" }, el("div", { class: "h-2 rounded-full bg-brass", style: `width:${max ? (value / max) * 100 : 0}%` })));
}

async function loadStats() {
  $$("[data-period]").forEach((b) => b.setAttribute("aria-pressed", String(+b.dataset.period === ui.period)));
  const s = await api(`/stats?days=${ui.period}`);
  const k = s.summary;
  const kpi = (label, value, hint = "") => el("div", { class: "rounded-3xl border border-line bg-coal p-6" },
    el("p", { class: "font-display text-3xl font-bold text-brass" }, value),
    el("p", { class: "mt-1 text-sm text-mute" }, label), hint ? el("p", { class: "mt-2 text-xs text-mute/70" }, hint) : null);
  const total = k.sources.site + k.sources.bot;
  $("#stats-kpi").replaceChildren(
    kpi("Записей", k.total, `${k.upcoming} впереди · ${k.cancelled} отмен`),
    kpi("Выручка", rub(k.revenue), `за ${k.visited} визитов`),
    kpi("Неявки", `${k.no_show_rate}%`, `${k.no_show} из ${k.visited + k.no_show}`),
    kpi("Из Telegram", total ? `${Math.round((k.sources.bot / total) * 100)}%` : "—", `сайт ${k.sources.site} · бот ${k.sources.bot}`),
  );
  const max = Math.max(1, ...s.per_day.map((d) => d.count));
  const showLabel = (i) => s.days <= 7 || i % 5 === 0 || i === s.per_day.length - 1;
  $("#stats-week").replaceChildren(...s.per_day.map((d, i) => el("div", { class: "flex h-full flex-1 flex-col items-center justify-end gap-2", title: `${human(d.day)}: ${d.count}` },
    s.days <= 7 ? el("span", { class: "text-xs text-mute" }, d.count) : null,
    el("div", { class: "w-full rounded-t bg-brass", style: `height:${(d.count / max) * 100}%;min-height:2px` }),
    el("span", { class: "h-4 text-[10px] text-mute" }, showLabel(i) ? (s.days <= 7 ? human(d.day).split(",")[0] : new Date(`${d.day}T00:00`).getDate()) : ""),
  )));
  $("#stats-masters").replaceChildren(...s.masters.map((m) => el("div", {},
    bar(m.name, m.load, 100, `загрузка ${m.load}%`),
    el("p", { class: "mt-1 text-xs text-mute" }, `${m.bookings} записей · ${rub(m.revenue)} · неявок ${m.no_show}`))));
  const top = Math.max(1, ...s.services.map((x) => x.count));
  $("#stats-services").replaceChildren(...(s.services.length ? s.services.map((x) => bar(x.name, x.count, top)) : [el("p", { class: "text-mute" }, "Пока нет записей")]));
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
$("#add-master").addEventListener("click", () => editMaster());
$("#master-form").addEventListener("submit", saveMaster);
$("#master-photo-file").addEventListener("change", async (e) => {
  try {
    const url = await upload(e.target.files[0]);
    $("#master-form").dataset.photo = url;
    showPhoto(url);
  } catch (err) {
    $("#master-error").textContent = err.message;
    $("#master-error").classList.remove("hidden");
  }
  e.target.value = "";
});
$("#master-photo-remove").addEventListener("click", () => { $("#master-form").dataset.photo = ""; showPhoto(""); });
$("#work-form").addEventListener("submit", saveWork);
$$("[data-period]").forEach((b) => b.addEventListener("click", () => { ui.period = +b.dataset.period; loadStats(); }));
let searchTimer;
$("#c-search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadClients, 250); });

if (store.auth) api("/check").then(start).catch(logout);
