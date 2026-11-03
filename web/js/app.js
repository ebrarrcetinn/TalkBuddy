// Ekranlar arası geçiş: karşılama → hesap → seni tanıyalım → seviye → partner → ilk konuşma → ana sayfa.
const LEVELS = [
  ["A1", "Başlangıç"],
  ["A2", "Temel"],
  ["B1", "Orta"],
  ["B2", "Orta üstü"],
  ["C1", "İleri"],
  ["C2", "Çok ileri"],
];
const AGE_LABELS = {
  "0-6": "0–6 yaş",
  "7-14": "7–14 yaş",
  "15-20": "15–20 yaş",
  "21-24": "21–24 yaş",
  "25-30": "25–30 yaş",
  "31-35": "31–35 yaş",
  "36+": "36 yaş ve üzeri",
};
const PARTNERS = { Female_Coach: "Kadın partner", Male_Coach: "Erkek partner" };
const STATUS_LABELS = {
  NEW: "Yeni",
  LEARNING: "Öğreniyorum",
  REVIEW: "Tekrar ediyorum",
  MASTERED: "Kullanabiliyorum",
};

const $ = (id) => document.getElementById(id);
let me = null;
let resetToken = null;
// İlgi alanı listesi sunucudan bir kez alınır; kurulum, profil ve konu seçimi aynı listeyi kullanır.
let interestList = null;

async function interests() {
  interestList ??= await api.interests();
  return interestList;
}

function levelLabel(code) {
  const found = LEVELS.find(([level]) => level === code);
  return found ? `${found[0]} ${found[1]}` : "Henüz belirlenmedi";
}

// Alt gezinme yalnızca ana bölümlerde ve onların alt ekranlarında görünür;
// kurulum ve konuşma sırasında gizlenir.
const TAB_OF = {
  home: "home",
  notifications: "home",
  words: "words",
  progress: "progress",
  profile: "profile",
  personal: "profile",
  password: "profile",
  preferences: "profile",
  settings: "profile",
};

// Veri bekleyen bir ekran, bu arada kullanıcı başka ekrana geçtiyse kendini açmaz.
let screenTicket = 0;

function ticket() {
  const current = screenTicket;
  return () => current === screenTicket;
}

// direction verilirse ekran yana kayarak gelir: "forward" sağdan, "back" soldan.
// Hesap ekranları geniş ekranda iki sütunlu açılır.
const AUTH_SCREENS = ["login", "register", "forgot", "reset"];

function show(name, direction) {
  screenTicket += 1;
  document.body.classList.toggle("auth-page", AUTH_SCREENS.includes(name));
  for (const screen of document.querySelectorAll("[data-screen]")) {
    screen.hidden = screen.id !== `screen-${name}`;
    screen.classList.remove("slide-forward", "slide-back");
    if (!screen.hidden && direction) {
      void screen.offsetWidth;
      screen.classList.add(`slide-${direction}`);
    }
  }
  const tab = TAB_OF[name];
  $("tabbar").hidden = !tab;
  for (const button of document.querySelectorAll(".tab")) {
    button.classList.toggle("active", button.dataset.go === tab);
    if (button.dataset.go === tab) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  window.scrollTo(0, 0);
}

// Seçenek düğmeleri üretir; seçili olan "selected" sınıfı alır.
function renderOptions(container, items, selected, onPick) {
  container.replaceChildren();
  for (const [value, label] of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "option";
    button.textContent = label;
    button.classList.toggle("selected", [].concat(selected).includes(value));
    button.addEventListener("click", () => onPick(value, button));
    container.append(button);
  }
}

// Alan hataları ilgili kutunun altında, genel hata formun sonunda gösterilir.
function formError(form, error) {
  for (const old of form.querySelectorAll(".field-error")) old.remove();
  const fields = error?.fields ?? {};
  for (const input of form.querySelectorAll("input")) {
    const message = fields[input.name];
    input.classList.toggle("invalid", Boolean(message));
    if (message) {
      const note = document.createElement("span");
      note.className = "field-error";
      note.textContent = message;
      input.closest("label").append(note);
    }
  }
  const box = form.querySelector(".form-error");
  const general = Object.keys(fields).length ? "" : error?.message ?? "";
  box.textContent = general;
  box.hidden = !general;
}

function formData(form) {
  return Object.fromEntries(new FormData(form));
}

// Formu gönderirken düğmeyi kilitler, böylece iki kez gönderilmez.
async function submitting(form, action) {
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  formError(form, null);
  try {
    await action();
  } catch (error) {
    formError(form, error);
  } finally {
    button.disabled = false;
  }
}

// Kullanıcının kurulum adımına göre doğru ekranı açar.
async function route() {
  try {
    me = await api.me();
  } catch (error) {
    if (error.status === 401) return show("login");
    $("screen-loading").textContent = error.message;
    return show("loading");
  }
  const step = me.onboarding_step;
  if (step === "age") return showAge();
  if (step === "level") return showLevel();
  if (step === "assessment") return showAssessment();
  if (step === "result") return showResult();
  if (step === "interests") return showInterests();
  if (step === "goal") return showGoal();
  if (step === "partner") return showPartner();
  return showHome();
}

// Hesap ekranları

for (const button of document.querySelectorAll(".toggle-password")) {
  button.addEventListener("click", () => {
    const input = button.parentElement.querySelector("input");
    const hidden = input.type === "password";
    input.type = hidden ? "text" : "password";
    button.textContent = hidden ? "Gizle" : "Göster";
  });
}

for (const button of document.querySelectorAll("[data-go]")) {
  button.addEventListener("click", () => {
    const target = button.dataset.go;
    if (target === "home") return showHome();
    if (target === "words") return showWords();
    if (target === "profile") return showProfile();
    if (target === "progress") return showProgressScreen();
    if (target === "personal") return showPersonal();
    if (target === "password") return showPassword();
    if (target === "preferences") return showPreferences();
    if (target === "settings") return showSettings();
    show(target);
  });
}

$("login-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  submitting(form, async () => {
    // Boş alan sunucuya gönderilmez; hangi alanın eksik olduğu kutunun altında yazılır.
    const { email, password } = formData(form);
    const missing = {};
    if (!email.trim()) missing.email = "E-posta adresini yaz.";
    if (!password) missing.password = "Şifreni yaz.";
    if (Object.keys(missing).length) throw new ApiError("", 400, missing);
    await api.login({ ...formData(form), remember: form.elements.remember.checked });
    form.reset();
    await route();
  });
});

