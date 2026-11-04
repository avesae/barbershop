// Статическая демо-версия: отвечает вместо FastAPI прямо в браузере.
// Подключается только в сборке `npm run build:static` (Vercel). Логика слотов,
// статистики и демо-данных повторяет backend/app/{slots,stats,demo}.py.
(() => {
  const KEY = "fade-blade-demo-v1";
  const STEP = 30;
  const LEAD_MIN = 60;
  const DAYS_AHEAD = 14;
  const CONSENT_VERSION = "1.0";
  const DEMO = { user: "demo", password: "demo" };
  const MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
  const WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"];

  // --- время: «наивные» ISO-строки в локальном времени, как в API ------------

  const pad = (n) => String(n).padStart(2, "0");
  const dayIso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const iso = (d) => `${dayIso(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}:00`;
  const parse = (s) => new Date(s.length === 10 ? `${s}T00:00:00` : s);
  const addMin = (d, m) => new Date(d.getTime() + m * 60000);
  const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
  const atTime = (day, hhmm) => { const [h, m] = hhmm.split(":").map(Number); const d = parse(dayIso(day)); d.setHours(h, m); return d; };
  const monWeekday = (d) => (d.getDay() + 6) % 7;
  const now = () => { const d = new Date(); d.setSeconds(0, 0); return d; };
  const overlaps = (a0, a1, b0, b1) => a0 < b1 && b0 < a1;
  const humanDt = (d) => `${d.getDate()} ${MONTHS[d.getMonth()]} (${WD[monWeekday(d)]}), ${pad(d.getHours())}:${pad(d.getMinutes())}`;

  // --- детерминированный генератор случайных чисел -------------------------

  function rng(seed) {
    let a = seed;
    const next = () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
    return { random: next, int: (lo, hi) => lo + Math.floor(next() * (hi - lo + 1)), pick: (arr) => arr[Math.floor(next() * arr.length)] };
  }

  // --- демо-данные ----------------------------------------------------------

  const SERVICES = [
    ["Мужская стрижка", "Консультация, мытьё головы, стрижка и укладка", 1800, 60],
    ["Стрижка машинкой", "Одна насадка по всей голове, окантовка", 1000, 30],
    ["Фейд", "Плавный переход от кожи, укладка", 2000, 60],
    ["Моделирование бороды", "Форма, контур опасной бритвой, уход маслом", 1200, 30],
    ["Стрижка + борода", "Комплекс: стрижка и оформление бороды", 2800, 90],
    ["Королевское бритьё", "Распаривание горячим полотенцем, бритьё опасной бритвой", 1500, 45],
  ];
  const MASTERS = [
    ["Артём", "Топ-барбер", "10 лет за креслом. Классические стрижки и сложные фейды.", [1, 2, 3, 4, 5, 6], [0, 1, 2, 3, 4], ["10:00", "20:00"]],
    ["Тимур", "Барбер", "Мастер бороды и королевского бритья.", [1, 2, 4, 5, 6], [1, 2, 3, 4, 5], ["11:00", "21:00"]],
    ["Даниил", "Барбер", "Короткие стрижки и аккуратные переходы.", [1, 2, 3, 5], [0, 2, 4, 5, 6], ["10:00", "19:00"]],
  ];
  const NAMES = ["Алексей", "Дмитрий", "Максим", "Игорь", "Никита", "Павел", "Роман", "Сергей", "Егор", "Кирилл", "Андрей", "Михаил",
    "Владимир", "Константин", "Глеб", "Фёдор", "Марк", "Лев", "Степан", "Илья", "Антон", "Олег", "Вадим", "Георгий"];
  const NOTES = ["Короче на висках", "Не любит воск", "Пьёт эспрессо без сахара", "Аллергия на ментол", "Всегда к одному мастеру"];
  const REVIEWS = {
    5: ["Лучший фейд, что у меня был. Мастер своего дела!", "Записался через бота за минуту, пришёл — сразу посадили. Стрижка огонь.",
      "Королевское бритьё — must try. Горячие полотенца, атмосфера, всё на уровне.",
      "Хожу уже полгода, ни разу не разочаровали. Напоминание в Telegram — очень удобно.",
      "Бороду наконец-то привели в форму. Золотые руки у мастера."],
    4: ["Хорошая стрижка, уютно. Немного подождал, но кофе скрасил ожидание.", "Всё понравилось, в следующий раз попробую комплекс с бородой."],
  };

  function generate() {
    const r = rng(42);
    const t = now();
    const s = { seq: 0, services: [], masters: [], timeOff: [], clients: [], consents: [], bookings: [], reviews: [], works: [], created: dayIso(t) };
    const id = () => ++s.seq;
    SERVICES.forEach(([name, description, price, duration_min], i) =>
      s.services.push({ id: id(), name, description, price, duration_min, is_active: true, sort: i, rebook_days: 28 }));
    MASTERS.forEach(([name, title, bio, svc, days, [start, end]]) =>
      s.masters.push({ id: id(), name, title, bio, photo: null, is_active: true, telegram: false,
        service_ids: svc.map((i) => s.services[i - 1].id), hours: days.map((weekday) => ({ weekday, start, end })) }));

    const letters = "АБВГДЕЖЗИКЛМНОПРСТУФХЧШ";
    for (let i = 0; i < 200; i++) {
      const c = { id: id(), name: `${r.pick(NAMES)} ${r.pick([...letters])}.`, phone: "+79" + Array.from({ length: 9 }, () => r.int(0, 9)).join(""),
        telegram: r.random() < 0.6, notes: r.random() < 0.3 ? r.pick(NOTES) : "", created_at: iso(addDays(t, -r.int(31, 365))) };
      s.clients.push(c);
      s.consents.push({ client_id: c.id, version: CONSENT_VERSION, source: r.random() < 0.6 ? "bot" : "site", accepted_at: c.created_at });
    }

    for (let d = -30; d <= 7; d++) {
      const day = addDays(parse(dayIso(t)), d);
      for (const m of s.masters) {
        const work = m.hours.filter((h) => h.weekday === monWeekday(day));
        if (!work.length) continue;
        const lunch = [atTime(day, "14:00"), atTime(day, "14:30")];
        if (monWeekday(day) < 5) s.timeOff.push({ id: id(), master_id: m.id, start_at: iso(lunch[0]), end_at: iso(lunch[1]), reason: "Обед" });
        const busy = [lunch];
        const target = d <= 0 ? r.int(5, 8) : r.int(2, 5);
        for (let k = 0; k < target; k++) {
          const svcId = r.pick(m.service_ids);
          const svc = s.services.find((x) => x.id === svcId);
          let options = freeSlots(day, svc.duration_min, work, busy, null, 0);
          if (d >= 0) options = options.filter((x) => addMin(x, svc.duration_min) <= t || x > addMin(t, 60));
          if (!options.length) break;
          const start = r.pick(options);
          const end = addMin(start, svc.duration_min);
          busy.push([start, end]);
          const roll = r.random();
          const past = start < t;
          const status = past ? (roll < 0.07 ? "cancelled" : roll < 0.11 ? "no_show" : "done") : roll < 0.05 ? "cancelled" : "active";
          const client = r.random() < 0.6 ? s.clients[r.int(0, 59)] : r.pick(s.clients);
          s.bookings.push({ id: id(), client_id: client.id, master_id: m.id, service_id: svc.id, start_at: iso(start), end_at: iso(end),
            price: svc.price, status, source: r.random() < 0.62 ? "bot" : "site", created_at: iso(addDays(start, -r.int(1, 10))) });
        }
      }
    }

    const done = s.bookings.filter((b) => b.status === "done");
    for (let i = 0; i < 12 && done.length; i++) {
      const b = done.splice(r.int(0, done.length - 1), 1)[0];
      const roll = r.random();
      const rating = roll < 0.64 ? 5 : roll < 0.91 ? 4 : 3;
      const text = rating >= 4 ? r.pick(REVIEWS[rating]) : "Долго ждал, хотя пришёл вовремя.";
      s.reviews.push({ id: id(), booking_id: b.id, client_id: b.client_id, master_id: b.master_id, rating, text,
        author: s.clients.find((c) => c.id === b.client_id).name, published: rating >= 4, created_at: iso(addMin(parse(b.end_at), 180)) });
    }
    return s;
  }

  // --- хранилище: localStorage, а если оно недоступно — память вкладки ------

  let state;
  function load() {
    try {
      const raw = localStorage.getItem(KEY);
      if (raw) {
        const saved = JSON.parse(raw);
        // Демо «живёт» в текущих датах: на следующий день данные генерируются заново.
        if (saved.created === dayIso(now())) return saved;
      }
    } catch {}
    return generate();
  }
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch {}
  }
  state = load();
  save();

  // --- слоты ----------------------------------------------------------------

  function freeSlots(day, duration, work, busy, at, lead = LEAD_MIN) {
    const earliest = at ? addMin(at, lead) : null;
    const out = [];
    for (const w of [...work].sort((a, b) => a.start.localeCompare(b.start))) {
      const end = atTime(day, w.end);
      for (let t = atTime(day, w.start); addMin(t, duration) <= end; t = addMin(t, STEP)) {
        if (earliest && t < earliest) continue;
        if (busy.some(([b0, b1]) => overlaps(t, addMin(t, duration), b0, b1))) continue;
        out.push(t);
      }
    }
    return out;
  }

  const byId = (list, id) => list.find((x) => x.id === +id);
  class HttpError extends Error { constructor(status, msg) { super(msg); this.status = status; } }

  function bookable(masterId, serviceId) {
    const m = byId(state.masters, masterId);
    const s = byId(state.services, serviceId);
    if (!m || !m.is_active || !s || !s.is_active) throw new HttpError(400, "Мастер или услуга недоступны");
    if (!m.service_ids.includes(s.id)) throw new HttpError(400, "Этот мастер не оказывает выбранную услугу");
    return [m, s];
  }

  function slotsForDay(masterId, serviceId, dayStr, excludeId = null) {
    const t = now();
    const day = parse(dayStr);
    const today = parse(dayIso(t));
    if (day < today || day > addDays(today, DAYS_AHEAD)) return [];
    const [m, s] = bookable(masterId, serviceId);
    const dayEnd = addDays(day, 1);
    const busy = [
      ...state.bookings.filter((b) => b.master_id === m.id && b.status === "active" && b.id !== excludeId),
      ...state.timeOff.filter((x) => x.master_id === m.id),
    ].map((b) => [parse(b.start_at), parse(b.end_at)]).filter(([a, b]) => a < dayEnd && b > day);
    return freeSlots(day, s.duration_min, m.hours.filter((h) => h.weekday === monWeekday(day)), busy, t);
  }

  function normalizePhone(raw) {
    let d = String(raw || "").replace(/\D/g, "");
    if (d.length === 10 && d.startsWith("9")) d = "7" + d;
    if (d.length === 11 && "78".includes(d[0])) return "+7" + d.slice(1);
    throw new HttpError(400, "Укажите номер телефона в формате +7 900 000-00-00");
  }

  // --- представления, как в API --------------------------------------------

  const serviceOut = (s) => ({ ...s, master_ids: state.masters.filter((m) => m.service_ids.includes(s.id)).map((m) => m.id).sort((a, b) => a - b) });
  const client = (id) => byId(state.clients, id);
  function adminBooking(b) {
    const c = b.client_id ? client(b.client_id) : null;
    return { id: b.id, master_id: b.master_id, master: byId(state.masters, b.master_id).name, service: byId(state.services, b.service_id).name,
      start_at: b.start_at, end_at: b.end_at, price: b.price, status: b.status, source: b.source,
      client_name: c?.name ?? null, client_phone: c?.phone ?? null, telegram: Boolean(c?.telegram) };
  }
  function summary(b) {
    return `${byId(state.services, b.service_id).name} — ${b.price} ₽\nМастер: ${byId(state.masters, b.master_id).name}\nКогда: ${humanDt(parse(b.start_at))}`;
  }
  function outcome(b, t) {
    if (b.status === "cancelled" || b.status === "no_show") return b.status;
    return b.status === "done" || parse(b.start_at) <= t ? "visited" : "upcoming";
  }
  function metrics(list, t) {
    const visits = list.filter((b) => outcome(b, t) === "visited").map((b) => b.start_at).sort();
    const gaps = visits.slice(1).map((v, i) => Math.floor((parse(v) - parse(visits[i])) / 86400000));
    const upcoming = list.filter((b) => outcome(b, t) === "upcoming").map((b) => b.start_at).sort();
    return {
      visits: visits.length, no_shows: list.filter((b) => b.status === "no_show").length,
      spent: list.filter((b) => outcome(b, t) === "visited").reduce((a, b) => a + b.price, 0),
      last_visit: visits.at(-1) ?? null, next_visit: upcoming[0] ?? null,
      avg_interval_days: gaps.length ? Math.round(gaps.reduce((a, b) => a + b, 0) / gaps.length) : null,
    };
  }
  function summarize(list, t) {
    const out = list.map((b) => outcome(b, t));
    const visited = list.filter((_, i) => out[i] === "visited");
    const noShow = out.filter((o) => o === "no_show").length;
    const finished = visited.length + noShow;
    const live = list.filter((_, i) => out[i] !== "cancelled");
    return {
      total: live.length, visited: visited.length, no_show: noShow, cancelled: out.filter((o) => o === "cancelled").length,
      upcoming: out.filter((o) => o === "upcoming").length, revenue: visited.reduce((a, b) => a + b.price, 0),
      no_show_rate: finished ? Math.round((noShow / finished) * 1000) / 10 : 0,
      sources: { site: live.filter((b) => b.source === "site").length, bot: live.filter((b) => b.source === "bot").length },
    };
  }
  function workingMinutes(m, first, days) {
    let total = 0;
    for (let i = 0; i < days; i++) {
      const d = addDays(first, i);
      for (const w of m.hours.filter((h) => h.weekday === monWeekday(d))) {
        const w0 = atTime(d, w.start), w1 = atTime(d, w.end);
        let mins = (w1 - w0) / 60000;
        for (const o of state.timeOff.filter((x) => x.master_id === m.id)) {
          const lo = Math.max(w0, parse(o.start_at)), hi = Math.min(w1, parse(o.end_at));
          if (lo < hi) mins -= (hi - lo) / 60000;
        }
        total += Math.max(0, mins);
      }
    }
    return total;
  }
  const inRange = (b, start, end) => parse(b.start_at) >= start && parse(b.start_at) < end;

  // --- маршруты -------------------------------------------------------------

  const routes = [];
  const on = (method, pattern, fn) => routes.push({ method, re: new RegExp(`^${pattern.replace(/:\w+/g, "(\\d+)")}$`), fn });

  on("GET", "/api/health", () => ({ ok: true }));
  on("GET", "/api/info", () => ({
    name: "Fade & Blade", address: "Москва, ул. Покровка, 17", phone: "+7 (495) 000-00-00", bot_username: "",
    consent_version: CONSENT_VERSION, demo: DEMO, static_demo: true,
    consent_text: "Записываясь, вы даёте согласие барбершопу «Fade & Blade» на обработку персональных данных: имени, номера телефона и Telegram ID.\n\n" +
      "Зачем: запись на услугу, напоминания о визите, связь по записи.\nГде хранятся: на нашем сервере в России, третьим лицам не передаются.\n" +
      "Сколько: до отзыва согласия. Отозвать его и удалить данные можно кнопкой «Удалить мои данные» в боте.\n\n" +
      `Политика конфиденциальности: ${location.origin}/privacy.html\nВерсия текста: ${CONSENT_VERSION}`,
  }));
  on("GET", "/api/services", () => state.services.filter((s) => s.is_active).sort((a, b) => a.sort - b.sort || a.id - b.id)
    .map((s) => { const o = serviceOut(s); o.master_ids = o.master_ids.filter((id) => byId(state.masters, id).is_active); return o; }));
  on("GET", "/api/masters", () => state.masters.filter((m) => m.is_active)
    .map((m) => ({ id: m.id, name: m.name, title: m.title, bio: m.bio, photo: m.photo, service_ids: [...m.service_ids].sort((a, b) => a - b) })));
  on("GET", "/api/works", () => [...state.works].reverse().slice(0, 12).map((w) => ({ photo: w.photo, caption: w.caption })));
  on("GET", "/api/reviews", () => state.reviews.filter((r) => r.published).sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 9)
    .map((r) => ({ rating: r.rating, text: r.text, author: r.author, master: byId(state.masters, r.master_id).name, date: r.created_at.slice(0, 10) })));
  on("GET", "/api/dates", (q) => {
    const today = parse(dayIso(now()));
    return Array.from({ length: DAYS_AHEAD + 1 }, (_, i) => dayIso(addDays(today, i)))
      .filter((d) => slotsForDay(q.get("master_id"), q.get("service_id"), d).length);
  });
  on("GET", "/api/slots", (q) => slotsForDay(q.get("master_id"), q.get("service_id"), q.get("day")).map((t) => `${pad(t.getHours())}:${pad(t.getMinutes())}`));
  on("POST", "/api/bookings", (_, body) => {
    if (!body.consent) throw new HttpError(400, "Нужно согласие на обработку персональных данных");
    if (!String(body.name || "").trim()) throw new HttpError(400, "Укажите имя");
    const phone = normalizePhone(body.phone);
    const [, s] = bookable(body.master_id, body.service_id);
    const start = parse(body.start_at);
    if (!slotsForDay(body.master_id, body.service_id, dayIso(start)).some((t) => +t === +start)) throw new HttpError(409, "Это время уже занято, выберите другое");
    let c = state.clients.find((x) => x.phone === phone);
    if (!c) { c = { id: ++state.seq, phone, telegram: false, notes: "", created_at: iso(now()) }; state.clients.push(c); }
    c.name = String(body.name).trim().slice(0, 100);
    state.consents.push({ client_id: c.id, version: CONSENT_VERSION, source: "site", accepted_at: iso(now()) });
    const b = { id: ++state.seq, client_id: c.id, master_id: +body.master_id, service_id: s.id, start_at: iso(start),
      end_at: iso(addMin(start, s.duration_min)), price: s.price, status: "active", source: "site", created_at: iso(now()) };
    state.bookings.push(b);
    save();
    return [201, { id: b.id, summary: summary(b), bot_link: null }];
  });

  // админка
  on("GET", "/api/admin/check", () => ({ ok: true }));
  on("GET", "/api/admin/schedule", (q) => {
    const start = parse(q.get("day"));
    const end = addDays(start, +(q.get("days") || 1));
    return {
      masters: state.masters.filter((m) => m.is_active).map((m) => ({ id: m.id, name: m.name, hours: m.hours })),
      bookings: state.bookings.filter((b) => b.status !== "cancelled" && inRange(b, start, end)).sort((a, b) => a.start_at.localeCompare(b.start_at)).map(adminBooking),
      time_off: state.timeOff.filter((t) => parse(t.start_at) < end && parse(t.end_at) > start),
    };
  });
  on("GET", "/api/admin/bookings", (q) => {
    const today = parse(dayIso(now()));
    const start = q.get("date_from") ? parse(q.get("date_from")) : today;
    const end = addDays(q.get("date_to") ? parse(q.get("date_to")) : addDays(today, 14), 1);
    return state.bookings.filter((b) => inRange(b, start, end) && (!q.get("status") || b.status === q.get("status")))
      .sort((a, b) => a.start_at.localeCompare(b.start_at)).map(adminBooking);
  });
  on("POST", "/api/admin/bookings/:id/cancel", (_, __, [id]) => {
    const b = byId(state.bookings, id);
    if (b.status !== "active") throw new HttpError(400, "Запись уже отменена");
    b.status = "cancelled";
    save();
    return adminBooking(b);
  });
  on("POST", "/api/admin/bookings/:id/status", (_, body, [id]) => {
    const b = byId(state.bookings, id);
    if (b.status === "cancelled") throw new HttpError(400, "Запись отменена");
    if (parse(b.start_at) > now()) throw new HttpError(400, "Визит ещё не начался");
    b.status = body.status;
    save();
    return adminBooking(b);
  });
  on("GET", "/api/admin/services", () => [...state.services].sort((a, b) => a.sort - b.sort || a.id - b.id).map(serviceOut));
  function applyService(s, body) {
    Object.assign(s, { name: body.name, description: body.description || "", price: +body.price, duration_min: +body.duration_min,
      is_active: body.is_active !== false, rebook_days: +(body.rebook_days ?? 28) });
    for (const m of state.masters) {
      m.service_ids = m.service_ids.filter((x) => x !== s.id);
      if ((body.master_ids || []).includes(m.id)) m.service_ids.push(s.id);
    }
    save();
    return serviceOut(s);
  }
  on("POST", "/api/admin/services", (_, body) => { const s = { id: ++state.seq, sort: 100 }; state.services.push(s); return [201, applyService(s, body)]; });
  on("PUT", "/api/admin/services/:id", (_, body, [id]) => applyService(byId(state.services, id), body));
  on("GET", "/api/admin/masters", () => state.masters);
  function applyMaster(m, body) {
    for (const h of body.hours || []) if (h.end <= h.start) throw new HttpError(422, "Конец смены должен быть позже начала");
    Object.assign(m, { name: body.name, title: body.title || "Барбер", bio: body.bio || "", photo: body.photo || null,
      is_active: body.is_active !== false, service_ids: body.service_ids || [], hours: body.hours || [] });
    save();
    return m;
  }
  on("POST", "/api/admin/masters", (_, body) => { const m = { id: ++state.seq, telegram: false }; state.masters.push(m); return [201, applyMaster(m, body)]; });
  on("PUT", "/api/admin/masters/:id", (_, body, [id]) => applyMaster(byId(state.masters, id), body));
  on("POST", "/api/admin/masters/:id/invite", () => ({ code: "demo", link: null }));
  on("GET", "/api/admin/time-off", () => {
    const today = parse(dayIso(now()));
    return state.timeOff.filter((t) => parse(t.end_at) > today && t.reason !== "Обед").sort((a, b) => a.start_at.localeCompare(b.start_at));
  });
  on("POST", "/api/admin/time-off", (_, body) => {
    const day = parse(body.day);
    const start = body.start ? atTime(day, body.start) : day;
    const end = body.end ? atTime(day, body.end) : addDays(day, 1);
    if (end <= start) throw new HttpError(400, "Конец должен быть позже начала");
    const t = { id: ++state.seq, master_id: +body.master_id, start_at: iso(start), end_at: iso(end), reason: body.reason || "Закрыто" };
    state.timeOff.push(t);
    save();
    return [201, t];
  });
  on("DELETE", "/api/admin/time-off/:id", (_, __, [id]) => { state.timeOff = state.timeOff.filter((t) => t.id !== +id); save(); return [204, null]; });
  on("GET", "/api/admin/stats", (q) => {
    const days = +(q.get("days") || 7);
    const t = now();
    const first = addDays(parse(dayIso(t)), -(days - 1));
    const end = addDays(parse(dayIso(t)), 1);
    const list = state.bookings.filter((b) => inRange(b, first, end));
    const live = list.filter((b) => b.status !== "cancelled");
    const counts = {};
    for (const b of live) counts[b.start_at.slice(0, 10)] = (counts[b.start_at.slice(0, 10)] || 0) + 1;
    const svc = {};
    for (const b of live) { const n = byId(state.services, b.service_id).name; svc[n] = (svc[n] || 0) + 1; }
    return {
      days,
      per_day: Array.from({ length: days }, (_, i) => { const d = dayIso(addDays(first, i)); return { day: d, count: counts[d] || 0 }; }),
      summary: summarize(list, t),
      services: Object.entries(svc).sort((a, b) => b[1] - a[1]).map(([name, count]) => ({ name, count })),
      masters: state.masters.filter((m) => m.is_active).map((m) => {
        const mine = list.filter((b) => b.master_id === m.id);
        const booked = mine.filter((b) => b.status !== "cancelled").reduce((a, b) => a + (parse(b.end_at) - parse(b.start_at)) / 60000, 0);
        const work = workingMinutes(m, first, days);
        const s = summarize(mine, t);
        return { name: m.name, bookings: s.total, revenue: s.revenue, no_show: s.no_show, load: work ? Math.round(Math.min(booked / work, 1) * 1000) / 10 : 0 };
      }),
    };
  });
  on("GET", "/api/admin/clients", (q) => {
    const t = now();
    const query = (q.get("q") || "").trim().toLowerCase();
    const digits = query.replace(/\D/g, "");
    return state.clients
      .filter((c) => c.phone && (!query || (c.name || "").toLowerCase().includes(query) || (digits && c.phone.includes(digits))))
      .map((c) => ({ id: c.id, name: c.name, phone: c.phone, telegram: c.telegram, ...metrics(state.bookings.filter((b) => b.client_id === c.id), t) }))
      .sort((a, b) => (b.next_visit || b.last_visit || "").localeCompare(a.next_visit || a.last_visit || ""));
  });
  on("GET", "/api/admin/clients/:id", (_, __, [id]) => {
    const c = client(id);
    const mine = state.bookings.filter((b) => b.client_id === c.id).sort((a, b) => a.start_at.localeCompare(b.start_at));
    const consent = state.consents.filter((x) => x.client_id === c.id).at(-1);
    const rating = Object.fromEntries(state.reviews.filter((r) => r.client_id === c.id).map((r) => [r.booking_id, r.rating]));
    return { ...c, consent: consent || null, ...metrics(mine, now()),
      history: mine.reverse().map((b) => ({ id: b.id, start_at: b.start_at, service: byId(state.services, b.service_id).name,
        master: byId(state.masters, b.master_id).name, price: b.price, status: b.status, source: b.source, rating: rating[b.id] ?? null })) };
  });
  on("PUT", "/api/admin/clients/:id/notes", (_, body, [id]) => { client(id).notes = body.notes; save(); return { notes: body.notes }; });
  on("GET", "/api/admin/reviews", () => [...state.reviews].sort((a, b) => b.created_at.localeCompare(a.created_at)).map((r) => {
    const b = byId(state.bookings, r.booking_id);
    return { ...r, master: byId(state.masters, r.master_id).name, service: byId(state.services, b.service_id).name };
  }));
  on("PUT", "/api/admin/reviews/:id", (_, body, [id]) => {
    const r = byId(state.reviews, id);
    if (body.published && !r.text) throw new HttpError(400, "Публикуются только отзывы с текстом");
    r.published = body.published;
    save();
    return r;
  });
  on("DELETE", "/api/admin/reviews/:id", (_, __, [id]) => { state.reviews = state.reviews.filter((r) => r.id !== +id); save(); return [204, null]; });
  on("GET", "/api/admin/works", () => [...state.works].reverse());
  on("POST", "/api/admin/works", (_, body) => {
    const w = { id: ++state.seq, photo: body.photo, caption: body.caption || "", master_id: body.master_id ?? null };
    state.works.push(w);
    save();
    return [201, w];
  });
  on("DELETE", "/api/admin/works/:id", (_, __, [id]) => { state.works = state.works.filter((w) => w.id !== +id); save(); return [204, null]; });
  on("POST", "/api/admin/uploads", async (_, form) => {
    const file = form.get("file");
    if (!file || !file.type.startsWith("image/")) throw new HttpError(400, "Это не похоже на картинку");
    return [201, { url: await shrink(file) }];
  });

  // Фото в демо хранятся в браузере, поэтому ужимаем сильнее, чем на сервере.
  async function shrink(file) {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, 800 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.8);
  }

  // --- подмена fetch --------------------------------------------------------

  const realFetch = window.fetch.bind(window);
  const json = (status, data) => new Response(status === 204 ? null : JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });

  window.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === "string" ? input : input.url, location.origin);
    if (url.origin !== location.origin || !url.pathname.startsWith("/api")) return realFetch(input, init);
    const method = (init.method || "GET").toUpperCase();
    if (url.pathname.startsWith("/api/admin")) {
      const auth = new Headers(init.headers).get("Authorization") || "";
      let creds = "";
      try { creds = decodeURIComponent(escape(atob(auth.replace(/^Basic /, "")))); } catch {}
      if (creds !== `${DEMO.user}:${DEMO.password}`) return json(401, { detail: "Неверный логин или пароль" });
    }
    for (const r of routes) {
      const m = r.method === method && url.pathname.match(r.re);
      if (!m) continue;
      try {
        const body = init.body instanceof FormData ? init.body : init.body ? JSON.parse(init.body) : {};
        const result = await r.fn(url.searchParams, body, m.slice(1));
        return Array.isArray(result) && typeof result[0] === "number" && result.length === 2 ? json(result[0], result[1]) : json(200, result);
      } catch (e) {
        if (e instanceof HttpError) return json(e.status, { detail: e.message });
        console.error(e);
        return json(500, { detail: "Ошибка демо-версии" });
      }
    }
    return json(404, { detail: "Не найдено" });
  };

  // --- плашка «статическое демо» --------------------------------------------

  document.addEventListener("DOMContentLoaded", () => {
    const strip = document.querySelector("body > div.bg-cream > div");
    if (!strip) return;
    const note = document.createElement("span");
    note.className = "opacity-70";
    note.textContent = "Данные демо хранятся только в вашем браузере";
    const reset = document.createElement("button");
    reset.className = "underline decoration-ink/30 hover:decoration-ink";
    reset.textContent = "Сбросить демо";
    reset.addEventListener("click", () => { try { localStorage.removeItem(KEY); } catch {} location.reload(); });
    strip.append(note, reset);
  });
})();
