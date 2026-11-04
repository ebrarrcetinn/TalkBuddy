TalkBuddy

English · Türkçe

English

TalkBuddy is a voice-first web app that helps Turkish speakers practise speaking English. The learner talks out loud with a conversation partner, gets short and gentle corrections, saves new words and meets them again in later conversations. The partner speaks English at the learner's level and switches to Turkish only when the learner needs help. All interface text is in Turkish.

How it works
Sign up or log in. On a computer the login page has two columns; on a phone it is a single card.
Setup, one question per screen ("Devam et" slides to the next one): age group → English level (A1–C2, or "Seviyemi bilmiyorum" for the word assessment) → interests (up to 10 of 26, can be skipped) → learning goal → partner (female or male). Each step is saved, so a learner who leaves continues where they stopped. Finished setup is never shown again.
First conversation: short and easy for the chosen level, followed by a summary.
Home screen: one suggested conversation for today, words due for review and level plan progress.
Features

Speaking

The browser records until the learner pauses; the server transcribes the audio with Whisper (English and Turkish are detected automatically) and the partner answers aloud with a female or male voice. Pauses are longer for A1–A2, and tapping the partner interrupts it.
The learner can speak Turkish at any time without pressing a button ("…demek istiyorum", "Bunu nasıl söylerim?"). The partner replies with one short Turkish sentence, the English sentence the learner wanted, and an English question that lets them use it.
Speech recognition mistakes are not counted as language mistakes.
Tapping a word in the transcript shows its Turkish meaning and an example sentence, and can save it.

Learning

Word assessment: 5 sections (A1–C1) of 30 shuffled words from the Oxford 5000. A level passes at 29/30 (95%, not rounded). The suggestion is the highest level passed without a gap from A1.
Level plan: each level's word list forms a plan, and every conversation brings in a few new plan words.
Starter path for A1–A2: eight short guided conversations (introductions, daily routine, likes, family, café, weekend, town, plans). B1 and above get topics from their interests.
Vocabulary with spaced repetition (1, 3, 7, 14 and 30 days), filters for due, learning and mastered words, and audio for every word.
An optional monthly speaking review that can be postponed.

Progress and motivation

Streak, daily goal (5, 10, 15 or 20 minutes) and badges, counted in Turkish local time.
The "Gelişimim" screen is built only from saved records: today against the goal, a 7-day chart, total speaking time, sessions, word and review counts, level plan coverage, most corrected structures, monthly reviews, badges and a few personal suggestions. New learners see a short welcome instead of empty charts.
In-app notifications (daily goal, words due, weekly summary, monthly review, new badge); each type can be turned off.

Account and settings