$("register-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  submitting(form, async () => {
    await api.register(formData(form));
    form.reset();
    await route();
  });
});

$("forgot-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  const success = form.querySelector(".form-success");
  success.hidden = true;
  submitting(form, async () => {
    const { message } = await api.forgot(formData(form).email);
    success.textContent = message;
    success.hidden = false;
  });
});

$("reset-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  const success = form.querySelector(".form-success");
  success.hidden = true;
  submitting(form, async () => {
    const { password, password_confirm } = formData(form);
    const { message } = await api.reset(resetToken, password, password_confirm);
    form.reset();
    success.textContent = message;
    success.hidden = false;
    history.replaceState(null, "", "/");
  });
});

async function logout() {
  await api.logout().catch(() => {});
  me = null;
  show("login");
}

$("logout").addEventListener("click", logout);
$("settings-logout").addEventListener("click", logout);

// İlk kurulum: her soru kendi ekranında. Seçim yapılınca "Devam et" açılır; seçim sunucuya
// Devam et ile kaydedilir, böylece yarıda bırakan kullanıcı kaldığı adımdan devam eder.
const LEVEL_HINTS = {
  A1: "Birkaç kelime ve basit kalıplar biliyorum.",
  A2: "Kendimi ve günlük işlerimi kısa cümlelerle anlatabilirim.",
  B1: "Tanıdık konularda sohbet edebilirim.",
  B2: "Çoğu konuda rahatça konuşabilirim.",
  C1: "Karmaşık konularda akıcı konuşabilirim.",
  C2: "Neredeyse ana dilim gibi konuşurum.",
};
const choice = { age: null, level: null, interests: new Set(), goal: null, partner: null };

// Tek seçimli liste: seçilen satır işaretlenir ve Devam et düğmesi açılır.
function renderChoices(container, items, selected, next, onPick) {
  container.replaceChildren(
    ...items.map(([value, title, hint]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "choice";
      button.setAttribute("aria-pressed", String(value === selected));
      const name = document.createElement("strong");
      name.textContent = title;
      button.append(name);
      if (hint) {
        const text = document.createElement("span");
        text.textContent = hint;
        button.append(text);
      }
      button.addEventListener("click", () => {
        for (const other of container.children) other.setAttribute("aria-pressed", "false");
        button.setAttribute("aria-pressed", "true");
        next.disabled = false;
        onPick(value);
      });
      return button;
    }),
  );
  next.disabled = selected == null;
}

// Kayıt sırasında düğme kilitlenir; hata olursa sayfanın üstünde gösterilir.
async function saveStep(button, action) {
  button.disabled = true;
  try {
    await action();
  } finally {
    button.disabled = false;
  }
}

// 1. Yaş grubu
async function showAge(direction) {
  const groups = await api.ageGroups();
  choice.age = me.age_group;
  renderChoices($("age-options"), groups.map((group) => [group, AGE_LABELS[group] ?? group]),
    choice.age, $("age-next"), (value) => (choice.age = value));
  show("age", direction);
}

$("age-next").addEventListener("click", (event) =>
  saveStep(event.currentTarget, async () => {
    me = await api.setAgeGroup(choice.age);
    showLevel("forward");
  }));

// 2. Seviye: A1–C2 ya da "Seviyemi bilmiyorum" (isteğe bağlı kelime kontrolü)
function showLevel(direction) {
  choice.level = me.level;
  const items = LEVELS.map(([code, name]) => [code, `${code} · ${name}`, LEVEL_HINTS[code]]);
  if (me.assessment_available) {
    items.push([
      "unknown",
      "Seviyemi bilmiyorum",
      "İsteğe bağlı kelime kontrolü: 5 bölüm × 30 kelime, 5–10 dakika. Kaldığın yer kaydedilir.",
    ]);
  }
  renderChoices($("level-options"), items, choice.level, $("level-next"),
    (value) => (choice.level = value));
  show("level", direction);
}

$("level-back").addEventListener("click", () => showAge("back"));
$("level-next").addEventListener("click", (event) =>
  saveStep(event.currentTarget, async () => {
    if (choice.level === "unknown") return showAssessment("forward");
    me = await api.setLevel(choice.level);
    showInterests("forward");
  }));

// 3. İlgi alanları: en fazla 10; hiç seçmeden geçilebilir.
const MAX_INTERESTS = 10;

