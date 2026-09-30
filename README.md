# LearnOrbit

LearnOrbit is a Flask-based adaptive learning application. Students can study a topic with an AI tutor, take session-specific quizzes, review saved notes and mastery, and use study utilities in the same account.

> **Billing notice:** checkout is a demonstration flow. It does not process real payments.

## Contents

- [What the application does](#what-the-application-does)
- [Project structure](#project-structure)
- [Run locally](#run-locally)
- [AI provider setup](#ai-provider-setup)
- [Learning and analytics](#learning-and-analytics)
- [Plans and access](#plans-and-access)
- [Data and privacy](#data-and-privacy)
- [External services](#external-services)
- [Deployment notes](#deployment-notes)

## What the application does

### Learning cycle

1. **Learn:** create a session for a subject and discuss it with the AI tutor.
2. **Retrieve:** choose an untimed practice quiz or a timed exam. Assessments can mix single-choice MCQ, select-all-that-apply MSQ, and rubric-graded written answers.
3. **Repair:** review objective answers, written-answer rubric feedback, Bloom's taxonomy, and the examiner-intent blueprint revealed after submission. A quiz score below 40% reopens the session for an automatic, focused tutor review of missed questions.
4. **Revisit:** each completed session gets a 10-day recall test. When due, a quiz-mode attempt measures recall and schedules the next check 10 days later.

The tutor can vary its explanation and difficulty. Quiz prompts request questions across six Bloom levels (Remember, Understand, Apply, Analyze, Evaluate, Create). The UI asks learners to rate confidence on a five-point scale. Averages and calibration are computed from submitted answers; metrics are not inferred when no confidence rating exists.

### Dashboard

- Recent learning sessions, streak and attendance indicators, and per-topic mastery.
- A Chart.js study-rhythm graph with daily session counts and quiz scores across the previous 14 days.
- A weekly recorded-learning-time view and a recent missed-concept dashboard. Session duration is a wall-clock estimate, not device-level screen telemetry.
- Learning-topic connection map, generated from the account's topic list.
- A per-session 10-day recall-test countdown, due-test prompts, measured recall history, and exponential retention estimates on the dashboard. Tests and charts are retained for every completed session.
- Scholar Study Rooms provide invite-code, text-only group chat with polling; there is no live voice/video.
- Scholar timed exams contain 20 questions and use a server-enforced 30-minute window. They deduct 0.25 points only for an answered-wrong MCQ/MSQ; written questions use three criteria graded 0–2 each for partial credit. Quiz and exam examiner-intent blueprints are shown only after submission.
- Scholar tutor sessions include two-agent debate and twin-student teach-back helpers. Their generated output is temporary and not saved into the tutor transcript.
- Academy members can view global game leaderboards; signed-in usernames are displayed there.
- Daily signed-in learning check-ins grant 3 Orbit Tokens. The wallet ledger supports one-time cosmetic badge redemptions; tokens are not cash or transferable.
- Academy-only confidence, calibration, and quiz recall summaries. The dashboard describes their formulas and includes the number of rated and answered questions used as evidence.

The analytics are descriptive of stored app activity, not a clinical or psychological assessment. “Quiz recall accuracy” is retrieval accuracy in the displayed period. Per-session retention estimates use an exponential approximation and observed delayed-test scores; they are uncertain estimates, not validated diagnoses or guaranteed predictions. A near-perfect score relative to the prior test is treated as a lower-bound observation rather than a precise stability estimate.

### Notes and study utilities

- Generated session notes are stored in `learning_sessions.notes_md`. Regenerating notes replaces that session's saved notes.
- Calculator supports standard and scientific operations. The graph studio plots a function locally using Canvas and math.js; it redraws for theme changes.
- Focus music, relax timer, stopwatch, calendar, and eight browser games are available from the signed-in navigation. Calendar reminder polling runs while a signed-in LearnOrbit page is open; web notifications cannot be promised after the app is closed.
- The game directory includes instructions for both keyboard/mouse and touchscreen controls.
- Video Study accepts a local video with supported transcription or an uploaded caption file. Its transcript and chat are temporary browser-session content, not saved as tutor-session notes.
- Practice Code is a paid-tier feature and sends submissions to Judge0 CE.

## Project structure

```text
learnorbit/
├── app.py
├── init_db.py
├── app/
│   ├── __init__.py                 # Flask app factory, extensions, schema setup
│   ├── config.py                   # Environments, provider catalog, tier entitlements
│   ├── models/__init__.py          # SQLAlchemy models and relationships
│   ├── routes/
│   │   ├── auth.py                 # Registration, login, settings
│   │   ├── dashboard.py            # Dashboard and topic map
│   │   ├── tutor.py                # Tutor sessions, messages, completion
│   │   ├── quiz.py                 # Quiz generation, submission, scoring
│   │   ├── notes.py                # Persistent generated notes
│   │   ├── games.py                # Games, usage limits, best scores
│   │   ├── features.py             # Profiles, calendar, billing, utilities, video
│   │   ├── study_rooms.py          # Scholar invite-code rooms and text chat
│   │   ├── rewards.py              # Token wallet and cosmetic reward redemptions
│   │   └── api.py                  # Theme and provider APIs
│   └── services/
│       ├── ai_service.py           # Provider adapters and prompts
│       └── mastery_service.py      # Topic mastery calculations
├── templates/                      # Jinja pages, grouped by feature
├── static/
│   ├── css/                        # Shared design system and landing styles
│   └── js/                         # Shared navigation and landing interactions
├── instance/                       # Local uploaded files (not source-controlled)
└── requirements.txt
```

## Run locally

Requirements: Python 3.10 or newer and pip.

```bash
git clone <repository-url>
cd learnorbit
python -m venv .venv
source .venv/bin/activate       # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```

Set a unique `SECRET_KEY` in `.env`, then start the application:

```bash
python init_db.py
python app.py
```

Open [http://127.0.0.1:45000](http://127.0.0.1:5000). The default development database is `learnorbit_dev.db` in the project directory. The app factory creates missing tables and applies its small, additive compatibility migrations at startup.

Email verification can use SMTP settings documented in `.env.example`. Without SMTP in development, verification codes are written to the server console; production configuration should use a real mail provider.

## AI provider setup

Create an account, then choose a provider, model, and API key under **Settings**. The current provider catalog includes:

| Provider                         | Credential source                                                                         |
| -------------------------------- | ----------------------------------------------------------------------------------------- |
| OpenAI                           | [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)               |
| Google Gemini                    | [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)           |
| Anthropic Claude                 | [https://console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) |
| xAI Grok                         | [https://console.x.ai/](https://console.x.ai/)                                             |
| Hugging Face Inference Providers | [https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)           |

Provider model availability and pricing are controlled by each vendor. The key is used by the LearnOrbit server to make requests to the selected provider; protect the account database and server environment accordingly.

## Learning and analytics

### Quiz confidence calculations

For each submitted question, the learner's confidence rating (1–5) is stored with the attempt:

- **Average confidence:** mean rating multiplied by 20, expressed as a percentage.
- **Calibration:** `100 − mean absolute error`, where each rating is converted to a 20–100% confidence estimate and the observed outcome is 100% for a correct answer or 0% for an incorrect answer. Higher values mean confidence more closely tracked correctness.
- **Quiz recall accuracy:** correct answers divided by all answered quiz questions in the dashboard period.

The dashboard excludes unrated legacy answers from confidence and calibration and displays sample counts. These are transparent descriptive measures, not a validated diagnosis or an estimate of future exam performance.

### 10-day retention checks

Each completed session starts a fixed 10-day retrieval-test cycle, including sessions completed before this feature was added (their schedule is initialized when the dashboard or due-check API is opened). A due practice quiz is allowed even when an Explorer has used the session's one starter quiz. Submitting it advances that session's next test by another 10 days.

For a delayed score, the app compares the new score to the prior score, clamped to a 1–100% relative-retention range. When measured retention `r` is below 98%, an individual exponential stability estimate is calculated as `S = -t / ln(r)`, where `t` is the elapsed time in days. Repeated estimates are blended 50/50 for display. Relative scores at or above 98% are ceiling-censored; the app does not pretend to infer an exact decay rate from them. If no initial quiz score exists, the first delayed check establishes the observed baseline and is not used to fit decay. The requested ten-day interval stays fixed instead of being altered by this noisy estimate.

This is a transparent educational approximation, not a claim that memory follows one universal exponential curve or that ten days is optimal for every student. The evidence supports the learning activities used here—practice testing and distributed practice—not this specific fitted model or fixed cadence. Dunlosky et al. (2013) review: [Improving Students’ Learning With Effective Learning Techniques](https://www.psychologicalscience.org/publications/journals/pspi/learning-techniques.html).

### Theme and charts

The signed-in theme is saved to the user profile and mirrored in local storage for immediate display. PJAX navigation preserves the global audio element. Page scripts execute in order after navigation so external chart libraries load before the dashboard graph initializes.

The dashboard uses Chart.js. The calculator's separate function plotter uses the Canvas API and math.js; its background, axes, and curve are redrawn when the theme changes.

## Plans and access

The signed-in billing page and public landing page show the same plan boundaries:

| Plan               |     Price (demo) | Included access                                                                                                                                                                 |
| ------------------ | ---------------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Explorer** |             Free | 3 tutor sessions per UTC day, one starter quiz per session plus scheduled 10-day recall checks, games, calendar, notes, basic mastery and study-rhythm chart                    |
| **Scholar**  |  $9.99 / 30 days | Explorer features, unlimited sessions and practice quizzes, split-screen PDF preview, Practice Code, Study Rooms, 20-question/30-minute exams, two-agent debate, and teach-back |
| **Academy**  | $24.99 / 30 days | Scholar features plus confidence calibration, quiz-recall analytics, and global game leaderboards                                                                               |

Explorer is the default plan and is not offered as a checkout selection. Session and quiz quotas are enforced on their server routes. Practice Code, PDF preview, and advanced analytics are gated by plan on the server as well as in the interface. Plans are changed using a simulated checkout and no money or card details are transmitted to a payment processor.

## Data and privacy

SQLite is used by default. Set `DATABASE_URL` to use a supported production database. Principal data includes:

| Table                                                                                          | Data                                                                                       |
| ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `users`, `user_profiles`                                                                   | Account, selected plan, preferences, theme, profile                                        |
| `learning_sessions`                                                                          | Topic, timestamps, status, conversation, misconceptions, saved notes, quiz/mastery summary |
| `quiz_attempts`                                                                              | Submitted questions, answers, explanations, confidence ratings, and scores                 |
| `topic_mastery`                                                                              | Per-user topic scores and study counts                                                     |
| `learning_behavior`, `attendance_stamps`                                                   | Aggregated learning activity and attendance                                                |
| `session_documents`                                                                          | Uploaded tutor-session documents and retrieval data while the session is active            |
| `calendar_events`, `game_scores`, `game_usage`                                           | Personal study reminders and game activity                                                 |
| `topic_review_schedules`, `orbit_wallets`, `orbit_token_transactions`, `orbit_rewards` | Spaced-review planning and one-time token/badge purchases                                  |
| `subscriptions`, `payment_records`                                                         | Demonstration billing state and invoice references                                         |

Tutor conversations, quiz answers, and notes are associated with the student's account. AI requests are sent to the configured provider. Avoid entering sensitive personal information into prompts. Uploaded session documents are removed when a tutor session is ended.

## External services

- [Chart.js](https://www.chartjs.org/) for the dashboard activity graph.
- [math.js](https://mathjs.org/) for local calculator expression evaluation.
- [MathJax](https://www.mathjax.org/) and Marked.js for mathematical notation and Markdown rendering.
- [Lucide](https://lucide.dev/), Animate.css, CodeMirror 5, and Google Fonts for UI assets and editor presentation.
- [Judge0 CE](https://judge0.com/) for Practice Code execution. Submitted programs run in an external sandbox; there is no live interactive shell.
- Configured AI provider for tutor responses, notes, quiz content, and topic-map connections.

Third-party services have their own availability, terms, and privacy policies. CDN-backed assets require an internet connection.

## Deployment notes

Before deploying:

1. Set a long, unique `SECRET_KEY` and `FLASK_ENV=production`.
2. Configure a production `DATABASE_URL` and backups.
3. Serve behind HTTPS; production cookies are marked secure.
4. Configure SMTP for account verification and email receipts.
5. Use encrypted secret storage and database encryption at rest for provider keys.
6. Add deployment-appropriate rate limits, monitoring, and retention policies.
7. Integrate a real payment provider before representing checkout as a real purchase.

`requirements.txt` contains the Python runtime dependencies. Front-end libraries are loaded from CDNs; there is no JavaScript build step.
