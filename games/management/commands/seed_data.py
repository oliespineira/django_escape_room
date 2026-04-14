import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from games.models import (
    EscapeRoom,
    GameSession,
    HintEvent,
    Player,
    Puzzle,
    PuzzleAttempt,
    Team,
)


class Command(BaseCommand):
    help = "Seed the database with realistic ERIS demo data."

    def add_arguments(self, parser):
        parser.add_argument("--players", type=int, default=30)
        parser.add_argument("--teams", type=int, default=8)
        parser.add_argument("--rooms", type=int, default=5)
        parser.add_argument("--sessions", type=int, default=120)
        parser.add_argument("--active-sessions", type=int, default=4)
        parser.add_argument("--days", type=int, default=90, help="Spread completed sessions across N past days")
        parser.add_argument("--clear", action="store_true", help="Delete existing ERIS data first")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["clear"]:
            self._clear()

        players = self._seed_players(options["players"])
        teams = self._seed_teams(options["teams"], players)
        rooms = self._seed_rooms(options["rooms"])
        puzzles_by_room = {room.id: self._seed_puzzles(room) for room in rooms}

        self._seed_sessions(
            sessions_count=options["sessions"],
            active_count=options["active_sessions"],
            days=options["days"],
            teams=teams,
            rooms=rooms,
            puzzles_by_room=puzzles_by_room,
        )

        self.stdout.write(self.style.SUCCESS("Seed complete."))

    def _clear(self):
        HintEvent.objects.all().delete()
        PuzzleAttempt.objects.all().delete()
        GameSession.objects.all().delete()
        Puzzle.objects.all().delete()
        EscapeRoom.objects.all().delete()
        Team.objects.all().delete()
        Player.objects.all().delete()

    def _seed_players(self, n):
        first_names = [
            "Ava",
            "Noah",
            "Mia",
            "Ethan",
            "Liam",
            "Zoe",
            "Aria",
            "Omar",
            "Ivy",
            "Leo",
            "Sam",
            "Nina",
            "Kai",
            "Jade",
            "Rami",
            "Sara",
            "Yara",
            "Hana",
            "Theo",
            "Luca",
        ]
        last_names = [
            "Smith",
            "Johnson",
            "Brown",
            "Garcia",
            "Martinez",
            "Nguyen",
            "Khan",
            "Patel",
            "Jones",
            "Davis",
            "Miller",
            "Wilson",
            "Taylor",
            "Anderson",
        ]

        exp_choices = ["beginner", "intermediate", "expert"]
        exp_weights = [0.55, 0.33, 0.12]

        hint_choices = ["none", "low", "normal", "frequent"]
        hint_weights_by_exp = {
            "beginner": [0.05, 0.25, 0.45, 0.25],
            "intermediate": [0.10, 0.30, 0.45, 0.15],
            "expert": [0.25, 0.40, 0.30, 0.05],
        }

        players = []
        for i in range(n):
            exp = random.choices(exp_choices, weights=exp_weights, k=1)[0]
            hint_pref = random.choices(hint_choices, weights=hint_weights_by_exp[exp], k=1)[0]
            name = f"{random.choice(first_names)} {random.choice(last_names)}"
            players.append(
                Player(
                    name=f"{name} #{i+1}",
                    experience_level=exp,
                    hint_preference=hint_pref,
                )
            )
        Player.objects.bulk_create(players)
        return list(Player.objects.all())

    def _seed_teams(self, n, players):
        random.shuffle(players)
        teams = []
        for i in range(n):
            teams.append(Team.objects.create(name=f"Team {i+1}"))

        # assign 3-5 per team, reusing if needed
        idx = 0
        for team in teams:
            size = random.randint(3, 5)
            chosen = []
            for _ in range(size):
                chosen.append(players[idx % len(players)])
                idx += 1
            team.players.add(*chosen)
        return teams

    def _seed_rooms(self, n):
        catalog = [
            {
                "name": "Haunted Mansion",
                "theme": "horror",
                "difficulty": "hard",
                "max_time": 60,
                "description": "A cursed mansion where every clue whispers back.",
            },
            {
                "name": "Cyber Heist",
                "theme": "sci-fi",
                "difficulty": "medium",
                "max_time": 60,
                "description": "Infiltrate the vault, bypass the firewall, grab the data.",
            },
            {
                "name": "Ancient Temple",
                "theme": "adventure",
                "difficulty": "medium",
                "max_time": 75,
                "description": "Decode relics and avoid traps in a forgotten temple.",
            },
            {
                "name": "Space Station Lockdown",
                "theme": "space",
                "difficulty": "hard",
                "max_time": 75,
                "description": "Restore life support before the station goes dark.",
            },
            {
                "name": "Murder Mystery",
                "theme": "mystery",
                "difficulty": "easy",
                "max_time": 60,
                "description": "Interrogate suspects and uncover the culprit.",
            },
        ]
        rooms = []
        for i in range(n):
            src = catalog[i % len(catalog)]
            rooms.append(
                EscapeRoom.objects.create(
                    name=src["name"] if i < len(catalog) else f"{src['name']} {i+1}",
                    description=src["description"],
                    difficulty=src["difficulty"],
                    max_time=src["max_time"],
                    theme=src["theme"],
                )
            )
        return rooms

    def _seed_puzzles(self, room):
        puzzle_counts = {"easy": (5, 6), "medium": (6, 7), "hard": (7, 8)}
        low, high = puzzle_counts.get(room.difficulty, (6, 7))
        count = random.randint(low, high)

        base_expected_min = {"easy": 5, "medium": 7, "hard": 9}.get(room.difficulty, 7)

        puzzles = []
        for order in range(1, count + 1):
            # expected time increases slightly by order and difficulty
            expected_minutes = base_expected_min + int(order * 0.8) + random.randint(-1, 2)
            expected_seconds = max(60, expected_minutes * 60)
            puzzles.append(
                Puzzle(
                    room=room,
                    name=f"Puzzle {order}",
                    description=f"Challenge {order} in {room.name}.",
                    difficulty=min(10, max(1, (3 if room.difficulty == 'easy' else 5 if room.difficulty == 'medium' else 7) + random.randint(-1, 2))),
                    expected_time=expected_seconds,
                    order=order,
                )
            )
        Puzzle.objects.bulk_create(puzzles)
        return list(Puzzle.objects.filter(room=room).order_by("order"))

    def _team_profile(self, team):
        exp_weights = {"beginner": 0.0, "intermediate": 0.5, "expert": 1.0}
        players = list(team.players.all())
        if not players:
            return {"skill": 0.5, "hint_pref": "normal"}

        skill = sum(exp_weights.get(p.experience_level, 0.5) for p in players) / len(players)

        hint_rank = {"none": 0, "low": 1, "normal": 2, "frequent": 3}
        avg_hint_rank = sum(hint_rank.get(p.hint_preference, 2) for p in players) / len(players)
        hint_pref = min(hint_rank, key=lambda k: abs(hint_rank[k] - avg_hint_rank))

        return {"skill": skill, "hint_pref": hint_pref, "size": len(players)}

    def _seed_sessions(self, sessions_count, active_count, days, teams, rooms, puzzles_by_room):
        # difficulty affects baseline success and time
        success_base = {"easy": 0.78, "medium": 0.62, "hard": 0.48}

        now = timezone.now()

        # Completed sessions first (historical)
        completed_count = max(0, sessions_count - active_count)
        for i in range(completed_count):
            team = random.choice(teams)
            room = random.choice(rooms)
            puzzles = puzzles_by_room[room.id]
            profile = self._team_profile(team)

            start = now - timedelta(days=random.randint(1, max(1, days)), hours=random.randint(0, 23), minutes=random.randint(0, 59))
            session = GameSession.objects.create(
                team=team,
                room=room,
                start_time=start,
                active=False,
                hints_given=0,
            )

            # simulate attempts sequentially
            cursor = start
            total_hints = 0
            for puzzle in puzzles:
                attempt = PuzzleAttempt.objects.create(session=session, puzzle=puzzle, start_time=cursor, completed=False)

                # duration: expected * (skill adjustment) * randomness
                skill_factor = 1.15 - (0.35 * profile["skill"])  # experts faster
                noise = random.uniform(0.75, 1.45)
                duration = int(puzzle.expected_time * skill_factor * noise)

                # hints scale up when duration > expected and when hint_pref high
                hint_pref_factor = {"none": 0.2, "low": 0.6, "normal": 1.0, "frequent": 1.4}[profile["hint_pref"]]
                over_ratio = max(0.0, (duration - puzzle.expected_time) / max(1, puzzle.expected_time))
                expected_hints = hint_pref_factor * (0.2 + (0.9 * over_ratio))
                hints_for_puzzle = int(round(min(3, max(0, random.gauss(expected_hints, 0.5)))))

                # record hint events, biased later in the attempt
                for _ in range(hints_for_puzzle):
                    offset = int(duration * random.uniform(0.55, 0.9))
                    HintEvent.objects.create(
                        session=session,
                        puzzle=puzzle,
                        timestamp=cursor + timedelta(seconds=offset),
                        auto_suggested=bool(random.getrandbits(1)),
                        accepted=True,
                        hint_text=random.choice(
                            [
                                "Try checking the lock mechanism again.",
                                "Look for patterns in the symbols.",
                                "What can you combine from earlier clues?",
                                "Re-read the note; one word is important.",
                            ]
                        ),
                    )
                total_hints += hints_for_puzzle

                attempt.hints_used = hints_for_puzzle
                attempt.end_time = cursor + timedelta(seconds=duration)
                attempt.completed = True
                attempt.save()
                cursor = attempt.end_time

            session.hints_given = total_hints

            # outcome depends on room difficulty, team skill, and time usage
            max_seconds = room.max_time * 60
            time_used = int((cursor - start).total_seconds())
            base = success_base.get(room.difficulty, 0.6)
            skill_boost = (profile["skill"] - 0.5) * 0.25
            overtime_penalty = -0.35 if time_used > max_seconds else 0.0
            hint_overuse_penalty = -0.08 if total_hints >= 10 else 0.0
            p_success = max(0.05, min(0.95, base + skill_boost + overtime_penalty + hint_overuse_penalty))
            success = random.random() < p_success

            # if fail, set end time around max_time; if success, actual cursor
            end_time = start + timedelta(seconds=min(time_used, max_seconds + random.randint(0, 600)))
            session.end_time = end_time
            session.success = success
            session.last_hint_time = HintEvent.objects.filter(session=session).order_by("-timestamp").values_list("timestamp", flat=True).first()
            session.current_puzzle = None
            session.save()

        # Active sessions for live dashboard demo
        for i in range(active_count):
            team = random.choice(teams)
            room = random.choice(rooms)
            puzzles = puzzles_by_room[room.id]
            profile = self._team_profile(team)

            start = now - timedelta(minutes=random.randint(5, 45))
            session = GameSession.objects.create(
                team=team,
                room=room,
                start_time=start,
                active=True,
                hints_given=0,
            )

            # pick current puzzle and start attempt earlier so it's \"in progress\"
            current = random.choice(puzzles)
            session.current_puzzle = current
            session.save()

            attempt_start = now - timedelta(seconds=int(current.expected_time * random.uniform(0.6, 1.8)))
            attempt = PuzzleAttempt.objects.create(session=session, puzzle=current, start_time=attempt_start, completed=False)

            # maybe some hints already used
            hint_pref_factor = {"none": 0.2, "low": 0.6, "normal": 1.0, "frequent": 1.4}[profile["hint_pref"]]
            hints_used = int(round(min(2, max(0, random.gauss(0.8 * hint_pref_factor, 0.7)))))
            for _ in range(hints_used):
                HintEvent.objects.create(
                    session=session,
                    puzzle=current,
                    timestamp=attempt_start + timedelta(seconds=int(current.expected_time * random.uniform(0.4, 0.9))),
                    auto_suggested=True,
                    accepted=True,
                    hint_text=random.choice(
                        [
                            "Focus on the objects that can be moved.",
                            "You may be missing a hidden compartment.",
                            "Try a different order for the steps.",
                        ]
                    ),
                )

            attempt.hints_used = hints_used
            attempt.save()

            session.hints_given = hints_used
            session.last_hint_time = HintEvent.objects.filter(session=session).order_by("-timestamp").values_list("timestamp", flat=True).first()
            session.save()