async function showInterests(direction) {
  const topics = await interests();
  choice.interests = new Set(me.interests);
  renderOptions($("interest-options"), topics.map((item) => [item, item]), me.interests,
    (item, button) => {
      if (choice.interests.has(item)) choice.interests.delete(item);
      else if (choice.interests.size < MAX_INTERESTS) choice.interests.add(item);
      button.classList.toggle("selected", choice.interests.has(item));
      updateInterestCount();
    });
  updateInterestCount();
  show("interests", direction);
}

function updateInterestCount() {
  const count = choice.interests.size;
  $("interests-count").textContent = `${count} / ${MAX_INTERESTS} seçtin`;
  const next = $("interests-next");
  next.disabled = false;
  next.textContent = count ? "Devam et" : "Şimdilik geç";
}

$("interests-back").addEventListener("click", () => showLevel("back"));
$("interests-next").addEventListener("click", (event) =>
  saveStep(event.currentTarget, async () => {
    me = await api.setInterests([...choice.interests]);
    showGoal("forward");
  }));

// 4. Öğrenme amacı
async function showGoal(direction) {
  const goals = await api.goals();
  choice.goal = me.goal;
  renderChoices($("goal-options"), goals.map((goal) => [goal, goal]), choice.goal, $("goal-next"),
    (value) => (choice.goal = value));
  show("goal", direction);
}

$("goal-back").addEventListener("click", () => showInterests("back"));
$("goal-next").addEventListener("click", (event) =>
  saveStep(event.currentTarget, async () => {
    me = await api.setGoal(choice.goal);
    showPartner("forward");
  }));

// 5. Partner; ardından hiç konuşmamış kullanıcıya ilk kolay konuşma önerilir.
function showPartner(direction) {
  choice.partner = null;
  for (const card of document.querySelectorAll(".partner-card")) {
    card.setAttribute("aria-pressed", "false");
  }
  $("partner-next").disabled = true;
  show("partner", direction);
}

for (const card of document.querySelectorAll(".partner-card")) {
  card.addEventListener("click", () => {
    choice.partner = card.dataset.partner;
    for (const other of document.querySelectorAll(".partner-card")) {
      other.setAttribute("aria-pressed", String(other === card));
    }
    $("partner-next").disabled = false;
  });
}

$("partner-back").addEventListener("click", () => showGoal("back"));
$("partner-next").addEventListener("click", (event) =>
  saveStep(event.currentTarget, async () => {
    me = await api.setPartner(choice.partner);
    if (me.finished_sessions === 0) return showFirst();
    route();
  }));

let assessment = null;
let picked = new Set();
let sending = false;

async function showAssessment(direction) {
  assessment = await api.assessment();
  if (assessment.completed) return showResult();
  $("assessment-guardian").hidden = me.age_group !== "0-6";
  renderSection();
  show("assessment", direction);
}

$("assessment-back").addEventListener("click", () => showLevel("back"));
$("assessment-skip").addEventListener("click", () => showLevel("back"));
$("result-back").addEventListener("click", () => showLevel("back"));

// Kelimeler sabit sırada gösterilir; dokunmak işareti açar/kapatır.
function renderSection() {
  picked = new Set();
  const index = assessment.section;
  $("assessment-step").textContent = `Bölüm ${index + 1} / ${assessment.total_sections}`;
  $("assessment-title").textContent = `${levelLabel(assessment.level)} kelimeleri`;
  const grid = $("assessment-words");
  grid.replaceChildren();
  for (const word of assessment.words) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "word-choice";
    button.textContent = word;
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", () => {
      if (picked.has(word)) picked.delete(word);
      else picked.add(word);
      const on = picked.has(word);
      button.classList.toggle("selected", on);
      button.setAttribute("aria-pressed", String(on));
      updateCounter();
      if (picked.size === assessment.words.length) submitSection();
    });
    grid.append(button);
  }
  updateCounter();
}

function updateCounter() {
  $("assessment-counter").textContent = `İşaretlenen: ${picked.size}/${assessment.words.length}`;
}

// Bölüm bir kez gönderilir; çift tıklama ya da otomatik geçiş tekrar göndermez.
async function submitSection() {
  if (sending) return;
  sending = true;
  $("assessment-done").disabled = true;
  try {
    assessment = await api.submitSection(assessment.section, [...picked]);
    if (assessment.completed) return showResult();
    renderSection();
    window.scrollTo(0, 0);
  } catch (error) {
    $("assessment-counter").textContent = error.message;
  } finally {
    sending = false;
    $("assessment-done").disabled = false;
  }
}

$("assessment-done").addEventListener("click", submitSection);

let recommended = null;

async function showResult() {
  const result = await api.assessmentResult();
  recommended = result.recommended_level;
  // Oxford 5000 C1'de bittiği için bütün bölümleri geçen kullanıcıya "C1 ve üzeri" denir.
  const allPassed = result.scores.every((score) => score.passed);
  $("result-level").textContent = `${levelLabel(recommended)}${allPassed ? " ve üzeri" : ""}`;
  const list = $("result-scores");
  list.replaceChildren();
  for (const score of result.scores) {
    const item = document.createElement("li");
    item.classList.toggle("passed", score.passed);
    const bar = document.createElement("span");
    bar.className = "bar";
    bar.style.setProperty("--fill", `${(score.selected / score.total) * 100}%`);
    item.append(score.level, bar, `${score.selected}/${score.total}`);
    list.append(item);
  }
  $("result-inconsistent").hidden = !result.inconsistent;
  show("result");
}

$("result-accept").addEventListener("click", async () => {
  me = await api.setLevel(recommended);
  showInterests("forward");
});
$("result-other").addEventListener("click", () => showLevel("back"));

