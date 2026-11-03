// Backend ile konuşan fonksiyonlar. Oturum, tarayıcının sakladığı çerezle taşınır.
class ApiError extends Error {
  constructor(message, status, fields = {}) {
    super(message);
    this.status = status;
    this.fields = fields;
  }
}

// JSON gövdesi gönderir; Blob verilirse (fotoğraf) olduğu gibi kendi türüyle gönderilir.
async function request(method, path, body) {
  const raw = body instanceof Blob;
  let response;
  try {
    response = await fetch(path, {
      method,
      headers:
        body === undefined ? {} : { "Content-Type": raw ? body.type : "application/json" },
      body: body === undefined || raw ? body : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Sunucuya ulaşılamadı. İnternet bağlantını kontrol et.", 0);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof data.detail === "string" ? data.detail : "Bir şeyler ters gitti. Tekrar dener misin?";
    throw new ApiError(message, response.status, data.fields ?? {});
  }
  return data;
}

// Ses kaydını sunucuya gönderir; cevap { text, language } olur.
async function transcribe(blob) {
  let response;
  try {
    response = await fetch("/api/speech/transcribe", {
      method: "POST",
      headers: { "Content-Type": blob.type || "application/octet-stream" },
      body: blob,
    });
  } catch {
    throw new ApiError("Sunucuya ulaşılamadı. İnternet bağlantını kontrol et.", 0);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(data.detail ?? "Sesin yazıya çevrilemedi.", response.status);
  return data;
}

const api = {
  transcribe,
  me: () => request("GET", "/api/me"),
  register: (form) => request("POST", "/api/auth/register", form),
  login: (form) => request("POST", "/api/auth/login", form),
  logout: () => request("POST", "/api/auth/logout"),
  forgot: (email) => request("POST", "/api/auth/forgot", { email }),
  reset: (token, password, password_confirm) =>
    request("POST", "/api/auth/reset", { token, password, password_confirm }),

  ageGroups: () => request("GET", "/api/age-groups"),
  interests: () => request("GET", "/api/interests"),
  goals: () => request("GET", "/api/goals"),
  setGoal: (goal) => request("PUT", "/api/me/goal", { goal }),
  setName: (form) => request("PUT", "/api/me/name", form),
  savePhoto: (blob) => request("PUT", "/api/me/photo", blob),
  deletePhoto: () => request("DELETE", "/api/me/photo"),
  setAgeGroup: (age_group) => request("PUT", "/api/me/age-group", { age_group }),
  setLevel: (level) => request("PUT", "/api/me/level", { level }),
  setPartner: (partner) => request("PUT", "/api/me/partner", { partner }),
  setInterests: (interests) => request("PUT", "/api/me/interests", { interests }),
  changePassword: (form) => request("PUT", "/api/me/password", form),
  deleteHistory: () => request("DELETE", "/api/me/history"),

  assessment: () => request("GET", "/api/assessment"),
  submitSection: (index, selected) => request("POST", `/api/assessment/sections/${index}`, { selected }),
  assessmentResult: () => request("GET", "/api/assessment/result"),

  startSession: (topic, minutes, mode = "practice", lesson = null) =>
    request("POST", "/api/sessions", {
      topic: topic ?? null,
      minutes: minutes ?? null,
      mode,
      lesson,
    }),
  help: (sessionId) => request("POST", `/api/sessions/${sessionId}/help`),
  snoozeReview: () => request("POST", "/api/me/review/snooze"),
  changeEmail: (form) => request("PUT", "/api/me/email", form),
  confirmEmail: (token) => request("POST", "/api/auth/email/confirm", { token }),
  explainWord: (word, sentence) => request("POST", "/api/words/explain", { word, sentence }),
  sendMessage: (sessionId, text, alternatives = []) =>
    request("POST", `/api/sessions/${sessionId}/messages`, { text, alternatives }),
  endSession: (sessionId) => request("POST", `/api/sessions/${sessionId}/end`),

  vocabulary: () => request("GET", "/api/me/vocabulary"),
  progress: () => request("GET", "/api/me/progress"),
  notifications: () => request("GET", "/api/me/notifications"),
  notificationsSeen: () => request("POST", "/api/me/notifications/seen"),
  saveSettings: (settings) => request("PUT", "/api/me/settings", settings),
  saveWord: (expression) => request("POST", "/api/me/vocabulary", { expression }),
};
