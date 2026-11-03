# TalkBuddy

TalkBuddy is a voice-first English speaking partner for Turkish learners. The learner talks out
loud with a partner, gets short and gentle corrections, saves new words, and reviews them
in later conversations. All interface text is in Turkish.

## Flow

Log in (new users sign up from the link under the card) → a one-question-per-screen setup that
slides forward with "Devam et": age group → English level (A1–C2, or "I don't know my level" for
the optional word assessment) → interests (up to 10 of 26, can be skipped) → learning goal →
partner (female / male) → a short, easy first conversation → "first conversation done" summary →
home screen. Each step is saved, so a learner who leaves continues from the same step.

## Features

- Accounts: a single centered login card with a sign-up link below it, floating-label fields,
  show/hide password and "remember me"; password reset by email, password and email change
  (confirmed by email), logout, conversation history deletion. Passwords are hashed with scrypt;
  sessions use an httpOnly cookie.
- Onboarding is saved step by step and is never asked again once finished.
- Word assessment: 5 sections (A1–C1) of 30 shuffled words each, taken from the Oxford 5000.
  A level passes at 29/30 (95%, unrounded). The recommendation is the highest level passed
  without a gap from A1. C2 can still be chosen by hand.
- Voice conversation: the browser records the learner until they pause, the server transcribes
  the audio with Whisper (faster-whisper, English and Turkish detected automatically, the
  learner's name given as a hint), and the partner answers aloud with a female or male voice.
  Pauses are longer for A1–A2, and tapping the partner interrupts it. Audio is processed in
  memory and never stored. With `WHISPER_MODEL=off` the browser's own recognition is used.
- The learner can speak Turkish at any point without pressing a button ("…demek istiyorum",
  "Bunu nasıl söylerim?"): the partner answers with one short Turkish sentence, the English
  sentence they wanted, and an English question that lets them use it.
- The coach (Claude) replies in JSON; the backend validates it and keeps vocabulary, errors,
  level estimates and session notes per learner.
- Vocabulary with spaced repetition (1, 3, 7, 14, 30 days); the words screen filters by due,
  learning and mastered, and every word can be listened to.
- Level plan: each level's Oxford words form a plan. The home screen shows real coverage, and
  each conversation brings in a few new plan words, starting with words left unmarked in the
  assessment.
- Starter path for A1–A2: eight short guided conversations (introductions, daily routine, likes,
  family, café, weekend, town, plans). B1 and above get the next topic from their interests.
- Home screen: one suggested conversation for today, with other topics and lengths (5–20
  minutes) folded away; where the learner left off, words due for review and level plan.
- Conversation screen with few controls: microphone, Turkish help and end; replay, speed,
  transcript and language are in a "more" menu.
- Streak, daily goal (5/10/15/20 minutes) and badges, computed from finished conversations in
  Turkish local time (UTC+3).
- Four tabs with separate jobs: Konuşma (today's conversation), Kelimelerim (words), Gelişimim
  (learning progress) and Profil (account and settings).
- Progress screen built only from saved records: today against the goal, streak, a 7-day chart,
  total speaking time and sessions, word and review counts, level plan coverage, most corrected
  structures, monthly reviews, badges and a few suggestions drawn from the same records. New
  learners see a short welcome instead of empty charts.
- Profile: photo (or initials), name, email and level, with four sub-screens: personal details
  (name, photo, age group, email change confirmed by email), password change, learning
  preferences (level, partner, daily goal, goal, interests, partner voice and speaking speed) and
  app settings (notifications, light/dark/system theme, larger text, history deletion, logout).
  Theme, text size, voice and speed are kept on the device; everything else is saved to the
  account. Profile photos are cropped and shrunk in the browser and only shown to their owner.
- In-app notifications (daily goal, words due, weekly summary, monthly review, new badge) behind
  a bell with an unread count; each type can be turned off in the profile. There are no phone
  push or email reminders.
- Tapping a word in the transcript shows its Turkish meaning and an example, and can save it.
- An optional monthly speaking review that can be postponed.
- Session summary built from saved records.
- Each user can only read their own data. Raw audio is never stored.

## Project layout

```
app/
  main.py        FastAPI routes
  accounts.py    sign-up, login, onboarding, assessment state
  auth.py        password hashing, tokens, email
  assessment.py  word assessment sections and scoring
  speech.py      speech-to-text with Whisper
  wordlist.py    Oxford 5000 word list loading
  plan.py        level plan progress and new word suggestions
  path.py        starter path and today's suggested conversation
  progress.py    streak, daily goal, badges, progress and notifications
  tutor.py       conversation flow and learner memory
  coach.py       prompt assembly and JSON parsing
  level.py       level estimate (coach + word profile)
  vocab.py       spaced repetition
  report.py      session summary
  db.py          SQLite storage
  prompts/       coach system prompt
data/            Oxford 5000 word list (not in the repository)
web/             Turkish single-page interface
tests/
```

## Setup

Requires Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\activate           # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
copy .env.example .env           # macOS/Linux: cp .env.example .env
```

Fill in `ANTHROPIC_API_KEY` in `.env`. Without SMTP settings, password reset links are printed
to the server terminal.

The Whisper model (`small` by default, about 500 MB) is downloaded on the first start and
cached. `tiny` or `base` are faster on slow computers; `medium` is more accurate.

The server terminal shows how long each step takes ("Ses 1.2 sn'de yazıya çevrildi",
"Partnerin cevabı 2.4 sn sürdü"). If transcription is the slow part, set `WHISPER_MODEL=base`.
The partner's instructions are sent with prompt caching, so replies after the first one in a
conversation start faster.

## Run

```bash
uvicorn app.main:build_default_app --factory --env-file .env --reload --port 8080
```

Open http://localhost:8080 in Chrome or Edge (voice recognition needs one of these).

## Test

```bash
pytest
ruff check .
```

## Word list

Word levels come only from the Oxford 5000 (Oxford University Press), which covers A1–C1.
The list is not open-licensed, so it is not stored in this repository. Put it at
`data/oxford5000.csv` with the columns `word,pos,level`, where `pos` is one of `noun`, `verb`,
`adjective`, `adverb` or another part of speech, and `level` is A1–C1.

Without this file the app still runs: the word assessment is hidden and learners pick their
level, and level tracking relies on the coach's estimate alone. Permission from Oxford
University Press is needed before the list is used in a public release. The 95% threshold is
an app rule, not an official CEFR standard.