function showFirst() {
  const next = me.suggestion;
  character.render($("first-character"), me.partner, "happy");
  $("first-title").textContent =
    `${next.title}: ${next.description} Yaklaşık ${next.minutes} dakika.`;
  show("first");
}

$("first-start").addEventListener("click", () => startSuggested());

function drawPartnerCards() {
  for (const element of document.querySelectorAll(".character[data-persona]")) {
    character.render(element, element.dataset.persona, "happy");
  }
}

// Ana sayfa: önce günün konuşması; diğer bölümler veri biriktikçe görünür.

function showHome() {
  $("home-greeting").textContent = `Hello, ${me.first_name}!`;
  const partner = me.partner === "Male_Coach" ? "erkek" : "kadın";
  $("home-meta").textContent = `Seviye: ${levelLabel(me.level)}. Partner: ${partner}.`;
  character.render($("home-character"), me.partner, "happy");
  showHabit();
  showBell();
  showToday();
  renderTopics();
  renderMinutes();
  $("home-review").hidden = !me.review_due;

  const started = me.finished_sessions > 0;
  $("row-continue").hidden = !(started && (me.last_summary || me.last_topic));
  $("home-continue").textContent = me.last_summary || me.last_topic || "";
  $("row-due").hidden = !me.due_words;
  $("home-due").textContent = `${me.due_words} kelime. Partnerin bugün bunları konuşmada kullanacak.`;
  show("home");
}

// Seri ve günlük hedef: ilk konuşmadan sonra görünür; dili cezalandırıcı değil, destekleyicidir.
function showHabit() {
  $("home-habit").hidden = me.finished_sessions === 0;
  const done = Math.min(me.today_minutes, me.daily_goal);
  $("habit-goal-bar").style.width = `${(done / me.daily_goal) * 100}%`;
  $("habit-goal-text").textContent =
    me.today_minutes >= me.daily_goal
      ? `Bugünkü hedefin tamam: ${me.today_minutes} dakika`
      : `Bugün ${me.today_minutes} / ${me.daily_goal} dakika`;
  $("habit-streak").textContent = me.streak
    ? `Seri: ${me.streak} gün`
    : "Bugün konuşursan yeni bir seri başlar";
}

function showBell() {
  const count = me.unread_notifications;
  $("bell-count").hidden = !count;
  $("bell-count").textContent = count > 9 ? "9+" : String(count);
  $("home-bell").setAttribute("aria-label", count ? `Bildirimler, ${count} yeni` : "Bildirimler");
}

$("home-bell").addEventListener("click", showNotifications);

function showToday() {
  const next = me.suggestion;
  $("today-step").textContent =
    next.kind === "lesson" ? `Başlangıç rotası, adım ${next.step} / ${next.total_steps}` : "Günün konuşması";
  $("today-title").textContent = next.title;
  $("today-text").textContent = next.description;
  $("today-length").textContent = `Yaklaşık ${next.minutes} dakika`;
}

let mode = "practice";

function startTalk(topicChoice, length, lesson = null, talkMode = "practice") {
  mode = talkMode;
  show("talk");
  talk.start(me, showSummary, topicChoice, length, talkMode, lesson);
}

function startSuggested() {
  const next = me.suggestion;
  startTalk(next.topic, next.minutes, next.lesson);
}

$("start-talking").addEventListener("click", startSuggested);
$("start-free").addEventListener("click", () => startTalk(topic, minutes));

// Kendi konusunu seçmek isteyene: ilgi alanları ve "Partnerim seçsin".
let topic = null;

function renderTopics() {
  const options = me.interests;
  topic = null;
  $("home-topics-hint").hidden = options.length > 0;
  renderOptions(
    $("home-topics"),
    [[null, "Partnerim seçsin"], ...options.map((item) => [item, item])],
    null,
    (value, button) => {
      topic = value;
      for (const other of $("home-topics").children) other.classList.remove("selected");
      button.classList.add("selected");
    },
  );
  $("home-topics").firstElementChild.classList.add("selected");
}

// Konuşma süresi: tercih tarayıcıda hatırlanır.
const MINUTES = [5, 10, 15, 20];
let minutes = 10;

function renderMinutes() {
  try {
    minutes = Number(localStorage.getItem("talkbuddy-minutes")) || 10;
  } catch {}
  renderOptions($("home-minutes"), MINUTES.map((value) => [value, `${value} dk`]), minutes, (value) => {
    minutes = value;
    try {
      localStorage.setItem("talkbuddy-minutes", String(value));
    } catch {}
    renderMinutes();
  });
}

$("review-start").addEventListener("click", () => startTalk(null, 15, null, "monthly"));

$("review-snooze").addEventListener("click", async () => {
  await api.snoozeReview();
  me = await api.me();
  $("home-review").hidden = true;
});