Four tabs: Konuşma (today's conversation), Kelimelerim (words), Gelişimim (progress) and Profil (account and settings).
Profile: photo, name, email and level, with personal details, password change, learning preferences (level, partner, daily goal, interests, partner voice and speaking speed) and app settings (notifications, light/dark/system theme, larger text, history deletion, logout).
Password reset by email; email changes are confirmed by email.
Privacy and security
Passwords are hashed with scrypt; sessions use an httpOnly cookie.
Each user can only read their own data. Profile photos are only shown to their owner.
Raw audio is processed in memory and never stored; only the transcribed text is saved.
The API key is kept in .env on the server and never reaches the browser.
Tech stack
Backend: Python 3.11+, FastAPI, SQLite
Conversation partner: Anthropic API; replies are JSON, validated by the backend
Speech recognition: faster-whisper (runs locally on the server)
Frontend: plain HTML, CSS and JavaScript with no build step; speech output uses the browser's own voices
Tests and linting: pytest, Ruff
Project layout
app/
  main.py        FastAPI routes
  config.py      settings read from .env
  accounts.py    sign-up, login, setup steps, profile
  auth.py        password hashing, tokens, email
  assessment.py  word assessment sections and scoring
  speech.py      speech-to-text with Whisper
  llm.py         Anthropic API client
  coach.py       prompt assembly and JSON parsing
  schemas.py     shape of the partner's replies
  tutor.py       conversation flow and learner memory
  level.py       level estimate
  vocab.py       spaced repetition
  wordlist.py    word list loading
  plan.py        level plan and new word suggestions
  path.py        starter path and today's conversation
  progress.py    streak, daily goal, badges, notifications
  report.py      session summary
  db.py          SQLite storage
  prompts/       partner instructions
web/             Turkish single-page interface
tests/           pytest tests (no real API calls)
data/            word list (not in the repository)
Setup

Requires Python 3.11 or newer.

bash
python -m venv .venv
.venv\Scripts\activate           # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
copy .env.example .env           # macOS/Linux: cp .env.example .env

Add your ANTHROPIC_API_KEY to .env. Other settings in .env:

Setting	Purpose
WHISPER_MODEL	tiny, base, small (default) or medium. Larger is more accurate but slower. off uses the browser's own recognition.
DATABASE_PATH	SQLite file, talkbuddy.db by default
SMTP_*, MAIL_FROM	Email for password reset. If empty, reset links are printed in the server terminal.
COOKIE_SECURE	Set to true when the site runs over HTTPS

The Whisper model is downloaded on first start and cached. The server terminal shows how long each step takes ("Ses 1.2 sn'de yazıya çevrildi", "Partnerin cevabı 2.4 sn sürdü"); if transcription is slow, use WHISPER_MODEL=base.

Run
bash
uvicorn app.main:build_default_app --factory --env-file .env --reload --port 8080

Open http://localhost:8080 in Chrome or Edge.

Test
bash
pytest
ruff check .
Word list

Word levels come from the Oxford 5000 (Oxford University Press), which covers A1–C1. The list is not openly licensed, so it is not in this repository. To use it, place it at data/oxford5000.csv with the columns word,pos,level.

Without this file the app still runs: learners choose their level themselves and the word assessment is hidden. Permission from Oxford University Press is needed before the list is used in a public release. The 95% threshold is a rule of this app, not an official CEFR standard.

Türkçe

TalkBuddy, İngilizce konuşmayı geliştirmek isteyen Türkler için hazırlanmış, ses odaklı bir web uygulamasıdır. Öğrenci bir konuşma partneriyle sesli konuşur, kısa ve nazik düzeltmeler alır, yeni kelimeleri kaydeder ve bunlarla sonraki konuşmalarda yeniden karşılaşır. Partner öğrencinin seviyesinde İngilizce konuşur, yalnızca öğrenci yardıma ihtiyaç duyduğunda Türkçeye geçer. Arayüzün tamamı Türkçedir.

Nasıl çalışır?
Kayıt ol ya da giriş yap. Bilgisayarda giriş sayfası iki sütunlu, telefonda tek kart olarak görünür.
Her ekranda tek soru ile kurulum ("Devam et" ile bir sonrakine kayar): yaş grubu → İngilizce seviyesi (A1–C2 ya da kelime testi için "Seviyemi bilmiyorum") → ilgi alanları (26 alandan en fazla 10, atlanabilir) → öğrenme amacı → partner (kadın ya da erkek). Her adım kaydedilir; yarıda bırakan öğrenci kaldığı yerden devam eder. Tamamlanan kurulum bir daha gösterilmez.
İlk konuşma: seçilen seviyeye göre kısa ve kolay bir konuşma, ardından özet.
Ana ekran: günün önerilen konuşması, tekrar zamanı gelen kelimeler ve seviye planındaki ilerleme.
Özellikler

Konuşma

Tarayıcı öğrenci durana kadar sesi kaydeder; sunucu sesi Whisper ile yazıya çevirir (İngilizce ve Türkçe otomatik algılanır) ve partner kadın ya da erkek sesiyle sesli cevap verir. A1–A2 seviyesinde bekleme süreleri daha uzundur; partnere dokunmak onun sözünü keser.
Öğrenci hiçbir düğmeye basmadan istediği an Türkçe konuşabilir ("…demek istiyorum", "Bunu nasıl söylerim?"). Partner kısa bir Türkçe cümle, öğrencinin söylemek istediği İngilizce cümle ve onu kullanabileceği İngilizce bir soru ile cevap verir.
Ses tanıma hataları dil hatası sayılmaz.
Konuşma metnindeki bir kelimeye dokununca Türkçe anlamı ve örnek cümlesi görünür; kelime kaydedilebilir.

Öğrenme

Kelime testi: Oxford 5000 listesinden alınan, karışık sıralı 30'ar kelimelik 5 bölüm (A1–C1). Bir seviye 29/30 (yuvarlamadan %95) ile geçilir. Öneri, A1'den başlayarak arada boşluk olmadan geçilen en yüksek seviyedir.
Seviye planı: her seviyenin kelime listesi bir plan oluşturur ve her konuşmada plandan birkaç yeni kelime kullanılır.
A1–A2 için başlangıç yolu: sekiz kısa, yönlendirmeli konuşma (tanışma, günlük rutin, sevdiklerin, aile, kafe, hafta sonu, şehir, planlar). B1 ve üstü konuları ilgi alanlarından alır.
Aralıklı tekrar ile kelime çalışması (1, 3, 7, 14 ve 30 gün); tekrar zamanı gelen, öğrenilen ve öğrenilmiş kelimeler için filtreler; her kelime dinlenebilir.
Ertelenebilen, isteğe bağlı aylık konuşma değerlendirmesi.

Gelişim ve motivasyon

Seri, günlük hedef (5, 10, 15 ya da 20 dakika) ve rozetler; Türkiye saatine göre hesaplanır.
"Gelişimim" ekranı yalnızca kayıtlı verilerden oluşur: bugünün hedefe göre durumu, 7 günlük grafik, toplam konuşma süresi, konuşma sayısı, kelime ve tekrar sayıları, seviye planı, en sık düzeltilen yapılar, aylık değerlendirmeler, rozetler ve birkaç kişisel öneri. Yeni öğrenciler boş grafikler yerine kısa bir karşılama görür.
Uygulama içi bildirimler (günlük hedef, tekrar zamanı gelen kelimeler, haftalık özet, aylık değerlendirme, yeni rozet); her tür ayrı ayrı kapatılabilir.

Hesap ve ayarlar

Dört sekme: Konuşma (günün konuşması), Kelimelerim, Gelişimim ve Profil (hesap ve ayarlar).
Profil: fotoğraf, ad, e-posta ve seviye; kişisel bilgiler, şifre değiştirme, öğrenme tercihleri (seviye, partner, günlük hedef, ilgi alanları, partner sesi ve konuşma hızı) ve uygulama ayarları (bildirimler, açık/koyu/sistem teması, büyük yazı, geçmişi silme, çıkış).
E-posta ile şifre sıfırlama; e-posta değişikliği e-posta ile onaylanır.
Gizlilik ve güvenlik
Şifreler scrypt ile özetlenerek saklanır; oturumlar httpOnly çerez ile tutulur.
Her kullanıcı yalnızca kendi verisini görebilir. Profil fotoğrafını yalnızca sahibi görür.
Ham ses bellekte işlenir ve hiçbir zaman kaydedilmez; yalnızca yazıya çevrilmiş metin saklanır.
API anahtarı sunucudaki .env dosyasında durur, tarayıcıya hiçbir zaman gönderilmez.
Kullanılan teknolojiler
Sunucu: Python 3.11+, FastAPI, SQLite
Konuşma partneri: Anthropic API; cevaplar JSON olarak gelir ve sunucu tarafından doğrulanır
Ses tanıma: faster-whisper (sunucuda yerel olarak çalışır)
Arayüz: derleme adımı olmayan düz HTML, CSS ve JavaScript; sesli okuma tarayıcının kendi seslerini kullanır
Test ve kod denetimi: pytest, Ruff
Klasör yapısı

Klasör yapısı için yukarıdaki Project layout bölümüne bakın.

Kurulum

Python 3.11 veya üstü gerekir.

bash
python -m venv .venv
.venv\Scripts\activate           # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
copy .env.example .env           # macOS/Linux: cp .env.example .env

.env dosyasına kendi ANTHROPIC_API_KEY değerini yaz. .env içindeki diğer ayarlar:

Ayar	Görevi
WHISPER_MODEL	tiny, base, small (varsayılan) ya da medium. Büyüdükçe daha doğru ama daha yavaş. off yazılırsa tarayıcının kendi ses tanıması kullanılır.
DATABASE_PATH	SQLite dosyası, varsayılan talkbuddy.db
SMTP_*, MAIL_FROM	Şifre sıfırlama e-postası. Boş kalırsa sıfırlama bağlantısı sunucu terminaline yazılır.
COOKIE_SECURE	Site HTTPS üzerinden yayınlandığında true yapılır

Whisper modeli ilk açılışta indirilir ve saklanır. Sunucu terminali her adımın ne kadar sürdüğünü yazar ("Ses 1.2 sn'de yazıya çevrildi", "Partnerin cevabı 2.4 sn sürdü"); ses tanıma yavaşsa WHISPER_MODEL=base kullan.

Çalıştırma
bash
uvicorn app.main:build_default_app --factory --env-file .env --reload --port 8080

Chrome veya Edge'de http://localhost:8080 adresini aç.

Test
bash
pytest
ruff check .
Kelime listesi

Kelime seviyeleri, A1–C1 aralığını kapsayan Oxford 5000 listesinden (Oxford University Press) gelir. Liste açık lisanslı olmadığı için bu depoda yer almaz. Kullanmak için word,pos,level sütunlarıyla data/oxford5000.csv konumuna koyulmalıdır.

Bu dosya olmadan da uygulama çalışır: öğrenciler seviyesini kendisi seçer ve kelime testi gizlenir. Liste herkese açık bir sürümde kullanılmadan önce Oxford University Press'ten izin alınmalıdır. %95 eşiği bu uygulamanın kuralıdır, resmî bir CEFR standardı değildir.
