# TalkBuddy

[English](#english) | [Türkçe](#türkçe)

## English

TalkBuddy is a web app for Turkish speakers who want to practise speaking English. You chat with a
conversation partner by voice or by typing. It answers at your level, corrects you briefly, and
keeps the words and sentence patterns you didn't know. The interface is in Turkish.

### Features

**Conversation**

- Speaking and typing share one chat screen. Speech is transcribed on the server with
  faster-whisper, and both English and Turkish are recognised.
- You can switch to Turkish whenever you get stuck ("Bunu nasıl söylerim?"). The partner gives you
  the English sentence and carries on. Turkish sentences are read with a Turkish voice.
- Questions in the middle of the conversation ("Doğru mu söyledim?", "Bu ne demek?") are answered
  first, then the partner goes back to the topic.
- You can interrupt the partner by talking, typing or tapping its picture.
- The whole day is one conversation: leave and come back the same day to continue where you left off.

**Words and sentences**

- Tap any English word in the partner's messages to see its Turkish meaning and save it.
- Saying "Bu kelimeyi bilmiyorum" or "Bu kalıbı bilmiyorum" saves it too.
- Saying or typing "Bu cümleyi ekle" saves the partner's last English sentence.
- Words go to **Kelimelerim**. Sentence patterns ("I'm looking forward to ...") and sentences you
  didn't know how to say go to **Cümlelerim**. Any entry can be removed.
- Saved items come back in later conversations with spaced repetition (1, 3, 7, 14, 30 days).

**Learning path and progress**

- Step-by-step setup: age group, level (A1–C2, or a word assessment), interests, learning goal and
  partner (female or male). Each step is saved.
- Word assessment based on the Oxford 5000: five levels of 30 words, a level passes at 29/30.
- Guided starter conversations for A1–A2; topics from your interests for B1 and above.
- Streak, daily goal, badges and a progress screen built only from your own sessions.
- Profile with photo, password and email change, learning preferences, light and dark theme.

**Privacy**

- Recordings are never stored, only the transcribed text.
- Passwords are hashed and each user can only see their own data.

### Tech

Python 3.11, FastAPI, SQLite, Anthropic API, faster-whisper, plain HTML/CSS/JavaScript, pytest,
Ruff.

### Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
copy .env.example .env          # macOS/Linux: cp .env.example .env
```

Put your `ANTHROPIC_API_KEY` in `.env`. `WHISPER_MODEL` can be `tiny`, `base`, `small` or
`medium`; `base` is a good choice on slower machines. Without SMTP settings, password reset links
are printed in the terminal.

```bash
uvicorn app.main:build_default_app --factory --env-file .env --reload --port 8080
```

Open http://localhost:8080 in Chrome or Edge. For Turkish sentences to be read correctly, the
computer needs a Turkish voice (Windows: Settings → Time & language → Speech → Add voices).

### Tests

```bash
pytest
ruff check .
```

### Word list

The Oxford 5000 list is not included because it is not openly licensed. If you have it, place it
at `data/oxford5000.csv` with the columns `word,pos,level`. The app works without it, but the word
assessment is hidden. Using the list in a public release requires permission from Oxford
University Press.

## Türkçe

TalkBuddy, İngilizce konuşma pratiği yapmak isteyenler için hazırladığım bir web uygulaması.
Partnerinle sesli konuşabilir ya da yazışabilirsin. Partner seviyene göre cevap veriyor, hatalarını
kısaca düzeltiyor ve bilmediğin kelimeleri ve kalıpları saklıyor. Arayüz Türkçe.

### Özellikler

**Sohbet**

- Konuşma ve yazışma aynı ekranda. Ses sunucuda faster-whisper ile yazıya çevriliyor; İngilizce
  ve Türkçe tanınıyor.
- Takıldığında Türkçe sorabilirsin ("Bunu nasıl söylerim?"). Partner İngilizcesini söyleyip
  konuşmaya devam ediyor. Türkçe cümleler Türkçe sesle okunuyor.
- Konuşmanın ortasında sorduğun sorular ("Doğru mu söyledim?", "Bu ne demek?") önce cevaplanıyor,
  sonra partner konuya dönüyor.
- Konuşarak, yazarak ya da resmine dokunarak partnerin sözünü kesebilirsin.
- Gün boyu tek sohbet: konuşmadan çıkıp aynı gün geri dönünce kaldığın yerden devam ediyorsun.

**Kelimeler ve cümleler**

- Partnerin mesajlarındaki İngilizce bir kelimeye dokununca Türkçesi açılıyor ve kaydedebiliyorsun.
- "Bu kelimeyi bilmiyorum" ya da "Bu kalıbı bilmiyorum" demek de onu kaydediyor.
- "Bu cümleyi ekle" deyince ya da yazınca partnerin son İngilizce cümlesi kaydediliyor.
- Kelimeler **Kelimelerim**'e; cümle kalıpları ("I'm looking forward to ...") ve nasıl
  söyleyeceğini bilmediğin cümleler **Cümlelerim**'e gidiyor. İstemediğin kaydı listeden
  çıkarabiliyorsun.
- Kaydedilenler sonraki konuşmalarda aralıklı tekrarla (1, 3, 7, 14, 30 gün) yeniden karşına
  çıkıyor.

**Öğrenme yolu ve gelişim**

- Adım adım kurulum: yaş grubu, seviye (A1–C2 ya da kelime testi), ilgi alanları, öğrenme amacı ve
  partner (kadın ya da erkek). Her adım kaydediliyor.
- Oxford 5000 tabanlı kelime testi: her biri 30 kelimelik beş seviye, geçme sınırı 29/30.
- A1–A2 için yönlendirmeli başlangıç konuşmaları; B1 ve üstü için ilgi alanlarına göre konular.
- Seri, günlük hedef, rozetler ve yalnızca kendi konuşmalarından oluşan gelişim ekranı.
- Fotoğraflı profil, şifre ve e-posta değiştirme, öğrenme tercihleri, açık ve koyu tema.

**Gizlilik**

- Ses kaydı saklanmıyor, sadece yazıya çevrilmiş metin kaydediliyor.
- Şifreler özetlenerek saklanıyor ve her kullanıcı yalnızca kendi verisini görüyor.

### Kurulum

Kurulum ve çalıştırma komutları İngilizce bölümdekiyle aynı. `.env` dosyasına kendi
`ANTHROPIC_API_KEY` değerini yazman yeterli. Bilgisayar yavaşsa `WHISPER_MODEL=base`
kullanabilirsin. Türkçe cümlelerin doğru okunması için bilgisayarda Türkçe ses yüklü olmalı
(Windows: Ayarlar → Saat ve dil → Konuşma → Ses ekle).

### Kelime listesi

Oxford 5000 listesi açık lisanslı olmadığı için depoda yok. Elinde varsa `data/oxford5000.csv`
olarak ekleyebilirsin. Liste olmadan da uygulama çalışıyor, sadece kelime testi görünmüyor.
Herkese açık bir sürümde kullanmak için Oxford University Press'ten izin gerekiyor.