// Konuşma sonu özeti: sayılar backend'in kayıtlarından gelir; ilk konuşma ayrıca kutlanır.
async function showSummary(reply, message) {
  const firstTime = me.finished_sessions === 0;
  me = await api.me().catch(() => me);
  const facts = $("summary-facts");
  const lists = $("summary-lists");
  facts.replaceChildren();
  lists.replaceChildren();
  $("summary-next").hidden = true;
  if (!reply) {
    $("summary-title").textContent = "Konuşma bitti";
    $("summary-text").textContent = message ?? "Konuşma başlamadan bitirildi.";
    return show("summary");
  }
  $("summary-title").textContent =
    mode === "monthly" ? "Aylık konuşma değerlendirmen" : firstTime ? "İlk konuşmanı tamamladın!" : "Güzel bir konuşmaydı";
  const report = reply.report;
  $("summary-text").textContent = report.summary || reply.spoken_text;

  const rows = [
    ["Süre", `${report.minutes} dakika`],
    ["Cevapların", String(report.turns)],
  ];
  if (report.start_level !== report.end_level && report.end_level) {
    rows.push(["Seviye", `${report.start_level ?? "?"} → ${report.end_level}`]);
  }
  for (const [term, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = value;
    facts.append(dt, dd);
  }

  addList(lists, "Yeni kelimelerin", report.new_words.map((word) =>
    word.turkish_meaning ? `${word.expression}: ${word.turkish_meaning}` : word.expression));
  addList(lists, "Doğrusunu öğrendiklerin", report.corrections.map((item) =>
    `${item.error} → ${item.correction}`));
  if (mode === "monthly") addList(lists, "Geliştirilecek alanlar", report.focus_areas);

  if (mode !== "monthly") {
    $("summary-next").textContent = `Sıradaki konuşman: ${me.suggestion.title}.`;
    $("summary-next").hidden = false;
  }
  show("summary");
}

function addList(container, title, items) {
  if (!items.length) return;
  const heading = document.createElement("h3");
  heading.textContent = title;
  const list = document.createElement("ul");
  for (const text of items) {
    const item = document.createElement("li");
    item.textContent = text;
    list.append(item);
  }
  container.append(heading, list);
}

// Kelimelerim: tekrar zamanı gelenler önce; her kelime dinlenebilir.
const WORD_FILTERS = [
  ["due", "Tekrar zamanı"],
  ["learning", "Öğreniyorum"],
  ["mastered", "Kullanabildiklerim"],
  ["all", "Hepsi"],
];
let words = [];
let wordFilter = "due";

function isDue(word) {
  return word.status !== "MASTERED" && word.next_review.slice(0, 10) <= localToday();
}

function localToday() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

function matches(word, filter) {
  if (filter === "due") return isDue(word);
  if (filter === "learning") return word.status !== "MASTERED";
  if (filter === "mastered") return word.status === "MASTERED";
  return true;
}

async function showWords() {
  const current = ticket();
  words = await api.vocabulary();
  if (!current()) return;
  if (!words.some(isDue) && wordFilter === "due") wordFilter = "all";
  renderWords();
  show("words");
}

function renderWords() {
  $("words-empty").hidden = words.length > 0;
  $("words-filters").hidden = words.length === 0;
  renderOptions(
    $("words-filters"),
    WORD_FILTERS.map(([key, label]) => [key, `${label} (${words.filter((w) => matches(w, key)).length})`]),
    wordFilter,
    (key) => {
      wordFilter = key;
      renderWords();
    },
  );
  const list = $("words-list");
  list.replaceChildren(...words.filter((word) => matches(word, wordFilter)).map(wordCard));
}

const DATE_FORMAT = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "long" });

function wordCard(word) {
  const card = document.createElement("article");
  card.className = "word-card";

  const head = document.createElement("div");
  head.className = "word-head";
  const name = document.createElement("strong");
  name.textContent = word.expression;
  const listen = document.createElement("button");
  listen.type = "button";
  listen.className = "listen";
  listen.setAttribute("aria-label", `${word.expression} kelimesini dinle`);
  listen.innerHTML =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9Zm12.5 3A4.5 4.5 0 0 0 14 8v8a4.5 4.5 0 0 0 2.5-4Z"/></svg>';
  listen.addEventListener("click", () => voice.speak(word.expression, me.partner, 0.85));
  head.append(name, listen);
  card.append(head);

  if (word.turkish_meaning) {
    const meaning = document.createElement("p");
    meaning.textContent = word.turkish_meaning;
    card.append(meaning);
  }
  if (word.example) {
    const example = document.createElement("p");
    example.className = "muted small";
    example.textContent = word.example;
    card.append(example);
  }
  const state = document.createElement("p");
  state.className = "word-state";
  state.textContent = isDue(word)
    ? "Tekrar zamanı geldi; partnerin bir sonraki konuşmada kullanacak."
    : word.status === "MASTERED"
      ? "Konuşmalarda kullanabiliyorsun."
      : `${STATUS_LABELS[word.status]}. Sonraki tekrar: ${DATE_FORMAT.format(new Date(word.next_review))}.`;
  if (word.cefr_level) state.prepend(`${word.cefr_level}. `);
  card.append(state);
  return card;
}

// Gelişimim: yalnızca kayıtlardan hesaplanan öğrenme bilgileri.
function statRows(container, rows) {
  container.replaceChildren(
    ...rows.flatMap(([term, value]) => {
      const dt = document.createElement("dt");
      dt.textContent = term;
      const dd = document.createElement("dd");
      dd.textContent = value;
      return [dt, dd];
    }),
  );
}

