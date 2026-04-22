# ERIS - Escape Room Intelligence System

ERIS is a Django platform for Game Masters to run multiple escape-room sessions in parallel.  
It combines a real-time operations dashboard, a priority queue for intervention decisions, puzzle dependency tracking, and analytics/simulation tooling.

---

## What The Project Does

- Runs **GM operations workflows**: setup, start/pause/end sessions, issue hints, mark puzzle completion, inspect session timeline.
- Maintains a **ranked live queue** using stuckness + fairness + urgency + team hint preference.
- Supports **puzzle dependency graphs** with unlock logic based on outputs (AND/OR conditions).
- Tracks **fairness metrics** and outliers across active sessions.
- Provides **post-session analytics** (difficulty, bottlenecks, room performance, team-size success, hint timing).
- Includes a **simulation mode** to compare conservative/balanced/aggressive hint strategies without touching production session rows.
- Exposes a **DRF API** for sessions, puzzles, teams, and queue state.

---

## Priority Formula

```
Priority = 0.50 * StuckScore
         + 0.25 * FairnessDeficit
         + 0.15 * TimeUrgency
         + 0.10 * TeamPreferenceBoost
```

- `StuckScore`: how far a team is beyond expected puzzle time (never negative).
- `FairnessDeficit`: how under-hinted the team is vs active-session average.
- `TimeUrgency`: proximity to room time limit.
- `TeamPreferenceBoost`: aggregate player hint preference in the team.

---

## Core Apps

- `escape_room/`: project settings + root URL routing + WSGI/ASGI.
- `games/`: domain logic (models, views, API, intelligence engines, analytics service, admin, templates, static assets, seed command).

---

## Data Model (Current)

The project currently uses 10 core domain entities:

- `Player`
- `Team` (M2M with `Player`)
- `EscapeRoom`
- `Puzzle` (belongs to `EscapeRoom`)
- `GameSession` (team in room, lifecycle state, timers, current puzzle)
- `PuzzleAttempt` (per-session per-puzzle run)
- `HintEvent` (logged hints)
- `PuzzleOutput` (outputs produced by puzzle completion)
- `PuzzleDependency` (required outputs to unlock a puzzle; supports AND/OR)
- `OutputAcquired` (session-level acquired output ledger)

High-level flow:

```
Player <-> Team -> GameSession -> EscapeRoom -> Puzzle
                        |             |          |
                        |             |          +-> PuzzleOutput
                        |             |          +-> PuzzleDependency (requires PuzzleOutput)
                        +-> PuzzleAttempt
                        +-> HintEvent
                        +-> OutputAcquired (PuzzleOutput)
```

---

## Web Routes

- `/` -> redirects to `/dashboard/`
- `/dashboard/` -> queue + recommendations + fairness snapshot
- `/setup/` -> assign teams/players to rooms and create pending sessions
- `/sessions/<id>/` -> session timeline, attempts, acquired outputs, puzzle graph
- `/analytics/` -> reports/charts
- `/simulation/` -> strategy simulations
- `/rooms/`, `/rooms/create/`, `/rooms/<id>/`, `/rooms/<id>/edit/`
- `/players/`, `/players/create/`, `/players/<id>/edit/`, `/players/<id>/delete/`
- `/accounts/login/`, `/accounts/logout/`, `/accounts/register/`
- `/admin/`

---

## API Routes

All API endpoints require authentication.

Base resources (DRF `ModelViewSet`, full CRUD):

- `/api/sessions/`
- `/api/puzzles/`
- `/api/teams/`

Custom session actions:

- `POST /api/sessions/{id}/start/` - start pending session or resume paused session
- `POST /api/sessions/{id}/pause/` - pause active session
- `POST /api/sessions/{id}/hint/` - log hint and increment counters
- `POST /api/sessions/{id}/complete-puzzle/` - complete current puzzle and auto-advance
- `POST /api/sessions/{id}/end/` - end session with success/failure flag

Queue/fairness endpoint:

- `GET /api/queue/` - ranked queue plus fairness report and outlier detection

---

## Quick Start

### 1) Clone

```bash
git clone https://github.com/oliespineira/django_escape_room.git
cd django_escape_room
```

### 2) Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate      # macOS / Linux
venv\Scripts\activate         # Windows
```

### 3) Install dependencies

```bash
pip install -r requirements.txt
```

### 4) Migrate

```bash
python manage.py migrate
```

### 5) Seed demo data (optional but recommended)

```bash
python manage.py seed_data --clear
```

Useful seed options:

```bash
python manage.py seed_data --players 30 --teams 10 --rooms 4 --sessions 25 --active-sessions 8 --days 14
```

### 6) Create GM account

```bash
python manage.py createsuperuser
```

### 7) Run server

```bash
python manage.py runserver
```

Open `http://127.0.0.1:8000` (redirects to login if not authenticated).

---

## Running Tests

```bash
python manage.py test games --verbosity=2
```

Current test suite includes **22 tests** covering:

- model relationships/defaults/ordering
- queue algorithm behavior + edge cases
- hint recommender
- analytics empty case
- simulation output
- API actions and auth requirements

---

## Project Structure

```
django_escape_room/
|-- escape_room/
|   |-- settings.py
|   |-- urls.py
|   |-- asgi.py
|   `-- wsgi.py
|-- games/
|   |-- models.py
|   |-- views.py
|   |-- urls.py
|   |-- api_urls.py
|   |-- serializers.py
|   |-- intelligence.py
|   |-- admin.py
|   |-- tests.py
|   |-- services/
|   |   `-- analytics.py
|   |-- management/commands/
|   |   `-- seed_data.py
|   |-- templates/
|   |   |-- registration/
|   |   |   |-- login.html
|   |   |   `-- register.html
|   |   `-- games/
|   |       |-- base.html
|   |       |-- dashboard.html
|   |       |-- setup.html
|   |       |-- analytics.html
|   |       |-- simulation.html
|   |       |-- players.html
|   |       |-- rooms.html
|   |       |-- room_create.html
|   |       |-- room_edit.html
|   |       |-- room_detail.html
|   |       `-- session_detail.html
|   `-- static/games/
|       |-- css/style.css
|       `-- js/
|           |-- dashboard.js
|           `-- charts.js
|-- manage.py
`-- requirements.txt
```

---

## Tech Stack

- Backend: Django 6.0.4, Django REST Framework 3.17.1
- Database (default): SQLite
- Frontend: Django templates + Bootstrap + Chart.js
- Data libs: NumPy, Pandas
- Tests: Django `TestCase`, DRF `APIClient`

---

## Development Notes

- Authentication is enforced with `LoginRequiredMiddleware` for pages and `IsAuthenticated` for API endpoints.
- Register route is publicly accessible (`/accounts/register/`) and auto-login is performed after successful signup.
- Session lifecycle states: `pending -> active -> paused -> active -> ended`.

### Current local settings are development-only

In `escape_room/settings.py`, defaults are intentionally local/dev:

- `DEBUG = True`
- `ALLOWED_HOSTS = []`
- hardcoded `SECRET_KEY`
- SQLite configured as default DB

Before deployment, externalize secrets and harden settings.

---

## Team

5-person IE University Databases project (April 2026).