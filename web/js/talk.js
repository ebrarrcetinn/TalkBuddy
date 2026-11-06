// Konuşma ekranı: sesli konuşma ve yazışma aynı sohbette. Partner konuşunca mikrofon kendiliğinden
// açılır; öğrenci istediği an yazabilir, Türkçe sorabilir ya da partnerin sözünü kesebilir.
const talk = (() => {
  const STATUS = {
    connecting: "Bağlanıyor…",
    listening: "Dinliyor",
    thinking: "Düşünüyor…",
    speaking: "Konuşuyor · sözünü kesmek için dokun",
    muted: "",
    typing: "",
    error: "Bir sorun oluştu",
  };

  const $ = (id) => document.getElementById(id);
  const el = {
    status: $("talk-status"),
    character: $("talk-character"),
    thread: $("talk-thread"),
    toast: $("talk-toast"),
    mute: $("talk-mute"),
    replay: $("talk-replay"),
    speed: $("talk-speed"),
    form: $("talk-text"),
    input: $("talk-text").elements.text,
    timer: $("talk-timer"),
    topic: $("talk-topic"),
    menu: $("talk-menu"),
    back: $("talk-back"),
    end: $("talk-end"),
    sheet: $("talk-sheet"),
    sheetWord: $("sheet-word"),
    sheetLevel: $("sheet-level"),
    sheetMeaning: $("sheet-meaning"),
    sheetExample: $("sheet-example"),
    sheetListen: $("sheet-listen"),
    sheetSave: $("sheet-save"),
    sheetClose: $("sheet-close"),
  };

  let profile = null;
  let sessionId = null;
  let lastReply = "";
  let muted = false;
  let active = false;
  let onFinish = null;
  let onLeave = null;
  let pending = null;
  let warnedTurkishVoice = false;
  let micAsked = false;

  function storedRate() {
    try {
      return Number(localStorage.getItem("talkbuddy-rate")) || 1;
    } catch {
      return 1;
    }
  }

  function saveRate(rate) {
    el.speed.value = rate;
    try {
      localStorage.setItem("talkbuddy-rate", String(rate));
    } catch {}
  }

  function rate() {
    return Number(el.speed.value);
  }

  // Durum üstte yazıyla, mikrofon düğmesinde renkle gösterilir.
  function setStatus(name) {
    el.status.textContent = STATUS[name];
    el.status.dataset.state = name;
    el.mute.dataset.state = name;
    el.character.dataset.state = name === "speaking" ? "talk" : "idle";
  }

  function state() {
    return el.status.dataset.state;
  }

  function showToast(text, duration = 4000) {
    el.toast.textContent = text;
    el.toast.hidden = false;
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(() => (el.toast.hidden = true), duration);
  }

  // Sohbet balonları

  function scrollToEnd() {
    el.thread.scrollTop = el.thread.scrollHeight;
  }

  // Partnerin İngilizce cümlelerindeki her kelimeye dokunulabilir; Türkçe cümleler düz yazılır.
  function appendWords(item, sentence) {
    for (const part of sentence.split(/(\s+)/)) {
      const word = part.replace(/^[^A-Za-z]+|[^A-Za-z]+$/g, "");
      if (!word) {
        item.append(part);
        continue;
      }
      const button = document.createElement("button");
      button.type = "button";
      button.className = "word";
      button.textContent = part;
      button.addEventListener("click", () => openWord(word, sentence));
      item.append(button);
    }
  }

  function addMessage(role, text, newWords = []) {
    const item = document.createElement("li");
    item.className = `bubble bubble-${role}`;
    if (role === "assistant") {
      for (const sentence of text.match(/[^.!?:]+[.!?:]*\s*/g) ?? [text]) {
        if (voice.isTurkish(sentence)) item.append(sentence);
        else appendWords(item, sentence);
      }
    } else {
      item.textContent = text;
    }
    el.thread.append(item);
    const sentences = newWords.filter(isSentence);
    const words = newWords.filter((expression) => !isSentence(expression));
    addSaved("Kelimelerine eklendi", words);
    addSaved("Cümlelerine eklendi", sentences);
    scrollToEnd();
    return item;
  }

  // Sunucudaki vocab.kind ile aynı ayrım: "..." içeren kalıplar ve noktalamayla biten
  // çok kelimeli ifadeler Cümlelerim'e gider.
  function isSentence(expression) {
    const text = expression.trim();
    if (text.includes("...") || text.includes("…")) return true;
    return text.split(/\s+/).length > 1 && /[.?!]$/.test(text);
  }

  function addSaved(label, items) {
    if (!items.length) return;
    const saved = document.createElement("li");
    saved.className = "thread-saved";
    saved.textContent = `${label}: ${items.join(", ")}`;
    el.thread.append(saved);
  }

  // Öğrencinin sözü yazıya çevrilirken ve partner düşünürken sohbette geçici balon görünür.
  function showPending(role, text) {
    clearPending();
    pending = addMessage(role, text);
    pending.classList.add("is-pending");
  }

  function clearPending() {
    pending?.remove();
    pending = null;
  }

  // Kelime kartı: Türkçe anlamı, örnek cümle, dinleme ve kaydetme.
  let sheetWord = "";

  async function openWord(word, sentence) {
    sheetWord = word;
    el.toast.hidden = true;
    el.sheetWord.textContent = word;
    el.sheetLevel.hidden = true;
    el.sheetMeaning.textContent = "Anlamı getiriliyor…";
    el.sheetExample.hidden = true;
    el.sheetSave.disabled = false;
    el.sheetSave.textContent = "Kelimelerime ekle";
    el.sheet.hidden = false;
    try {
      const info = await api.explainWord(word, sentence);
      if (sheetWord !== word) return;
      el.sheetMeaning.textContent = info.turkish_meaning;
      el.sheetLevel.textContent = info.level ?? "";
      el.sheetLevel.hidden = !info.level;
      el.sheetExample.textContent = info.example;
      el.sheetExample.hidden = !info.example;
    } catch (error) {
      if (sheetWord === word) el.sheetMeaning.textContent = error.message;
    }
  }

  el.sheetListen.addEventListener("click", () => voice.speak(sheetWord, profile.partner, 0.85));
  el.sheetClose.addEventListener("click", () => (el.sheet.hidden = true));
  el.sheetSave.addEventListener("click", async () => {
    el.sheetSave.disabled = true;
    try {
      const { saved } = await api.saveWord(sheetWord);
      el.sheetSave.textContent = saved ? "Kelimelerine eklendi" : "Zaten kelimelerinde";
    } catch (error) {
      el.sheetSave.disabled = false;
      el.sheetMeaning.textContent = `Kaydedilemedi: ${error.message}`;
    }
  });

  // Kalan süre: süre dolunca konuşma kesilmez, yalnızca haber verilir.
  let timer = null;

  function startTimer(minutes) {
    clearInterval(timer);
    el.timer.hidden = !minutes;
    if (!minutes) return;
    const endsAt = Date.now() + minutes * 60000;
    let warned = false;
    const tick = () => {
      const left = Math.max(0, Math.round((endsAt - Date.now()) / 1000));
      const mm = String(Math.floor(left / 60)).padStart(2, "0");
      const ss = String(left % 60).padStart(2, "0");
      el.timer.textContent = left ? `${mm}:${ss}` : "Süre doldu";
      el.timer.classList.toggle("done", !left);
      if (!left && !warned) {
        warned = true;
        showToast("Süre doldu. İstersen bitirebilir ya da devam edebilirsin.", 8000);
      }
    };
    tick();
    timer = setInterval(tick, 1000);
  }

  // Mikrofon

  function setMuted(value) {
    muted = value;
    el.mute.setAttribute("aria-label", muted ? "Mikrofonu aç" : "Mikrofonu kapat");
    el.mute.setAttribute("aria-pressed", String(muted));
  }

  function pauseFor(level) {
    return ["A1", "A2", null, undefined].includes(level) ? 2000 : 1500;
  }

  // Whisper sunucuda açıksa ses sunucuda yazıya çevrilir ve Türkçe de tanınır; değilse tarayıcı tanır.
  function serverSpeech() {
    return profile.speech_engine === "whisper" && voice.recordingSupported();
  }

  function canListen() {
    return serverSpeech() || voice.supported();
  }

  function stopMic() {
    voice.stopListening();
    voice.stopRecording();
  }

  // Mikrofonu açar; konuşma bitince partnere gönderir. Öğrenci yazıyorsa mikrofon açılmaz.
  function listen() {
    if (!active) return;
    if (muted || !canListen() || el.input.value.trim()) {
      setStatus(muted || !canListen() ? "muted" : "typing");
      return;
    }
    setStatus("listening");
    if (serverSpeech()) {
      voice.record({
        pauseMs: pauseFor(profile.level),
        onSpeechStart: () => showPending("user", "Seni dinliyorum…"),
        onAudio: transcribeAndSend,
        onError: handleMicError,
      });
      return;
    }
    voice.listen({
      lang: "en-US",
      pauseMs: pauseFor(profile.level),
      onPartial: (text) => showPending("user", text),
      onUtterance: (text, alternatives) => send(text, alternatives),
      onError: handleMicError,
    });
  }

  async function transcribeAndSend(audio) {
    if (!active) return;
    setStatus("thinking");
    showPending("user", "Yazıya çevriliyor…");
    try {
      const { text } = await api.transcribe(audio);
      if (!text.trim()) {
        clearPending();
        return setTimeout(listen, 1200);
      }
      send(text.trim());
    } catch (error) {
      clearPending();
      setStatus("error");
      showToast(error.message);
      setTimeout(listen, 1500);
    }
  }

  // Mikrofon açılamazsa sessizce kapanır; uyarı yalnızca öğrenci konuşmak için düğmeye basınca çıkar.
  function handleMicError(error) {
    clearPending();
    if (["not-allowed", "service-not-allowed", "audio-capture"].includes(error)) {
      setMuted(true);
      setStatus("muted");
      if (micAsked) {
        showToast(
          "Mikrofonuna ulaşılamadı. Mikrofonunu aç ve adres çubuğundaki kilit simgesinden bu siteye izin ver.",
          8000,
        );
      }
      return;
    }
    setTimeout(listen, error === "network" ? 1500 : 1200);
  }

  // Partnerin cevabı

  async function respond(reply) {
    sessionId = reply.session_id;
    lastReply = reply.spoken_text;
    clearPending();
    addMessage("assistant", reply.spoken_text, reply.new_words ?? []);
    if (reply.speech_rate === "slower") saveRate(Math.max(0.6, rate() - 0.15));
    if (reply.speech_rate === "faster") saveRate(Math.min(1.3, rate() + 0.15));
    await speakReply(reply.spoken_text, reply.expression);
  }

  async function speakReply(text, expression = "neutral") {
    if (!active) return;
    setStatus("speaking");
    if (expression === "laugh") await voice.playLaugh(profile.partner);
    await voice.speak(text, profile.partner, rate());
    if (!active) return;
    listen();
  }

  // Partner konuşurken araya girilir: ses durur, öğrenci konuşur ya da yazar.
  function interrupt() {
    if (state() !== "speaking") return false;
    voice.stopSpeaking();
    return true;
  }

  async function send(text, alternatives = [], typed = false) {
    clearPending();
    addMessage("user", text);
    setStatus("thinking");
    showPending("assistant", "…");
    try {
      await respond(await api.sendMessage(sessionId, text, alternatives, typed));
    } catch (error) {
      clearPending();
      setStatus("error");
      showToast(error.message);
      setTimeout(listen, 2000);
    }
  }

  async function start(
    currentProfile,
    finished,
    topic = null,
    minutes = null,
    mode = "practice",
    lesson = null,
    left = null,
  ) {
    profile = currentProfile;
    onFinish = finished;
    onLeave = left;
    active = true;
    sessionId = null;
    lastReply = "";
    micAsked = false;
    const lessonTitle = lesson ? profile.suggestion.title : null;
    el.topic.textContent =
      mode === "monthly" ? "Aylık değerlendirme" : lessonTitle ?? topic ?? "Serbest konuşma";
    el.menu.open = false;
    el.sheet.hidden = true;
    el.toast.hidden = true;
    el.input.value = "";
    el.thread.replaceChildren();
    setMuted(!canListen());
    el.mute.hidden = !canListen();
    saveRate(storedRate());
    character.render(el.character, profile.partner, "idle");
    setStatus("connecting");

    await voice.ready();
    if (!warnedTurkishVoice && !voice.hasTurkishVoice()) {
      warnedTurkishVoice = true;
      showToast(
        "Bilgisayarında Türkçe ses yüklü değil; Türkçe cümleler yanlış okunabilir. Windows'ta Ayarlar → Saat ve dil → Konuşma → Ses ekle bölümünden Türkçe ekleyebilirsin.",
        12000,
      );
    }

    try {
      const today = await api.today();
      if (!active) return;
      // Gün boyu tek sohbet: açık konuşma varsa ona devam edilir, mesajlar tek akışta görünür.
      const open = today.open_session;
      for (const message of today.messages) addMessage(message.role, message.text);
      if (open && open.mode === mode) {
        sessionId = open.id;
        lastReply = [...today.messages].reverse().find((m) => m.role === "assistant")?.text ?? "";
        if (open.topic !== topic || open.lesson !== lesson) el.topic.textContent = "Bugünkü sohbet";
        startTimer(minutes ?? (mode === "monthly" ? 15 : null));
        // Partnerin son sorusu cevapsız kaldıysa onu yeniden sorar; cevap verdikçe sohbet ilerler.
        const unanswered = today.messages.at(-1)?.role === "assistant";
        return unanswered ? speakReply(lastReply) : listen();
      }
      const reply = await api.startSession(topic, minutes, mode, lesson);
      startTimer(minutes ?? (mode === "monthly" ? 15 : null));
      await respond(reply);
    } catch (error) {
      setStatus("error");
      showToast(error.message, 10000);
    }
  }

  function stop() {
    active = false;
    clearInterval(timer);
    clearPending();
    stopMic();
    voice.closeMic();
    voice.stopSpeaking();
  }

  // "Bitir": konuşma kapanır ve özet gösterilir.
  async function end() {
    if (!active) return;
    stop();
    if (!sessionId) return onFinish(null);
    setStatus("thinking");
    try {
      onFinish(await api.endSession(sessionId));
    } catch (error) {
      onFinish(null, error.message);
    }
  }

  // Geri: konuşma açık kalır; aynı gün yeniden girince kaldığı yerden devam eder.
  function leave() {
    stop();
    onLeave?.();
  }

  el.character.addEventListener("click", () => {
    if (interrupt()) listen();
  });

  // Mikrofon düğmesi: partner konuşuyorsa sözünü keser ve dinler; değilse mikrofonu açar/kapatır.
  el.mute.addEventListener("click", () => {
    micAsked = true;
    if (interrupt()) {
      setMuted(false);
      return listen();
    }
    setMuted(!muted);
    if (muted) {
      stopMic();
      clearPending();
      setStatus("muted");
    } else {
      listen();
    }
  });

  // Yazmaya başlamak da araya girmektir: partner susar, mikrofon yazı bitene kadar bekler.
  el.input.addEventListener("input", () => {
    if (!el.input.value.trim()) return;
    interrupt();
    if (state() === "listening") {
      stopMic();
      clearPending();
    }
    if (state() !== "thinking") setStatus("typing");
  });

  el.form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = el.input.value.trim();
    if (!text || !sessionId || state() === "thinking") return;
    el.input.value = "";
    interrupt();
    stopMic();
    send(text, [], true);
  });

  for (const item of el.menu.querySelectorAll("button.menu-item")) {
    item.addEventListener("click", () => (el.menu.open = false));
  }

  el.replay.addEventListener("click", () => {
    if (!lastReply || state() === "thinking") return;
    stopMic();
    clearPending();
    speakReply(lastReply);
  });

  el.speed.addEventListener("change", () => saveRate(rate()));
  el.back.addEventListener("click", leave);
  el.end.addEventListener("click", end);
  window.addEventListener("pagehide", stop);

  return { start, stop };
})();