async function showProgressScreen() {
  const current = ticket();
  const data = await api.progress();
  if (!current()) return;
  const empty = data.sessions === 0;
  $("progress-empty").hidden = !empty;
  $("progress-body").hidden = empty;
  show("progress");
  if (empty) return;

  $("progress-today").textContent = `${data.today_minutes} / ${data.daily_goal} dakika`;
  $("progress-goal-bar").style.width = `${Math.min(100, (data.today_minutes / data.daily_goal) * 100)}%`;
  $("progress-streak").textContent = [
    data.goal_met ? "Bugünkü hedefin tamam." : "",
    data.streak ? `Serin: ${data.streak} gün.` : "Bugün konuşursan yeni bir seri başlar.",
    `En uzun serin: ${data.best_streak} gün.`,
  ].filter(Boolean).join(" ");

  renderWeek(data.week);
  const weekMinutes = data.week.reduce((sum, day) => sum + day.minutes, 0);
  statRows($("progress-totals"), [
    ["Bu hafta", `${weekMinutes} dakika`],
    ["Toplam konuşma süresi", `${data.total_minutes} dakika`],
    ["Tamamlanan konuşma", String(data.sessions)],
  ]);

  $("progress-advice-panel").hidden = !data.advice.length;
  $("progress-advice").replaceChildren(...data.advice.map(listItem));

  statRows($("progress-words"), [
    ["Öğrenilen kelimeler", String(data.words_total)],
    ["Kullanabildiklerin", String(data.words_mastered)],
    ["Öğrenmeye devam ettiklerin", String(data.words_learning)],
    ["Tekrar zamanı gelen", String(data.words_due)],
    ["Yapılan tekrarlar", String(data.reviews_done)],
  ]);
  $("progress-review").hidden = !data.words_due;

  $("progress-plan-panel").hidden = !data.plan;
  if (data.plan) {
    const plan = data.plan;
    $("progress-plan").textContent =
      `${plan.level} seviyesinin Oxford kelimelerinden ${plan.known} / ${plan.total} tanesini kullanabiliyorsun (%${plan.percent}). ${plan.learning} kelime öğreniliyor.`;
    $("progress-plan-bar").style.width = `${plan.percent}%`;
  }

  $("progress-mistakes-panel").hidden = !data.mistakes.length;
  $("progress-mistakes").replaceChildren(
    ...data.mistakes.map((item) => {
      const row = listItem(item.name);
      const count = document.createElement("span");
      count.className = "count";
      count.textContent = `${item.count} kez`;
      row.append(count);
      return row;
    }),
  );
  $("progress-monthly-panel").hidden = !data.monthly_reviews.length;
  $("progress-monthly").replaceChildren(
    ...data.monthly_reviews.map((item) =>
      listItem(`${DATE_FORMAT.format(new Date(item.date))}: ${item.summary}`)),
  );
  $("progress-badges").replaceChildren(...data.badges.map(badgeItem));
}

$("progress-review").addEventListener("click", () => {
  wordFilter = "due";
  showWords();
});

function listItem(text) {
  const item = document.createElement("li");
  item.textContent = text;
  return item;
}

// Haftalık grafik: her gün için bir sütun; yükseklik o günün dakikasıyla orantılı.
function renderWeek(week) {
  const chart = $("progress-week");
  const most = Math.max(...week.map((day) => day.minutes), 1);
  chart.setAttribute(
    "aria-label",
    week.map((day) => `${day.day} ${day.minutes} dakika`).join(", "),
  );
  chart.replaceChildren(
    ...week.map((day, index) => {
      const column = document.createElement("div");
      column.className = "week-day";
      column.classList.toggle("is-today", index === week.length - 1);
      const value = document.createElement("span");
      value.className = "week-value";
      value.textContent = day.minutes ? String(day.minutes) : "";
      const bar = document.createElement("span");
      bar.className = "week-bar";
      bar.style.height = `${(day.minutes / most) * 100}%`;
      const label = document.createElement("span");
      label.className = "week-label";
      label.textContent = day.day;
      column.append(value, bar, label);
      return column;
    }),
  );
}

function badgeItem(badge) {
  const item = document.createElement("li");
  item.className = "badge-item";
  item.classList.toggle("earned", badge.earned);
  const title = document.createElement("strong");
  title.textContent = badge.title;
  const text = document.createElement("span");
  text.textContent = badge.earned ? badge.description : "Henüz kazanılmadı";
  item.append(title, text);
  return item;
}

// Bildirim merkezi: açılınca hepsi okundu sayılır.
const NOTICE_TARGETS = {
  daily: "home",
  review: "words",
  weekly: "progress",
  badge: "progress",
  monthly: "home",
};

async function showNotifications() {
  const current = ticket();
  const { items } = await api.notifications();
  if (!current()) return;
  $("notices-empty").hidden = items.length > 0;
  $("notices").replaceChildren(
    ...items.map((notice) => {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "notice-item";
      const title = document.createElement("strong");
      title.textContent = notice.title;
      const text = document.createElement("span");
      text.textContent = notice.text;
      const day = document.createElement("span");
      day.className = "muted small";
      day.textContent = DATE_FORMAT.format(new Date(notice.date));
      button.append(title, text, day);
      button.addEventListener("click", () => {
        const target = NOTICE_TARGETS[notice.type];
        if (target === "words") return showWords();
        if (target === "progress") return showProgressScreen();
        showHome();
      });
      item.append(button);
      return item;
    }),
  );
  show("notifications");
  await api.notificationsSeen();
  me = await api.me();
}

// Profil fotoğrafı yoksa adın baş harfleri gösterilir.
function renderAvatar(element) {
  element.replaceChildren();
  if (me.photo_version) {
    const image = document.createElement("img");
    image.src = `/api/me/photo?v=${encodeURIComponent(me.photo_version)}`;
    image.alt = "";
    element.append(image);
  } else {
    element.textContent = `${me.first_name[0] ?? ""}${me.last_name[0] ?? ""}`.toLocaleUpperCase("tr");
  }
}

// Profil: hesap özeti ve menü.
function showProfile() {
  renderAvatar($("profile-avatar"));
  $("profile-name").textContent = `${me.first_name} ${me.last_name}`;
  $("profile-email").textContent = me.email;
  $("profile-level-tag").textContent = me.level ?? "Seviye yok";
  $("profile-level-tag").title = levelLabel(me.level);
  show("profile");
}

