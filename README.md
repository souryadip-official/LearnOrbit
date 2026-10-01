# LearnOrbit

LearnOrbit is a responsive, Flask-based learning application that combines an AI tutor, assessments, learning analytics, spaced review, study utilities, games, community features, and a restricted operations console.

> **Important:** Subscription checkout is a demonstration flow. It does not collect card details or process real payments. LearnOrbit is not an accredited school, a substitute for an educator, or a validated psychological or medical assessment.

## Contents

- [Product overview](#product-overview)
- [Feature guide](#feature-guide)
- [Plans and entitlements](#plans-and-entitlements)
- [Technology and project layout](#technology-and-project-layout)
- [Run locally](#run-locally)
- [Environment variables and secrets](#environment-variables-and-secrets)
- [Database setup](#database-setup)
- [AI provider setup](#ai-provider-setup)
- [Admin provisioning and access](#admin-provisioning-and-access)
- [Deploy to Render](#deploy-to-render)
- [Production readiness and operations](#production-readiness-and-operations)
- [Data, privacy, and third parties](#data-privacy-and-third-parties)
- [Development and validation](#development-and-validation)
- [Known limitations](#known-limitations)

## Product overview

LearnOrbit is designed around a repeatable learning cycle:

1. **Learn:** start a topic-based tutor session and discuss concepts with the AI tutor.
2. **Retrieve:** generate a practice quiz or, where entitled, a timed exam. Supported question types include single-answer MCQ, multiple-select MSQ, and written responses.
3. **Understand:** review explanations, Bloom's taxonomy labels, confidence information, and the examiner-intent blueprint after submission.
4. **Improve:** revisit missed concepts and continue the tutor session with targeted practice.
5. **Remember:** take a scheduled recall test for completed sessions and view the observed results and retention estimates over time.

LearnOrbit is a learning aid. AI-generated explanations, questions, written-answer grading, topic links, feedback summaries, and retention estimates can be incomplete or incorrect. Learners should verify consequential information with appropriate sources.

## Feature guide

### Student learning

- **AI tutor:** topic-based sessions, chat, Markdown/code/math rendering, and optional uploaded study documents for retrieval-grounded answers.
- **Quiz and exam:** a standard quiz contains 10 questions, is untimed, and does not apply negative marking. Scholar/Academy exam mode contains 20 questions, has a 30-minute server-checked time window, and deducts 0.25 points for each answered-wrong MCQ/MSQ. Written answers use rubric-based evaluation and do not receive negative marking.
- **Question insights:** assessments can include Bloom's taxonomy labels and reveal a paper blueprint/examiner-intent breakdown after submission.
- **Weak-topic follow-up:** prior missed concepts can be used to shape later question generation and tutor re-engagement.
- **Notes:** generated notes are stored against the learning session and can be revisited.
- **Learning analytics:** session and quiz history, topic mastery, attendance/streak, confidence and recall metrics, weekly activity, and a topic-connection visualization.
- **Ten-day recall schedule:** completed sessions are given a recurring retrieval check. The dashboard shows time remaining; completing a due check advances the next check by ten days.
- **Misconceptions and concepts to revisit:** the dashboard surfaces stored misconceptions and review candidates based on available learner performance data.
- **Academic cohort statistics:** an academic leaderboard shows anonymized cohort performance summaries and score distributions; it does not publish other learners' real names.
- **Feedback and issue tracking:** submit star ratings and suggestions, report an issue, and follow issue-status updates from the same account.
- **Application guide and policies:** the student-facing “Know LearnOrbit” guide explains the main product areas; terms and policy pages are linked from the public site and account UI.

### Learning calculations and interpretation

- **Confidence average:** the mean of submitted 1–5 confidence ratings, displayed on a percentage-like 20–100 scale.
- **Calibration:** `100 - mean absolute error` between the selected confidence percentage and the scored correct/incorrect outcome (100 or 0). Unrated historical answers are excluded, and samples are shown in the dashboard.
- **Quiz recall accuracy:** correct answers divided by answered questions in the selected activity window.
- **Retention estimate:** where a prior score exists and the relative delayed score is below the ceiling threshold, the app estimates exponential stability as `S = -t / ln(r)`, with elapsed days `t` and relative score `r`. Repeated estimates are blended for display. A first delayed test establishes a baseline, and near-ceiling scores are treated as censored instead of pretending to give a precise decay value.
- **Fixed schedule:** the ten-day interval is a product rule, not a scientifically individualized optimum. The exponential curve is a descriptive approximation, not a validated prediction for an individual learner.
- **Study time:** recorded session timing is an app activity estimate; it is not device-wide screen-time monitoring.

### Study tools and engagement

- **Scientific calculator and graph studio:** expression evaluation uses math.js in the browser; graphs are drawn locally with Canvas.
- **Calendar:** personal study events and reminders. Reminder checks require the LearnOrbit app to be open; delivery after closing the app is not guaranteed.
- **Focus music:** playback preferences are saved in the browser. Browser autoplay rules can require a user gesture after refresh.
- **Relax timer, stopwatch, and games:** browser-based breaks and casual practice activities.
- **Orbit Tokens and rewards:** daily signed-in check-ins award tokens; the wallet ledger supports one-time cosmetic badge redemptions. Tokens are not money, transferable, or redeemable for cash.
- **Study Rooms:** Scholar-and-above invite-code rooms provide text chat with periodic polling. They do not provide live audio/video. Members can leave; room ownership transfers to the longest-standing remaining member, and an owner's last-member exit deletes the empty room and its messages.
- **Two-agent debate and teach-back:** optional AI learning modes are available on eligible plans. Generated helper output is not part of the persisted tutor transcript.
- **Practice Code:** an eligible-plan code editor submits programs to the configured Judge0 CE service. It is a run-once sandbox integration, not a live shell or production deployment environment.
- **Progressive Web App:** the site provides an installable manifest and a service worker that caches selected static assets and an offline fallback page. Authenticated pages, API data, and interactive learning are not available offline.

### Feedback and operations

- Anonymous feedback forms collect 1–5 ratings across usability, learning value, reliability, design, speed, mobile experience, readability/accessibility, useful features, and overall experience.
- Aggregate ratings are displayed on the public landing page only after the configured minimum response count is reached. Written comments remain private to authorized staff.
- Staff can request an AI-assisted synthesis of recent feedback. This explicitly sends comment text to the configured Gemini or Hugging Face provider; review the original comments and generated themes before making decisions.
- Staff can review issues, update their status, manage user access, inspect platform activity, and edit supported policy content. Sensitive administrative actions are audited.

## Plans and entitlements

Current plan names, price labels, and feature gates are configured in `app/config.py`. Displayed charges and simulated checkout records are for demonstration only.

| Plan | Current displayed price | Main access |
| --- | ---: | --- |
| **Explorer** | Free | Limited daily tutor sessions, one starter quiz per session, scheduled recall quizzes, games, calendar, notes, basic mastery, and study-rhythm views. |
| **Scholar** | $9.99 per 30-day period | Explorer features plus unlimited sessions/quizzes, split-screen PDF preview, Practice Code, Study Rooms, timed exams, debate, and teach-back. |
| **Academy** | $24.99 per 30-day period | Scholar features plus advanced confidence/recall analytics and global game leaderboards. |

Plan access is enforced in server routes for gated actions; hiding a button in the UI alone is not the access control. The plan prices and billing records are not connected to a payment processor. Do not represent a checkout as a real subscription sale.

## Technology and project layout

- **Backend:** Python, Flask, Flask-Login, Flask-WTF/CSRF, SQLAlchemy, Flask-Migrate.
- **Database:** SQLite by default in development; PostgreSQL through `DATABASE_URL` for production.
- **Frontend:** server-rendered Jinja templates, plain JavaScript, CSS, and third-party libraries loaded from CDNs. There is no npm build step.
- **AI:** server-side provider adapters for OpenAI-compatible services, Google Gemini, Anthropic, xAI, and Hugging Face.
- **External execution:** Judge0 CE for Practice Code; Twilio for production staff OTP; SMTP for user email verification and invoice email delivery.

```text
learnorbit/
├── app.py                         # WSGI entry point; loads .env for local runs
├── init_db.py                     # Optional local table initialization helper
├── requirements.txt               # Python runtime dependencies
├── .env.example                   # Safe configuration template; contains no live credentials
├── app/
│   ├── __init__.py                # App factory, extensions, startup schema setup
│   ├── config.py                  # Environments, plan gates, provider catalog
│   ├── models/__init__.py         # SQLAlchemy data models
│   ├── routes/                    # Auth, tutor, quiz, dashboard, admin, features, etc.
│   └── services/                  # AI provider and mastery services
├── templates/                     # Jinja pages by feature area
├── static/
│   ├── css/                       # Shared, feature, landing, and admin styles
│   ├── js/                        # Navigation, feature interactions, PWA, study rooms
│   ├── manifest.webmanifest       # PWA metadata
│   └── service-worker.js          # Static caching and offline navigation fallback
└── instance/                      # Runtime/private files; gitignored
```

## Run locally

### Requirements

- Python 3.10 or newer.
- `pip`.
- Optional provider accounts/API keys for AI features.
- Optional local PostgreSQL if you want to exercise PostgreSQL instead of the default SQLite database.

### Install and run

From the repository root:

```bash
git clone <repository-url>
cd learnorbit
python3 -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Generate a local-only random key and put it in your ignored `.env`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set a development-only `SECRET_KEY` in `.env`, then run:

```bash
python app.py
```

Open <http://127.0.0.1:45000>. The development database defaults to `learnorbit_dev.db` in the repository root. The application factory creates missing tables at startup. `init_db.py` is optional and does not replace schema migration planning.

To stop the development server, press `Ctrl+C`. Keep `.env`, local databases, uploaded files, and admin records out of version control.

## Environment variables and secrets

### Should you update `.env`?

**For local development:** yes, update your local `.env` with local settings and any optional credentials you need. `.env` is gitignored and should stay on your machine.

**For production:** do not rely on a repository `.env` file. Put the values in the hosting provider's protected environment-variable/secret settings. The app loads `.env` through `app.py` for local execution; deployed services should receive their secrets from the host.

Never add real database credentials, API keys, admin passwords, OTP credentials, or personal admin data to `README.md`, `.env.example`, source control, screenshots, or public issue trackers. If a credential has already been shared or committed, revoke/rotate it and update the secret store.

| Variable | Required when | Purpose |
| --- | --- | --- |
| `FLASK_ENV` | Production | Set to `production` to select production settings. |
| `SECRET_KEY` | Production | Long, unique random value used to sign Flask sessions and related tokens. |
| `DATABASE_URL` | Production | PostgreSQL connection URI. Required by production startup. |
| `SMTP_HOST` | Production user registration/login OTP | SMTP server hostname. Production account verification/login requires email delivery. |
| `SMTP_PORT` | If SMTP is configured | SMTP port; defaults to `587`. |
| `SMTP_FROM` | Recommended with SMTP | Sender address. Falls back to `SMTP_USER` when unset. |
| `SMTP_USER` | If SMTP authentication is needed | SMTP account username. |
| `SMTP_PASSWORD` | If SMTP authentication is needed | SMTP account password. |
| `ADMIN_REGISTRY_PATH` | Admin registry is mounted outside `instance/` | Absolute path to the private admin JSON file. Defaults to `instance/admins.json`. |
| `TWILIO_ACCOUNT_SID` | Production admin OTP | Twilio account SID. |
| `TWILIO_AUTH_TOKEN` | Production admin OTP | Twilio authentication token. |
| `TWILIO_FROM_NUMBER` | Production admin OTP | Twilio-enabled sender number. |
| `ADMIN_OTP_COUNTRY_CODE` | Optional | Country prefix for admin records whose mobile number is not in E.164 format; defaults to `+91`. Store phone values in E.164 form where possible. |
| `GEMINI_API_KEY` | Admin feedback synthesis using Gemini | Platform-managed Gemini key; optional. `GOOGLE_API_KEY` is also accepted. |
| `GEMINI_FEEDBACK_MODEL` | Optional | Feedback-synthesis model; defaults to `gemini-3.1-flash-lite`. |
| `HF_TOKEN` | Admin feedback synthesis fallback | Platform-managed Hugging Face token; optional. `HUGGINGFACEHUB_API_TOKEN` is also accepted. |
| `HF_FEEDBACK_MODEL` | Optional | Feedback-synthesis model; defaults to `openai/gpt-oss-120b`. |
See `.env.example` for the template and comments. Do not put your production `DATABASE_URL` in the committed example file.

### Student AI-provider keys versus admin provider keys

- Tutor, quiz generation, notes, and related AI actions use the **signed-in learner's selected provider/model and API key**, managed from the app's Settings page. Each learner supplies their own provider credential.
- `GEMINI_API_KEY` and `HF_TOKEN` are optional **platform-managed keys** used for the staff-requested feedback-comment synthesis feature; they do not automatically supply keys to student tutor sessions.
- Provider credentials are stored in the application's user database. Review and strengthen database access, encryption-at-rest, backup, and retention controls before handling real users' API keys at production scale. Never log, export, or expose these credentials to client-side JavaScript.
- Model names and account access vary by provider. A model listed in the UI is not a guarantee that the provider account can use it.

## Database setup

### Local SQLite (default)

Leave `DATABASE_URL` unset in development. The app selects SQLite at `learnorbit_dev.db`. The database is ignored by Git. SQLite is suitable for local development, not a multi-instance production deployment.

### Local PostgreSQL (optional)

1. Create a local PostgreSQL database and database user.
2. Install the project requirements (the psycopg 3 driver is included).
3. Set `DATABASE_URL` in your private local `.env`:

   ```dotenv
   DATABASE_URL=postgresql+psycopg://USERNAME:PASSWORD@HOST:5432/DATABASE?sslmode=require
   ```

4. If the password contains URI-reserved characters, percent-encode it in the URL.
5. Restart the app and verify that it starts and that registration/session data appears in the intended database.

Use `sslmode=require` for hosted PostgreSQL services that require TLS. Follow the database provider's current connection-string and network access instructions.

### Production PostgreSQL

1. Create a managed PostgreSQL service and database/user with only the privileges the application needs.
2. Obtain the provider's application connection URI and confirm TLS/SSL requirements. If using the existing Aiven PostgreSQL service, retrieve the URI from the Aiven Console after rotating any credential that has been exposed, and confirm that its network-access rules permit connections from the hosting service.
3. Add it as a **secret environment variable** named `DATABASE_URL` on the web-service host. Do not commit it or paste it into `.env.example`.
4. Set `FLASK_ENV=production` and a fresh `SECRET_KEY` in the same host secret manager.
5. Start the service and verify database connectivity before accepting users.
6. Enable automated backups and test a restore before relying on the database.

Production startup currently calls `db.create_all()` and an additive compatibility routine for a small set of legacy columns. This can create missing tables and add known columns, but it is **not** a complete versioned migration strategy. It does not safely handle arbitrary renames, removals, data transformations, or all future schema changes. Back up the database before deployment and add/review explicit Flask-Migrate/Alembic revisions before making non-additive production schema changes.

Pointing `DATABASE_URL` at a new database does not copy records from `learnorbit_dev.db`. If existing learner data must be retained, plan and test a separate migration/export/import with consistent IDs, constraints, file paths, and a rollback plan. Do not run a first migration against a live database without a verified backup.

## AI provider setup

Learners configure their provider in **Settings** and use their own provider account/API key. Supported providers are OpenAI, Google Gemini, Anthropic, xAI, and Hugging Face Inference Providers.

1. Create an API key with the selected provider.
2. Sign in to LearnOrbit and open Settings.
3. Select the provider and a model available to that provider account.
4. Enter and validate the key, then save.
5. Try a new tutor question or quiz generation.

Provider usage may incur charges on the learner's provider account and is subject to vendor rate limits, model availability, and privacy terms. Do not include secrets or unnecessary sensitive personal information in prompts or uploaded learning documents.

For the optional admin feedback synthesis feature, set a platform-managed `GEMINI_API_KEY` (preferred) and optional `GEMINI_FEEDBACK_MODEL` in the host secret manager. Hugging Face can be configured as fallback with `HF_TOKEN` and `HF_FEEDBACK_MODEL`. The admin action explicitly sends up to 100 recent comments to the selected external provider. Data redaction is best-effort and is not guaranteed to remove all identifying information.

## Admin provisioning and access

Admin accounts are **not registered through the website**. Admin identities are allowlisted in a private JSON file; they are separate from student login and are **not provisioned as student rows in PostgreSQL**. The database stores transient OTP and audit records, but the staff allowlist itself is a separate secret file. The admin panel uses password verification followed by mobile OTP. It has a separate staff session and expires it after 30 minutes of inactivity.

### Required JSON shape

The default path is `instance/admins.json`. Keep the record private and use a password hash, never a plain-text password:

```json
{
  "admins": [
    {
      "email": "admin@example.com",
      "password_hash": "PASTE_A_WERKZEUG_PASSWORD_HASH_HERE",
      "display_name": "LearnOrbit Administrator",
      "date_of_birth": "YYYY-MM-DD",
      "sex": "prefer-not-to-say",
      "date_of_join": "YYYY-MM-DD",
      "mobile": "+15551234567",
      "role": "admin"
    }
  ]
}
```

The email, password hash, and mobile number are used for authentication/delivery. The other profile fields support the staff profile UI. Use actual authorized staff details only, and collect/store only profile information you need.

### Generate and install a password hash

Run from an environment where the project requirements are installed. The password is entered interactively, not included in the shell command:

```bash
python - <<'PY'
from getpass import getpass
from werkzeug.security import generate_password_hash

password = getpass("New admin password: ")
print(generate_password_hash(password))
PY
```

Copy the resulting hash into the private JSON record. Use a unique strong password and store it in an approved password manager. Never paste a plaintext password into a command that will be saved in shell history.

### Local development admin

1. Create the `instance` directory and `instance/admins.json` locally.
2. Restrict access to the file on macOS/Linux:

   ```bash
   mkdir -p instance
   chmod 700 instance
   chmod 600 instance/admins.json
   ```

3. Start the app with `FLASK_ENV=development`.
4. Sign in through **Admin Panel**. In development/debug only, the one-time code is printed to the server terminal. Student email verification/login codes are also printed in the terminal when SMTP is not configured in local debug mode. Do not rely on terminal OTP behavior in production.

The `instance/` directory is gitignored. Keep it private; do not commit it or copy it to a public artifact.

### Admin OTP in production

Production admin OTP requires Twilio. Configure the Twilio SID, token, sender number, and country code (if required) as host secrets. Provision `admins.json` via a protected file/secret mechanism. If any of these settings are missing or Twilio delivery fails, production admin sign-in fails closed; it does not print a usable OTP in production logs.

For a host that supports secret files, upload the JSON as a secret file and set `ADMIN_REGISTRY_PATH` to the file's absolute runtime path. For example, Render mounts secret files under `/etc/secrets/`; upload `admins.json` there and set `ADMIN_REGISTRY_PATH=/etc/secrets/admins.json`. The current loader rejects POSIX files readable by group/others, so verify the mounted file has owner-only permissions (mode `0600`). If the provider does not support sufficiently restrictive permissions, do not weaken the check or enable admin login until a compatible secret-file mechanism is configured. Do not rely on a transient app filesystem for this file.

## Deploy to Render

Render can host this Flask app as one Web Service: Flask renders the frontend and serves static assets. A separate static-site service is not required.

> Render's free web services spin down after inactivity, have ephemeral local filesystems, and are intended for testing/hobby use rather than production. Use a paid always-on service and durable object storage for a real production workload.

### Before creating the service

1. Push the repository to a private GitHub repository, after confirming `.env`, local databases, `instance/`, and uploads are not tracked.
2. Rotate any database/API/Twilio credentials that have been exposed in chat, logs, screenshots, or source control.
3. Create or select a managed PostgreSQL database. Copy its application connection URI from the provider dashboard; do not publish it.
4. Prepare a fresh `SECRET_KEY` and (if using the admin console) an admin JSON secret file and Twilio credentials.
5. Decide how to persist user uploads. Render's free filesystem is ephemeral; the app stores some uploads/profile images locally under its runtime instance path. Production needs persistent disk or, preferably, object storage and a configured storage integration.

### Create and configure the Render Web Service

1. In the Render Dashboard choose **New → Web Service**, connect the repository, and select the deployment branch.
2. Configure:
   - **Runtime:** Python.
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn app:app --bind 0.0.0.0:$PORT`
   - **Instance type:** choose Free only for a disposable/hobby deployment; select an always-on paid instance for production needs.
3. Generate a new production signing secret (do not reuse the development value):

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   Copy the output directly into the host's secret field; do not commit it.
4. In **Environment**, add the following as protected environment variables:
   - `FLASK_ENV` = `production`
   - `SECRET_KEY` = a newly generated random value
   - `DATABASE_URL` = the managed PostgreSQL URI (with required SSL mode)
   - SMTP variables for learner email verification/login OTP and invoice email, if enabled
   - Twilio variables for production admin OTP, if admin access is enabled
   - `ADMIN_REGISTRY_PATH` = `/etc/secrets/admins.json` when using a secret file
   - Optional platform feedback synthesis keys: `GEMINI_API_KEY`/`GEMINI_FEEDBACK_MODEL`, or `HF_TOKEN`/`HF_FEEDBACK_MODEL`
5. Under **Environment → Secret Files**, upload `admins.json` if enabling admins. Keep its contents private and ensure the configured path exactly matches the mounted file path. Confirm its permissions meet the app's owner-only file check before relying on staff login.
6. Save settings and deploy. Inspect the build and startup logs for missing environment variables, database errors, or failed external-service configuration.
7. Visit the HTTPS service URL. Verify the landing page, user registration email OTP, student login, a basic tutor/quiz flow with a learner-configured AI key, and admin password-plus-SMS-OTP if configured.
8. Verify database backups and restores, log alerts, service availability, and upload persistence before inviting users.

### Free deployment caveats

- The service may sleep after a period without requests; the first request after sleep can be delayed.
- Local file changes, including local SQLite data and uploaded files, can be lost during restart, redeploy, or sleep.
- Use the external managed PostgreSQL database, not SQLite on an ephemeral host.
- Free app hosting does not make the managed database free; review each provider's current pricing, free quotas, region/network settings, and backup policy.
- A PWA service worker does not make authenticated app functionality work offline.

See the [Render Flask deployment guide](https://render.com/docs/deploy-flask), [free-instance limitations](https://render.com/docs/free), and [environment-variable/secret-file guide](https://render.com/docs/configure-environment-variables).

## Production readiness and operations

Before treating a deployment as production:

- Rotate exposed credentials and use unique values for all secrets.
- Set `FLASK_ENV=production`; use a unique `SECRET_KEY` and PostgreSQL `DATABASE_URL`.
- Require TLS to the database and HTTPS to browsers. Production sessions use secure cookies.
- Configure SMTP for student account email verification/login OTP; test delivery and retry/error behavior.
- Configure Twilio for admin OTP. Limit admin allowlist entries and phone/profile data to authorized staff.
- Add durable external storage for profile images and uploaded study documents; app-local paths are not durable on ephemeral hosts.
- Configure database backups, retention, restore drills, monitoring, error reporting, and operational alerts.
- Review rate limits and abuse protection at the proxy/application layers, including AI-generation and external Judge0 calls.
- Review privacy notices and data-retention/deletion policies for user content, provider credentials, uploads, feedback, and issue reports.
- Establish an explicit, reviewed schema migration process before non-additive database changes.
- Integrate a real payment provider and verify payment lifecycle/webhook handling before offering paid subscriptions.
- Review applicable privacy, education, consumer, and data-protection requirements for the jurisdictions where you operate.

The application currently initializes tables at startup; it is not a complete automated deployment/migration pipeline. Treat startup schema changes as a release risk and validate them against a restored staging copy before production rollout.

## Data, privacy, and third parties

### Stored application data

Depending on use, the application database can hold:

- Student account identifiers, password hashes, profile/preferences, theme, and plan state.
- AI provider/model selection and user-supplied provider API key data.
- Learning sessions, tutor conversation history, notes, quiz questions/answers, assessment scores, confidence ratings, mastery, and misconceptions.
- Attendance/activity records, review schedules, recall-test history, game scores/usage, calendar events, token balances/ledger, and rewards.
- Feedback ratings and private optional written comments.
- User-submitted issue reports and status history.
- Admin OTP/audit records, subscription/demo-checkout records, and application policy/settings.

Tutor prompts and uploaded content may be sent to the AI provider selected by the learner. Practice Code submissions are sent to Judge0. Admin feedback synthesis sends selected recent comments to the configured AI provider only after a staff member requests it. Each service has its own terms and privacy practices.

Uploaded session documents are associated with a learner/session and are removed when the session is ended/deleted through the relevant flow. Profile images and files are stored on the app filesystem by the current implementation; deploy with persistent/object storage and backup controls if those files must survive.

Feedback ratings may be aggregated publicly after the minimum sample threshold. Individual written comments are not published in the public summary. Academic leaderboard rows use anonymized labels rather than learner names.

Do not submit passwords, API keys, payment details, government identifiers, or other sensitive personal data in tutor prompts, feedback comments, study-room chat, or issue reports.

### Third-party services and browser libraries

- AI requests: provider selected by the learner; admin feedback synthesis can use Gemini or Hugging Face.
- Judge0 CE: Practice Code execution.
- Twilio: production mobile OTP for the staff console.
- SMTP provider: user email verification/login OTP and optional invoice email.
- CDN libraries may include Chart.js, math.js, MathJax, Marked.js, Lucide, CodeMirror, Animate.css, and Google Fonts. CDN features require internet access.

Third-party endpoints can change, be rate-limited, charge usage fees, or be unavailable. Confirm their current documentation and terms before production use.

## Development and validation

There is no frontend package-manager build step. The main runtime requirements are in `requirements.txt`.

Useful checks from the repository root:

```bash
python -m compileall -q app
node --check static/js/main.js
node --check static/js/landing.js
node --check static/js/rooms.js
node --check static/js/pwa.js
git diff --check
```

These commands check Python bytecode compilation, JavaScript parsing, and patch whitespace; they are not a substitute for feature tests, browser testing, security review, or PostgreSQL staging verification. If a test suite is added, run the focused tests for changed routes and models, then the full suite before release.

## Known limitations

- Billing and checkout are simulated and must not be treated as real payment collection.
- The AI is probabilistic; output can be wrong, empty, or malformed. Verify important answers and assessment feedback.
- User provider keys are stored in the application database. Production must apply appropriate database access, backup, encryption-at-rest, and secrets-retention controls.
- Startup `create_all()` and additive column setup do not constitute a full schema migration strategy.
- Free/ephemeral hosting is unsuitable for durable uploads and uninterrupted production service.
- Calendar reminders require an open app page; they are not guaranteed after the app is closed.
- Browser autoplay policy can prevent music from resuming without user interaction.
- PWA offline support is limited to selected static resources and a fallback page; there is no offline login, AI, chat, quiz, or data synchronization.
- Retention curves, mastery, confidence, and time measurements are educational approximations and should be read with their sample sizes and limitations.
