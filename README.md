# ERIS — Escape Room Intelligence System

A Django-based real-time decision support platform for Game Masters (GMs).  
ERIS helps GMs manage multiple escape room sessions simultaneously by automatically prioritising which team needs help first, ensuring fair hint distribution, and generating post-game analytics.

---

## Features

- **Real-time GM Dashboard** — live queue of all active sessions, auto-refreshing every 10 seconds
- **Priority Queue Algorithm** — weighted scoring system that ranks teams by how stuck they are, fairness deficit, time urgency, and hint preference
- **Fairness Engine** — z-score outlier detection ensures no team is over- or under-hinted relative to others
- **Hint Recommender** — rule-based engine that suggests `hint`, `monitor`, or `wait` per session
- **Post-Game Analytics** — puzzle difficulty reports, bottleneck identification, room balance scores, and team size analysis
- **Simulation Mode** — compare `conservative`, `balanced`, and `aggressive` hint strategies without touching live data
- **REST API** — full DRF-powered API for sessions, teams, puzzles, and queue state
- **Authentication** — login-protected dashboard and API; only authenticated GMs can access the system

---

## Priority Score Formula

```
Priority = 0.5 × StuckScore
         + 0.25 × FairnessDeficit
         + 0.15 × TimeUrgency
         + 0.10 × TeamPreferenceBoost
```

- **StuckScore** — how much longer the team has spent on a puzzle than expected (clamped to ≥ 0)
- **FairnessDeficit** — how many fewer hints this team has received compared to the active average
- **TimeUrgency** — how close the session is to the room's time limit
- **TeamPreferenceBoost** — aggregated hint preference of all players in the team

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/oliespineira/django_escape_room.git
cd django_escape_room
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Apply migrations

```bash
python manage.py migrate
```

### 5. Seed the database with demo data

```bash
python manage.py seed_data --clear
```

### 6. Create a GM user

```bash
python manage.py createsuperuser
```

### 7. Run the development server

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000` — you will be redirected to the login page.

---

## Running Tests

```bash
python manage.py test games --verbosity=2
```

21 tests covering models, queue algorithm edge cases, hint recommender, analytics engine, simulation mode, API endpoints, and authentication.

---

## Project Structure

```
django_escape_room/
├── escape_room/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── games/
│   ├── models.py          # All 7 core entities
│   ├── views.py           # Page views (login-protected)
│   ├── api_urls.py        # REST API routes
│   ├── serializers.py     # DRF serializers
│   ├── intelligence.py    # QueueManager, HintRecommender, SimulationMode
│   ├── admin.py           # Django admin configuration
│   ├── tests.py           # 21 unit and integration tests
│   ├── services/
│   │   └── analytics.py   # AnalyticsEngine
│   ├── management/
│   │   └── commands/
│   │       └── seed_data.py
│   ├── templates/
│   │   ├── registration/
│   │   │   └── login.html
│   │   └── games/
│   │       ├── base.html
│   │       ├── dashboard.html
│   │       ├── analytics.html
│   │       ├── simulation.html
│   │       ├── rooms.html
│   │       ├── room_detail.html
│   │       └── session_detail.html
│   └── static/
│       └── games/
│           ├── css/style.css
│           └── js/dashboard.js
├── manage.py
└── requirements.txt
```

---

## API Endpoints

All endpoints require authentication.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/sessions/` | List all sessions |
| POST | `/api/sessions/` | Create a new session |
| GET | `/api/sessions/{id}/` | Session detail |
| POST | `/api/sessions/{id}/hint/` | Log a hint |
| POST | `/api/sessions/{id}/end/` | End a session |
| GET | `/api/queue/` | Ranked priority queue with fairness data |
| GET | `/api/teams/` | List all teams |
| GET | `/api/puzzles/` | List all puzzles |

---

## Data Model

```
Player ──┐
         ├──(M2M)── Team ──── GameSession ──── EscapeRoom ──── Puzzle
                                   │
                                   ├──── PuzzleAttempt ──── Puzzle
                                   └──── HintEvent      ──── Puzzle
```

---

## Tech Stack

- **Backend** — Django 6.0.4, Django REST Framework 3.17
- **Database** — SQLite (development)
- **Frontend** — Django Templates, Bootstrap 5.3, Chart.js 4.4
- **Data processing** — NumPy, Pandas
- **Testing** — Django TestCase, DRF APIClient

---

## Team

5-person university project — IE University, Databases course, April 2026.

| Role | Responsibility |
|------|---------------|
| Person 1 | Database & data modelling |
| Person 2 | Backend & REST API |
| Person 3 | Intelligence & queue algorithm |
| Person 4 | Frontend & GM dashboard |
| Person 5 | Analytics & reporting |