// Ayarlar dokunulduğu an kaydedilir; kısa bir "Kaydedildi" notu görünür.
function saved(id) {
  const note = $(id);
  note.hidden = false;
  clearTimeout(note.timer);
  note.timer = setTimeout(() => (note.hidden = true), 1800);
}

function clearForm(form) {
  form.reset();
  for (const note of form.querySelectorAll(".form-error, .form-success")) note.hidden = true;
  for (const old of form.querySelectorAll(".field-error")) old.remove();
  for (const input of form.querySelectorAll("input")) input.classList.remove("invalid");
}

// Kişisel bilgilerim
function showPersonal() {
  renderAvatar($("personal-avatar"));
  $("photo-remove").hidden = !me.photo_version;
  $("photo-error").hidden = true;
  const nameForm = $("name-form");
  clearForm(nameForm);
  nameForm.elements.first_name.value = me.first_name;
  nameForm.elements.last_name.value = me.last_name;
  clearForm($("email-form"));
  $("personal-email").textContent = me.email;
  renderAge();
  show("personal");
}

function renderAge() {
  renderOptions($("personal-age"), Object.entries(AGE_LABELS), me.age_group, async (value) => {
    me = await api.setAgeGroup(value);
    renderAge();
  });
}

$("name-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  const success = form.querySelector(".form-success");
  success.hidden = true;
  submitting(form, async () => {
    me = await api.setName(formData(form));
    success.textContent = "Adın güncellendi.";
    success.hidden = false;
  });
});

// Fotoğraf tarayıcıda kare kırpılıp 320 piksele küçültülür; konum gibi ek bilgiler gönderilmez.
const PHOTO_SIZE = 320;

async function squarePhoto(file) {
  const bitmap = await createImageBitmap(file);
  const side = Math.min(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = PHOTO_SIZE;
  canvas.height = PHOTO_SIZE;
  canvas
    .getContext("2d")
    .drawImage(
      bitmap,
      (bitmap.width - side) / 2,
      (bitmap.height - side) / 2,
      side,
      side,
      0,
      0,
      PHOTO_SIZE,
      PHOTO_SIZE,
    );
  bitmap.close();
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
}

$("photo-input").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  event.target.value = "";
  if (!file) return;
  const error = $("photo-error");
  error.hidden = true;
  try {
    me = await api.savePhoto(await squarePhoto(file));
    showPersonal();
  } catch (problem) {
    error.textContent = problem.message || "Bu fotoğraf açılamadı. Başka bir fotoğraf dener misin?";
    error.hidden = false;
  }
});

$("photo-remove").addEventListener("click", async () => {
  me = await api.deletePhoto();
  showPersonal();
});

// Şifremi değiştir
function showPassword() {
  const form = $("password-form");
  clearForm(form);
  for (const input of form.querySelectorAll("input")) input.type = "password";
  for (const button of form.querySelectorAll(".toggle-password")) button.textContent = "Göster";
  show("password");
}

// Öğrenme tercihlerim
async function showPreferences() {
  const current = ticket();
  const goals = await api.goals();
  const topics = await interests();
  await voice.ready();
  if (!current()) return;
  $("prefs-level-note").textContent = me.start_level
    ? `Başlangıç seviyen ${levelLabel(me.start_level)}, şu anki seviyen ${levelLabel(me.level)}.`
    : `Şu anki seviyen: ${levelLabel(me.level)}.`;
  const pending = me.level_pending
    ? ` Şu an ${me.level_pending} seviyesine geçiş için ${me.level_pending_turns}/2 doğrulama var.`
    : "";
  $("prefs-level-explain").textContent =
    "Seviyen konuşmalarına göre güncellenir. Her mesajında iki bilgi birleştirilir: partnerinin " +
    "seviye tahmini (%70) ve kullandığın kelimelerin Oxford listesindeki seviyeleri (%30). " +
    "Tek bir cümle seviyeni değiştirmez; yeni seviye iki mesaj üst üste doğrulanırsa geçerli olur." +
    pending;
  const update = (call) => async (value) => {
    me = await call(value);
    saved("prefs-saved");
    showPreferences();
  };
  renderOptions($("prefs-level"), LEVELS.map(([code]) => [code, code]), me.level, update(api.setLevel));
  renderOptions($("prefs-partner"), Object.entries(PARTNERS), me.partner, update(api.setPartner));
  renderOptions(
    $("prefs-daily"),
    [5, 10, 15, 20].map((value) => [value, `${value} dk`]),
    me.daily_goal,
    update((value) => api.saveSettings({ daily_goal: value })),
  );
  renderOptions($("prefs-goal"), goals.map((goal) => [goal, goal]), me.goal, update(api.setGoal));
  renderOptions(
    $("prefs-interests"),
    topics.map((item) => [item, item]),
    me.interests,
    async (item, button) => {
      const chosen = new Set(me.interests);
      if (chosen.has(item)) chosen.delete(item);
      else chosen.add(item);
      me = await api.setInterests([...chosen]);
      button.classList.toggle("selected", me.interests.includes(item));
      saved("prefs-saved");
    },
  );
  $("prefs-rate").value = localSetting("talkbuddy-rate") || "1";
  renderVoices();
  show("preferences");
}

