// Karşılıklı sesli konuşma ekranı: dinle → partnere gönder → sesli cevap → tekrar dinle.
const talk = (() => {
  const STATUS = {
    connecting: "Bağlantı kuruluyor",
    listening: "Dinliyor",
    thinking: "Düşünüyor",
    speaking: "Yanıtlıyor",
    muted: "Mikrofon kapalı",
    typing: "Senin sıran",
    error: "Bir sorun oluştu",
  };

  const $ = (id) => document.getElementById(id);
  const el = {
    status: $("talk-status"),
    bubble: $("talk-bubble"),
    character: $("talk-character"),
    heard: $("talk-heard"),
    toast: $("talk-toast"),
    mute: $("talk-mute"),
    replay: $("talk-replay"),
    language: $("talk-language"),
    speed: $("talk-speed"),
    transcriptToggle: $("talk-transcript-toggle"),
    transcript: $("talk-transcript"),
    textForm: $("talk-text"),
    timer: $("talk-timer"),
    topic: $("talk-topic"),
    help: $("talk-help"),
    menu: $("talk-menu"),
    end: $("talk-end"),
  };

  let profile = null;
  let sessionId = null;
  let lastReply = "";
  let muted = false;
  let turkishMic = false;
  let active = false;
  let onFinish = null;
  let interrupted = false;

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

  // Durum hem yazıyla hem mikrofon halkasının rengiyle gösterilir.
  function setStatus(name) {
    el.status.textContent = STATUS[name];
    el.status.dataset.state = name;
    el.mute.dataset.state = name;
  }

  // Kısa bilgi kutusu; istenirse içinde tek bir işlem düğmesi olur.
  function showToast(text, action, duration = action ? 7000 : 4000) {
    el.toast.replaceChildren(text);
    if (action) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "link";
      button.textContent = action.label;
      button.addEventListener("click", action.run, { once: true });
      el.toast.append(" ", button);
    }
    el.toast.hidden = false;
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(() => (el.toast.hidden = true), duration);
  }

  // Dökümde partnerin sözlerindeki kelimelere dokunulunca dinlenebilir ve kaydedilebilir.
  function addTranscript(role, text) {
    const item = document.createElement("li");
    item.className = `line line-${role}`;
    const who = document.createElement("strong");
    who.textContent = role === "user" ? "Sen" : "Partner";
    item.append(who, " ");
    if (role === "coach") {
      for (const part of text.split(/(\s+)/)) {
        const word = part.replace(/[^A-Za-z'-]/g, "");
        if (!word || part.trim() === "") {
          item.append(part);
          continue;
        }
        const button = document.createElement("button");
        button.type = "button";
        button.className = "word";
        button.textContent = part;
        button.addEventListener("click", () => wordActions(word, text));
        item.append(button);
      }
    } else {
      item.append(text);
    }
    el.transcript.append(item);
  }

  // Kelime sesli okunur, Türkçe anlamı ve örnek cümlesi gösterilir, kaydetme seçeneği sunulur.
  async function wordActions(word, sentence) {
    voice.speak(word, profile.partner, Number(el.speed.value));
    showToast(`"${word}" aranıyor…`);
    let text = `"${word}"`;
    try {
      const info = await api.explainWord(word, sentence);
      const level = info.level ? ` (${info.level})` : "";
      text = `${info.word}${level}: ${info.turkish_meaning}${info.example ? ` · ${info.example}` : ""}`;
    } catch (error) {
      text = `"${word}": ${error.message}`;
    }
    showToast(text, {
      label: "Kelimelerime kaydet",
      run: async () => {
        try {
          const { saved } = await api.saveWord(word);
          showToast(saved ? `"${word}" kelimelerine kaydedildi.` : `"${word}" zaten kelimelerinde var.`);
        } catch (error) {
          showToast(`Kaydedilemedi: ${error.message}`);
        }
      },
    }, 12000);
  }

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
      el.timer.textContent = left ? `Kalan ${mm}:${ss}` : "Süre doldu";
      el.timer.classList.toggle("done", !left);
      if (!left && !warned) {
        warned = true;
        showToast("Süre doldu. İstersen konuşmayı bitirebilir ya da devam edebilirsin.", null, 8000);
      }
    };
    tick();
    timer = setInterval(tick, 1000);
  }

  // Mikrofon düğmesi bir simgedir; durumu yazı yerine etiket ve görünümle gösterilir.
  function setMuted(value) {
    muted = value;
    el.mute.setAttribute("aria-label", muted ? "Mikrofonu aç" : "Mikrofonu kapat");
    el.mute.setAttribute("aria-pressed", String(muted));
  }

  function pauseFor(level) {
    return ["A1", "A2", null, undefined].includes(level) ? 2000 : 1500;
  }

  // Whisper sunucuda açıksa ses kaydedilip sunucuda yazıya çevrilir; değilse tarayıcı tanır.
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

  // Mikrofonu açar; konuşma bitince otomatik olarak partnere gönderir.
  function listen() {
    if (!active) return;
    if (muted || !canListen()) {
      setStatus(muted ? "muted" : "typing");
      character.render(el.character, profile.partner, "idle");
      return;
    }
    setStatus("listening");
    character.render(el.character, profile.partner, "idle");
    el.heard.textContent = "";
    if (serverSpeech()) {
      voice.record({
        pauseMs: pauseFor(profile.level),
        onSpeechStart: () => (el.heard.textContent = "Seni dinliyorum…"),
        onAudio: transcribeAndSend,
        onError: handleMicError,
      });
      return;
    }
    voice.listen({
      lang: turkishMic ? "tr-TR" : "en-US",
      pauseMs: pauseFor(profile.level),
      onPartial: (text) => (el.heard.textContent = text),
      onUtterance: (text, alternatives) => send(text, alternatives),
      onError: handleMicError,
    });
  }

  async function transcribeAndSend(audio) {
    if (!active) return;
    setStatus("thinking");
    el.heard.textContent = "Yazıya çevriliyor…";
    try {
      const { text } = await api.transcribe(audio);
      if (!text.trim()) {
        el.heard.textContent = "Sesini duyamadım. Biraz daha yüksek sesle tekrar dener misin?";
        return setTimeout(listen, 1200);
      }
      send(text.trim());
    } catch (error) {
      setStatus("error");
      el.heard.textContent = error.message;
      setTimeout(listen, 1500);
    }
  }

  function handleMicError(error) {
    if (error === "not-allowed" || error === "service-not-allowed") {
      setStatus("muted");
      el.heard.textContent =
        "Mikrofon izni verilmedi. Adres çubuğundaki kilit simgesinden mikrofona izin verip sayfayı yenile. Bu arada yazarak da devam edebilirsin.";
      el.textForm.hidden = false;
      return;
    }
    if (error === "network") {
      el.heard.textContent = "Ses tanıma servisine ulaşılamadı. Tekrar deneniyor…";
      setTimeout(listen, 1500);
      return;
    }
    setStatus("error");
    el.heard.textContent = "Sesini anlayamadım. Tekrar dener misin?";
    setTimeout(listen, 1200);
  }

  async function respond(reply) {
    sessionId = reply.session_id;
    lastReply = reply.spoken_text;
    el.heard.textContent = "";
    addTranscript("coach", reply.spoken_text);
    el.bubble.textContent = reply.spoken_text;
    el.bubble.hidden = false;

    if (reply.speech_rate === "slower") saveRate(Math.max(0.6, Number(el.speed.value) - 0.15));
    if (reply.speech_rate === "faster") saveRate(Math.min(1.3, Number(el.speed.value) + 0.15));
    if (reply.new_words?.length) showToast(`Kelimelerine eklendi: ${reply.new_words.join(", ")}`);

    await speakReply(reply.spoken_text, reply.expression);
  }

  async function speakReply(text, expression = "neutral") {
    if (!active) return;
    setStatus("speaking");
    if (expression === "laugh") {
      character.render(el.character, profile.partner, "laugh");
      await voice.playLaugh(profile.partner);
    }
    character.render(el.character, profile.partner, "talk");
    interrupted = false;
    const spoke = await voice.speak(text, profile.partner, Number(el.speed.value));
    character.render(el.character, profile.partner, expression === "neutral" ? "idle" : "happy");
    if (!spoke && active && !interrupted) {
      showToast(
        "Ses çalınamadı. Bilgisayarının sesini ve Chrome'da bu sitenin sesinin kapalı olmadığını kontrol et.",
        null,
        15000,
      );
    }
    listen();
  }

  async function send(text, alternatives = []) {
    addTranscript("user", text);
    el.heard.textContent = text;
    setStatus("thinking");
    try {
      await respond(await api.sendMessage(sessionId, text, alternatives));
    } catch (error) {
      setStatus("error");
      el.heard.textContent = error.message;
      setTimeout(listen, 2000);
    }
  }

  // "Türkçe yardım": partner son söylediğini Türkçe açıklar ve örnek bir cevap verir.
  async function askHelp() {
    if (!sessionId || el.status.dataset.state === "thinking") return;
    stopMic();
    voice.stopSpeaking();
    setStatus("thinking");
    el.heard.textContent = "Türkçe açıklama hazırlanıyor…";
    try {
      await respond(await api.help(sessionId));
    } catch (error) {
      setStatus("error");
      el.heard.textContent = error.message;
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
  ) {
    profile = currentProfile;
    onFinish = finished;
    active = true;
    turkishMic = false;
    sessionId = null;
    const lessonTitle = lesson ? profile.suggestion.title : null;
    el.topic.textContent =
      mode === "monthly" ? "Aylık değerlendirme" : lessonTitle ?? topic ?? "Serbest konuşma";
    el.menu.open = false;
    el.transcript.replaceChildren();
    el.transcript.hidden = true;
    el.transcriptToggle.textContent = "Döküm";
    el.bubble.hidden = true;
    setMuted(false);
    el.language.textContent = "Türkçe konuşacağım";
    // Whisper dili kendisi algıladığı için dil düğmesine gerek kalmaz.
    el.language.hidden = serverSpeech();
    el.textForm.hidden = canListen();
    el.heard.textContent = canListen()
      ? ""
      : "Tarayıcın sesli konuşmayı desteklemiyor. Chrome ya da Edge kullanabilirsin; şimdilik yazarak devam et.";
    saveRate(storedRate());
    character.render(el.character, profile.partner, "idle");
    setStatus("connecting");

    await voice.ready();
    try {
      const reply = await api.startSession(topic, minutes, mode, lesson);
      startTimer(minutes ?? (mode === "monthly" ? 15 : null));
      await respond(reply);
    } catch (error) {
      setStatus("error");
      el.heard.textContent = error.message;
    }
  }

  // Konuşma bitince mikrofon ve ses tamamen kapatılır.
  async function end() {
    if (!active) return;
    active = false;
    clearInterval(timer);
    stopMic();
    voice.closeMic();
    voice.stopSpeaking();
    if (!sessionId) return onFinish(null);
    setStatus("thinking");
    try {
      onFinish(await api.endSession(sessionId));
    } catch (error) {
      onFinish(null, error.message);
    }
  }

  function stop() {
    active = false;
    clearInterval(timer);
    stopMic();
    voice.closeMic();
    voice.stopSpeaking();
  }

  // Partner konuşurken karaktere dokunmak sözünü keser ve dinlemeye geçer.
  el.character.addEventListener("click", () => {
    if (el.status.dataset.state !== "speaking") return;
    interrupted = true;
    voice.stopSpeaking();
  });

  el.mute.addEventListener("click", () => {
    setMuted(!muted);
    if (muted) {
      stopMic();
      setStatus("muted");
    } else {
      listen();
    }
  });

  el.help.addEventListener("click", askHelp);

  // Menüden bir seçim yapılınca menü kapanır.
  for (const item of el.menu.querySelectorAll("button.menu-item")) {
    item.addEventListener("click", () => (el.menu.open = false));
  }

  el.replay.addEventListener("click", () => {
    if (!lastReply) return;
    stopMic();
    speakReply(lastReply);
  });

  el.language.addEventListener("click", () => {
    turkishMic = !turkishMic;
    el.language.textContent = turkishMic ? "İngilizce konuşacağım" : "Türkçe konuşacağım";
    if (el.status.dataset.state === "listening") {
      voice.stopListening();
      listen();
    }
  });

  el.speed.addEventListener("change", () => saveRate(Number(el.speed.value)));

  el.transcriptToggle.addEventListener("click", () => {
    el.transcript.hidden = !el.transcript.hidden;
    el.transcriptToggle.textContent = el.transcript.hidden ? "Döküm" : "Dökümü gizle";
  });

  el.textForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const input = el.textForm.elements.text;
    const text = input.value.trim();
    if (!text || !sessionId) return;
    input.value = "";
    stopMic();
    send(text);
  });

  el.end.addEventListener("click", end);
  window.addEventListener("pagehide", stop);

  return { start, stop };
})();
