// Telegram Mini App: та же запись, что на сайте, но пользователь известен по initData.
const tg = window.Telegram?.WebApp;
const $ = (s) => document.querySelector(s);
const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
const WEEKDAYS = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];
const st = { services: [], masters: [], service: null, master: null, date: null, time: null, me: null, busy: false };

async function api(path, options = {}) {
  const r = await fetch(`/api${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", "X-Telegram-Init-Data": tg?.initData ?? "", ...options.headers },
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(Array.isArray(data.detail) ? "Проверьте имя и телефон" : data.detail || "Ошибка, попробуйте ещё раз");
  return data;
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

function haptic() {
  tg?.HapticFeedback?.selectionChanged();
}

function pick(container, items, selected, onPick, render) {
  container.replaceChildren();
  if (!items.length) {
    container.append(el("p", "col-span-full text-sm text-mute/60", "Нет свободного времени"));
    return;
  }
  for (const item of items) {
    const b = render(item);
    b.type = "button";
    b.setAttribute("aria-pressed", String(item.value === selected));
    b.addEventListener("click", () => { haptic(); onPick(item.value); });
    container.append(b);
  }
}

function hint(container, text) {
  container.replaceChildren(el("p", "col-span-full text-sm text-mute/60", text));
}

function renderServices() {
  pick($("#services"), st.services.map((s) => ({ value: s.id, s })), st.service, (id) => {
    st.service = id;
    const ids = st.services.find((s) => s.id === id).master_ids;
    if (!ids.includes(st.master)) st.master = null;
    renderServices();
    renderMasters();
  }, ({ s }) => {
    const b = el("button", "chip flex items-center justify-between !rounded-2xl !px-4 !py-3 text-left");
    const left = el("span");
    left.append(el("span", "block font-semibold", s.name), el("span", "block text-xs opacity-70", `${s.duration_min} мин`));
    b.append(left, el("span", "font-display", `${s.price} ₽`));
    return b;
  });
}

function renderMasters() {
  if (!st.service) return hint($("#masters"), "Сначала выберите услугу");
  const ids = st.services.find((s) => s.id === st.service).master_ids;
  pick($("#masters"), st.masters.filter((m) => ids.includes(m.id)).map((m) => ({ value: m.id, m })), st.master, (id) => {
    st.master = id;
    renderMasters();
    loadDates();
  }, ({ m }) => {
    const b = el("button", "group chip flex flex-col items-center gap-2 !rounded-2xl !px-2 !py-3");
    if (m.photo) {
      const img = el("img", "size-12 rounded-full object-cover");
      img.src = m.photo;
      img.alt = "";
      b.append(img);
    } else {
      b.append(el("span", "grid size-12 place-items-center rounded-full bg-brass/15 font-display text-lg text-brass group-aria-pressed:bg-ink/15 group-aria-pressed:text-ink", m.name[0]));
    }
    b.append(el("span", "text-sm", m.name));
    return b;
  });
  if (!st.master) { hint($("#dates"), "Выберите мастера"); hint($("#times"), "Выберите дату"); }
  update();
}

async function loadDates() {
  st.date = st.time = null;
  update();
  hint($("#dates"), "Загружаем…");
  hint($("#times"), "Выберите дату");
  const dates = await api(`/dates?master_id=${st.master}&service_id=${st.service}`);
  const render = () => pick($("#dates"), dates.map((d) => ({ value: d })), st.date, (d) => { st.date = d; render(); loadTimes(); }, ({ value }) => {
    const d = new Date(`${value}T00:00:00`);
    const b = el("button", "chip flex shrink-0 flex-col items-center !rounded-2xl !px-4 !py-2");
    b.append(el("span", "text-xs opacity-70", WEEKDAYS[d.getDay()]), el("span", "font-display text-lg", d.getDate()), el("span", "text-xs opacity-70", MONTHS[d.getMonth()]));
    return b;
  });
  render();
}

async function loadTimes() {
  st.time = null;
  update();
  hint($("#times"), "Загружаем…");
  const times = await api(`/slots?master_id=${st.master}&service_id=${st.service}&day=${st.date}`);
  const render = () => pick($("#times"), times.map((t) => ({ value: t })), st.time, (t) => { st.time = t; render(); update(); },
    ({ value }) => el("button", "chip !px-0 text-center", value));
  render();
}

function ready() {
  const consentOk = st.me?.consent || $("#consent").checked;
  return Boolean(st.service && st.master && st.date && st.time && $("#name").value.trim() && $("#phone").value.trim() && consentOk && !st.busy);
}

function update() {
  const ok = ready();
  if (tg?.MainButton) {
    tg.MainButton.setText(st.time ? `Записаться на ${st.time}` : "Записаться");
    ok ? tg.MainButton.enable() : tg.MainButton.disable();
    tg.MainButton.setParams({ color: ok ? "#c9a266" : "#3a3530", text_color: ok ? "#11100e" : "#a89f92" });
  }
  $("#fallback-btn").disabled = !ok;
}

async function submit() {
  if (!ready()) return;
  st.busy = true;
  update();
  tg?.MainButton?.showProgress();
  $("#error").classList.add("hidden");
  try {
    const r = await api("/tg/bookings", {
      method: "POST",
      body: JSON.stringify({
        service_id: st.service, master_id: st.master, start_at: `${st.date}T${st.time}:00`,
        name: $("#name").value.trim(), phone: $("#phone").value, consent: st.me?.consent || $("#consent").checked,
      }),
    });
    tg?.HapticFeedback?.notificationOccurred("success");
    $("#flow").classList.add("hidden");
    $("#fallback").classList.add("hidden");
    $("#done").classList.remove("hidden");
    $("#done-summary").textContent = r.summary;
    tg?.MainButton?.hide();
    setTimeout(() => tg?.close(), 4000);
  } catch (e) {
    tg?.HapticFeedback?.notificationOccurred("error");
    $("#error").textContent = e.message;
    $("#error").classList.remove("hidden");
    if (/занято/.test(e.message)) loadTimes();
  } finally {
    st.busy = false;
    tg?.MainButton?.hideProgress();
    update();
  }
}

async function init() {
  if (!tg?.initData) {
    $("#outside").classList.remove("hidden");
    $("#flow").classList.add("hidden");
    return;
  }
  tg.ready();
  tg.expand();
  tg.setHeaderColor?.("#11100e");
  tg.setBackgroundColor?.("#11100e");
  tg.MainButton.onClick(submit);
  tg.MainButton.show();
  if (!tg.isVersionAtLeast?.("6.1")) $("#fallback").classList.remove("hidden");

  ["#name", "#phone", "#consent"].forEach((s) => $(s).addEventListener("input", update));
  $("#consent-toggle").addEventListener("click", (e) => { e.preventDefault(); $("#consent-text").classList.toggle("hidden"); });
  $("#fallback-btn").addEventListener("click", submit);

  try {
    const [services, masters, me] = await Promise.all([api("/services"), api("/masters"), api("/tg/me")]);
    Object.assign(st, { services, masters, me });
    $("#name").value = me.name ?? "";
    $("#phone").value = me.phone ?? "";
    $("#consent-text").textContent = me.consent_text;
    $("#consent-box").classList.toggle("hidden", me.consent);
    renderServices();
    update();
  } catch (e) {
    $("#error").textContent = e.message;
    $("#error").classList.remove("hidden");
  }
}

init();