function renderVoices() {
  const select = $("prefs-voice");
  const auto = document.createElement("option");
  auto.value = "";
  auto.textContent = `Otomatik (${me.partner === "Male_Coach" ? "erkek" : "kadın"} sesi aranır)`;
  const voices = voice.englishVoices().map((item) => {
    const option = document.createElement("option");
    option.value = item.name;
    option.textContent = `${item.name} (${item.lang})`;
    return option;
  });
  select.replaceChildren(auto, ...voices);
  select.value = voices.some((option) => option.value === voice.chosenVoice())
    ? voice.chosenVoice()
    : "";
  select.disabled = voices.length === 0;
}

$("prefs-rate").addEventListener("change", (event) => {
  saveLocalSetting("talkbuddy-rate", event.target.value);
  saved("prefs-saved");
});

$("prefs-voice").addEventListener("change", (event) => {
  voice.chooseVoice(event.target.value);
  saved("prefs-saved");
});

$("prefs-voice-test").addEventListener("click", () => {
  voice.stopSpeaking();
  voice.speak("Hi! I'm your English partner. Let's talk.", me.partner, Number($("prefs-rate").value));
});

// Uygulama ayarları
const NOTICE_LABELS = {
  daily: "Günlük hedef hatırlatması",
  review: "Kelime tekrar hatırlatması",
  weekly: "Haftalık özet",
  badge: "Yeni rozetler",
  monthly: "Aylık konuşma değerlendirmesi",
};
const THEMES = [
  ["system", "Sistem"],
  ["light", "Açık"],
  ["dark", "Koyu"],
];
const TEXT_SIZES = [
  ["normal", "Normal"],
  ["large", "Büyük"],
];

// Görünüm, yazı boyutu, ses ve hız yalnızca bu cihazda saklanır.
function localSetting(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function saveLocalSetting(key, value) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {}
}

function applyTheme(theme) {
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}

function applyTextSize(size) {
  if (size === "large") document.documentElement.dataset.text = "large";
  else delete document.documentElement.dataset.text;
}

function showSettings() {
  $("settings-notifications").replaceChildren(
    ...Object.entries(NOTICE_LABELS).map(([kind, label]) => {
      const row = document.createElement("label");
      row.className = "toggle";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = me.notification_prefs[kind];
      input.addEventListener("change", async () => {
        me = await api.saveSettings({ notifications: { [kind]: input.checked } });
        saved("settings-saved");
      });
      row.append(input, label);
      return row;
    }),
  );
  renderOptions($("settings-theme"), THEMES, localSetting("talkbuddy-theme") ?? "system", (theme) => {
    saveLocalSetting("talkbuddy-theme", theme === "system" ? null : theme);
    applyTheme(theme);
    showSettings();
  });
  renderOptions($("settings-text"), TEXT_SIZES, localSetting("talkbuddy-text") ?? "normal", (size) => {
    saveLocalSetting("talkbuddy-text", size === "large" ? size : null);
    applyTextSize(size);
    showSettings();
  });
  $("history-deleted").hidden = true;
  show("settings");
}

$("email-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  const success = form.querySelector(".form-success");
  success.hidden = true;
  submitting(form, async () => {
    const { message } = await api.changeEmail(formData(form));
    form.reset();
    success.textContent = `${message} Bağlantıyı açana kadar eski adresin geçerli kalır.`;
    success.hidden = false;
  });
});

$("password-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  const success = form.querySelector(".form-success");
  success.hidden = true;
  submitting(form, async () => {
    const { message } = await api.changePassword(formData(form));
    form.reset();
    success.textContent = `${message} Diğer cihazlardaki oturumların kapatıldı.`;
    success.hidden = false;
  });
});

// Silme geri alınamaz; ilk dokunuşta onay istenir, ikinci dokunuşta silinir.
$("delete-history").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  if (!button.dataset.confirm) {
    button.dataset.confirm = "1";
    button.textContent = "Emin misin? Silmek için tekrar dokun";
    setTimeout(() => {
      delete button.dataset.confirm;
      button.textContent = "Konuşma geçmişimi sil";
    }, 5000);
    return;
  }
  delete button.dataset.confirm;
  button.textContent = "Konuşma geçmişimi sil";
  const { message } = await api.deleteHistory();
  me = await api.me();
  $("history-deleted").textContent = message;
  $("history-deleted").hidden = false;
});

// Başlangıç: e-postadaki sıfırlama bağlantısıyla gelindiyse yeni şifre ekranı açılır.
// Beklenmeyen hatalar sayfanın üstünde kısa bir uyarı olarak gösterilir.
window.addEventListener("unhandledrejection", (event) => {
  const error = event.reason;
  if (error?.status === 401) return show("login");
  const notice = $("notice");
  notice.classList.remove("success");
  notice.textContent = error?.message ?? "Bir şeyler ters gitti. Tekrar dener misin?";
  notice.hidden = false;
  setTimeout(() => (notice.hidden = true), 5000);
});

drawPartnerCards();
// Açılış: sıfırlama bağlantısı yeni şifre ekranını, e-posta bağlantısı adres onayını açar.
const params = new URLSearchParams(location.search);
resetToken = params.get("reset");
if (resetToken) show("reset");
else if (params.get("email")) confirmEmail(params.get("email"));
else route();

async function confirmEmail(token) {
  history.replaceState(null, "", "/");
  const notice = $("notice");
  try {
    const { message } = await api.confirmEmail(token);
    notice.textContent = message;
    notice.classList.add("success");
  } catch (error) {
    notice.textContent = error.message;
    notice.classList.remove("success");
  }
  notice.hidden = false;
  setTimeout(() => (notice.hidden = true), 6000);
  route();
}
