// Ses: tarayıcının konuşma tanıma (mikrofon → yazı) ve seslendirme (yazı → ses) özellikleri.
const voice = (() => {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const synth = window.speechSynthesis;

  // Türkçe sesler de adlarıyla ayrılır: Emel, Seda, Filiz kadın; Ahmet, Tolga erkek.
  const FEMALE = ["female", "woman", "aria", "jenny", "zira", "samantha", "victoria", "karen", "susan", "hazel", "libby", "sonia", "michelle", "emma", "ava", "serena", "us english", "emel", "seda", "filiz", "yelda"];
  const MALE = ["male", "man", "guy", "davis", "david", "mark", "daniel", "george", "ryan", "alex", "fred", "james", "christopher", "eric", "andrew", "brian", "ahmet", "tolga"];
  // Türkçe harf içeren ya da Türkçede çok geçen kelimeler; Türkçe harfsiz cümleler de tanınsın.
  const TURKISH = /[çğıöşüÇĞİÖŞÜ]|^(bu|ve|bir|için|ne|nasıl|evet|hayır|kelime|anlamı|demek|de|da|mi|mu|ben|sen|biz|siz|var|yok|ama|yani|tamam|sonra|gibi|iyi|bunu|sana|bana|olarak|diye|dersin|denir|istersen|haydi|hadi|harika|aynen|deriz|mesela|tabii)$/i;

  let recognition = null;
  let listening = false;
  let silenceTimer = null;
  let heard = "";
  let alternatives = [];
  let handlers = {};
  let pauseMs = 1800;

  function supported() {
    return Boolean(Recognition && synth);
  }

  // Dinlemeyi başlatır. Konuşma bitince (sessizlik süresi dolunca) onUtterance(metin, alternatifler)
  // çağrılır. Alternatifler, tanıma servisinin aynı söz için önerdiği diğer yazımlardır.
  function listen(options) {
    handlers = options;
    pauseMs = options.pauseMs ?? 1800;
    heard = "";
    alternatives = [];
    let committed = "";
    listening = true;
    recognition = new Recognition();
    recognition.lang = options.lang;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 3;

    recognition.onresult = (event) => {
      let finalText = "";
      let interim = "";
      const others = ["", ""];
      for (const result of event.results) {
        if (result.isFinal) {
          finalText += `${result[0].transcript} `;
          others.forEach((_, k) => (others[k] += `${(result[k + 1] ?? result[0]).transcript} `));
        } else {
          interim += result[0].transcript;
        }
      }
      heard = committed + finalText;
      alternatives = others.map((text) => (committed + text).trim());
      handlers.onPartial?.((heard + " " + interim).trim());
      clearTimeout(silenceTimer);
      silenceTimer = setTimeout(finish, pauseMs);
    };

    recognition.onerror = (event) => {
      if (event.error === "no-speech" || event.error === "aborted") return;
      listening = false;
      handlers.onError?.(event.error);
    };

    // Tarayıcı kendi kendine dinlemeyi bitirirse yeniden başlar; o ana kadar duyulanlar korunur.
    recognition.onend = () => {
      if (!listening) return;
      committed = heard;
      try {
        recognition.start();
      } catch {
        listening = false;
      }
    };

    recognition.start();
  }

  function finish() {
    const text = heard.trim();
    if (!text) return;
    // Yalnızca büyük/küçük harfle ayrılan tahminler aynı sayılır.
    const seen = new Set([text.toLowerCase()]);
    const others = alternatives.filter((item) => {
      const key = item.toLowerCase();
      if (!item || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    stopListening();
    handlers.onUtterance?.(text, others);
  }

  function stopListening() {
    listening = false;
    clearTimeout(silenceTimer);
    if (recognition) {
      recognition.onend = null;
      recognition.abort();
      recognition = null;
    }
  }

  // İsimde kelime olarak geçiyor mu bakar ("female" içindeki "male" sayılmaz).
  function named(voiceItem, words) {
    const name = voiceItem.name.toLowerCase();
    return words.some((word) => new RegExp(`\\b${word}\\b`).test(name));
  }

  // Sunucu (Whisper) tanıması için mikrofon kaydı. Mikrofon sesinin şiddeti izlenir: konuşma
  // başlayınca kayıt tutulur, belirlenen süre sessiz kalınca kayıt biter ve onAudio(ses) çağrılır.
  let stream = null;
  let audioContext = null;
  let analyser = null;
  let monitor = null;
  let recorder = null;

  function recordingSupported() {
    return Boolean(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
  }

  async function openMic() {
    if (stream) return;
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    audioContext = new AudioContext();
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 1024;
    audioContext.createMediaStreamSource(stream).connect(analyser);
  }

  // Mikrofon tamamen kapanır; tarayıcıdaki mikrofon simgesi de söner.
  function closeMic() {
    stopRecording();
    stream?.getTracks().forEach((track) => track.stop());
    audioContext?.close();
    stream = null;
    audioContext = null;
  }

  function loudness() {
    const samples = new Float32Array(analyser.fftSize);
    analyser.getFloatTimeDomainData(samples);
    let sum = 0;
    for (const value of samples) sum += value * value;
    return Math.sqrt(sum / samples.length);
  }

  async function record(options) {
    try {
      await openMic();
    } catch (error) {
      options.onError?.(error.name === "NotAllowedError" ? "not-allowed" : "audio-capture");
      return;
    }
    stopRecording();
    const chunks = [];
    const type = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "";
    recorder = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
    recorder.ondataavailable = (event) => event.data.size && chunks.push(event.data);
    recorder.onstop = () => {
      if (speaking) options.onAudio(new Blob(chunks, { type: recorder.mimeType }));
    };
    recorder.start(250);

    // Ortam gürültüsü sessizken ölçülür; konuşma ondan belirgin şekilde yüksek olmalıdır.
    let noise = null;
    let speaking = false;
    let loudTicks = 0;
    let lastVoice = 0;
    const started = Date.now();
    monitor = setInterval(() => {
      const now = Date.now();
      const level = loudness();
      if (!speaking) noise = noise === null ? level : noise * 0.95 + level * 0.05;
      const threshold = Math.max(0.012, noise * 2.5);
      loudTicks = level > threshold ? loudTicks + 1 : 0;
      // Kısa bir tıkırtı konuşma sayılmaz; iki ölçüm (0,2 sn) üst üste yüksek olmalı.
      if (loudTicks >= 2) {
        lastVoice = now;
        if (!speaking) {
          speaking = true;
          options.onSpeechStart?.();
        }
      }
      if (speaking && (now - lastVoice > options.pauseMs || now - started > 45000)) {
        clearInterval(monitor);
        recorder.stop();
      } else if (!speaking && now - started > 60000) {
        // Bir dakika hiç konuşulmazsa boş kayıt atılır ve dinleme baştan başlar.
        record(options);
      }
    }, 100);
  }

  // Kaydı gönderilmeden durdurur (ör. mikrofon kapatıldığında).
  function stopRecording() {
    clearInterval(monitor);
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = null;
      recorder.stop();
    }
    recorder = null;
  }

  // Önce doğru cinsiyette, bilgisayarda kurulu ses aranır (Windows'ta Microsoft Zira, David gibi);
  // kurulu sesler internete bağlı olmadan ve gecikmesiz çalışır.
  // Kullanıcının bu cihazda seçtiği İngilizce ses; seçilmemişse partnere uygun ses aranır.
  const VOICE_KEY = "talkbuddy-voice";

  function chosenVoice() {
    try {
      return localStorage.getItem(VOICE_KEY) || "";
    } catch {
      return "";
    }
  }

  function chooseVoice(name) {
    try {
      if (name) localStorage.setItem(VOICE_KEY, name);
      else localStorage.removeItem(VOICE_KEY);
    } catch {}
  }

  function englishVoices() {
    return synth ? synth.getVoices().filter((v) => v.lang.toLowerCase().startsWith("en")) : [];
  }

  // Doğal (Natural, Online, Google) sesler Türkçe harfleri ve vurguyu çok daha iyi okur.
  function natural(voiceItem) {
    return /natural|online|google/i.test(voiceItem.name);
  }

  function pickVoice(lang, persona) {
    const voices = synth.getVoices().filter((v) => v.lang.toLowerCase().startsWith(lang));
    const chosen = lang === "en" && voices.find((v) => v.name === chosenVoice());
    if (chosen) return chosen;
    const wanted = persona === "Male_Coach" ? MALE : FEMALE;
    const other = persona === "Male_Coach" ? FEMALE : MALE;
    const gendered = voices.filter((v) => named(v, wanted) && !named(v, other));
    // İngilizcede gecikmesiz yerel ses, Türkçede doğru telaffuz için doğal ses önce gelir.
    const preferred = lang === "tr" ? natural : (v) => v.localService;
    return (
      gendered.find(preferred) ??
      gendered[0] ??
      voices.find(preferred) ??
      voices[0] ??
      null
    );
  }

  // Bu cihazda Türkçe okuyabilen bir ses var mı? Yoksa Türkçe cümleler yanlış okunur.
  function hasTurkishVoice() {
    return Boolean(synth?.getVoices().some((v) => v.lang.toLowerCase().startsWith("tr")));
  }

  // Cümle Türkçe mi? Tek bir Türkçe isim ("Ayşe") cümleyi Türkçe yapmasın diye kelimelerin oranına bakılır.
  function isTurkish(sentence) {
    const words = sentence
      .split(/\s+/)
      .map((word) => word.replace(/[^\p{L}']/gu, ""))
      .filter(Boolean);
    const turkish = words.filter((word) => TURKISH.test(word)).length;
    if (words.length === 1) return turkish === 1;
    return turkish >= 2 && turkish / words.length >= 0.3;
  }

  // Her yeni konuşma ya da susturma bir öncekini geçersiz kılar, kalan cümleler okunmaz.
  let generation = 0;
  let finishCurrent = null;
  // Chrome, referansı kalmayan konuşma nesnesini silip bitiş olayını hiç göndermeyebilir.
  const alive = new Set();

  // Metni cümle cümle okur. Promise, en az bir cümle gerçekten seslendirildiyse true döner.
  function speak(text, persona, rate) {
    if (!synth) return Promise.resolve(false);
    stopSpeaking();
    const turn = generation;
    // İki nokta da cümle sınırı sayılır: "Şöyle diyebilirsin: Istanbul is crowded." iki dilde okunur.
    const sentences = text.match(/[^.!?:]+[.!?:]*/g) ?? [text];
    let spoke = false;

    return new Promise((resolve) => {
      finishCurrent = () => resolve(spoke);
      let index = 0;

      const next = () => {
        if (turn !== generation) return;
        if (index >= sentences.length) {
          finishCurrent = null;
          return resolve(spoke);
        }
        const sentence = sentences[index++].trim();
        if (!sentence) return next();

        const turkish = isTurkish(sentence);
        const utterance = new SpeechSynthesisUtterance(sentence);
        const chosen = pickVoice(turkish ? "tr" : "en", persona);
        if (chosen) utterance.voice = chosen;
        utterance.lang = turkish ? "tr-TR" : "en-US";
        utterance.rate = rate;
        // Uygun cinsiyette ses bulunamazsa ton farkıyla ayrım yapılır.
        const gendered = chosen && named(chosen, persona === "Male_Coach" ? MALE : FEMALE);
        utterance.pitch = gendered ? 1 : persona === "Male_Coach" ? 0.8 : 1.2;

        let started = false;
        let finished = false;
        const done = () => {
          if (finished) return;
          finished = true;
          clearTimeout(watchdog);
          alive.delete(utterance);
          next();
        };
        utterance.onstart = () => {
          started = true;
          spoke = true;
        };
        utterance.onend = done;
        utterance.onerror = done;
        // Ses birkaç saniye içinde başlamazsa takılı kalınmaz: hiç ses çıkmadıysa konuşma bırakılır,
        // çıktıysa yalnızca bu cümle atlanır.
        const watchdog = setTimeout(() => {
          if (started) return;
          if (!spoke) return stopSpeaking();
          synth.cancel();
          setTimeout(done, 80);
        }, 3000);

        alive.add(utterance);
        synth.resume();
        synth.speak(utterance);
      };

      // cancel() çağrısından hemen sonraki konuşmayı Chrome sessizce yutabilir; kısa bir ara verilir.
      setTimeout(next, 80);
    });
  }

  // Bazı tarayıcılar iptalde olay göndermediği için bekleyen konuşma burada bitirilir.
  function stopSpeaking() {
    generation += 1;
    finishCurrent?.();
    finishCurrent = null;
    alive.clear();
    synth?.cancel();
  }

  // Sesler bazı tarayıcılarda geç yüklenir; ilk konuşmadan önce hazır olmalarını bekler.
  function ready() {
    if (!synth || synth.getVoices().length) return Promise.resolve();
    return new Promise((resolve) => {
      synth.onvoiceschanged = () => resolve();
      setTimeout(resolve, 1500);
    });
  }

  function playLaugh(persona) {
    const who = persona === "Male_Coach" ? "male" : "female";
    const audio = new Audio(`/static/sounds/laugh-${who}.mp3`);
    return audio.play().then(
      () => new Promise((resolve) => (audio.onended = resolve)),
      () => undefined,
    );
  }

  return {
    supported,
    listen,
    stopListening,
    recordingSupported,
    record,
    stopRecording,
    closeMic,
    speak,
    stopSpeaking,
    ready,
    playLaugh,
    englishVoices,
    hasTurkishVoice,
    isTurkish,
    chosenVoice,
    chooseVoice,
  };
})();
