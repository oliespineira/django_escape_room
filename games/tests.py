from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from games.intelligence import HintRecommender, QueueManager, SimulationMode
from games.models import (
    EscapeRoom,
    GameSession,
    Player,
    Puzzle,
    PuzzleAttempt,
    Team,
)
from games.services.analytics import AnalyticsEngine


class ModelRelationshipTests(TestCase):
    def test_team_players_m2m(self):
        p = Player.objects.create(name="A", experience_level="beginner", hint_preference="normal")
        t = Team.objects.create(name="T1")
        t.players.add(p)
        self.assertEqual(t.players.count(), 1)


class HintRecommenderTests(TestCase):
    def setUp(self):
        self.room = EscapeRoom.objects.create(
            name="R1",
            description="d",
            difficulty="medium",
            max_time=60,
            theme="t",
        )
        self.puzzle = Puzzle.objects.create(
            room=self.room,
            name="P1",
            description="pd",
            difficulty=5,
            expected_time=600,
            order=1,
        )
        self.team = Team.objects.create(name="Team")
        self.session = GameSession.objects.create(
            team=self.team,
            room=self.room,
            current_puzzle=self.puzzle,
            active=True,
        )

    def test_on_track_returns_wait(self):
        PuzzleAttempt.objects.filter(session=self.session).delete()
        attempt = PuzzleAttempt.objects.create(session=self.session, puzzle=self.puzzle, completed=False)
        attempt.start_time = timezone.now() - timedelta(seconds=300)
        attempt.save(update_fields=["start_time"])
        rec = HintRecommender().suggest_hint(self.session)
        self.assertEqual(rec["action"], "wait")

    def test_stuck_returns_hint(self):
        PuzzleAttempt.objects.filter(session=self.session).delete()
        attempt = PuzzleAttempt.objects.create(session=self.session, puzzle=self.puzzle, completed=False)
        attempt.start_time = timezone.now() - timedelta(seconds=1200)
        attempt.save(update_fields=["start_time"])
        rec = HintRecommender().suggest_hint(self.session)
        self.assertEqual(rec["action"], "hint")


class QueueManagerTests(TestCase):
    def setUp(self):
        self.room = EscapeRoom.objects.create(
            name="R1",
            description="d",
            difficulty="medium",
            max_time=60,
            theme="t",
        )
        self.p1 = Puzzle.objects.create(
            room=self.room,
            name="P1",
            description="pd",
            difficulty=5,
            expected_time=600,
            order=1,
        )
        self.team = Team.objects.create(name="Team")

    def test_higher_stuck_ranks_first(self):
        s_fast = GameSession.objects.create(
            team=self.team,
            room=self.room,
            current_puzzle=self.p1,
            active=True,
        )
        s_slow = GameSession.objects.create(
            team=self.team,
            room=self.room,
            current_puzzle=self.p1,
            active=True,
        )
        a_fast = PuzzleAttempt.objects.create(session=s_fast, puzzle=self.p1, completed=False)
        a_fast.start_time = timezone.now() - timedelta(seconds=100)
        a_fast.save(update_fields=["start_time"])
        a_slow = PuzzleAttempt.objects.create(session=s_slow, puzzle=self.p1, completed=False)
        a_slow.start_time = timezone.now() - timedelta(seconds=2000)
        a_slow.save(update_fields=["start_time"])

        ranked = QueueManager().rank_sessions([s_fast, s_slow])
        self.assertEqual(ranked[0][0].id, s_slow.id)


class AnalyticsEngineTests(TestCase):
    def test_puzzle_difficulty_report_empty(self):
        self.assertEqual(AnalyticsEngine().puzzle_difficulty_report(), [])


class SimulationModeTests(TestCase):
    def test_simulate_returns_keys(self):
        room = EscapeRoom.objects.create(
            name="R1",
            description="d",
            difficulty="easy",
            max_time=60,
            theme="t",
        )
        Puzzle.objects.create(room=room, name="P1", description="d", difficulty=3, expected_time=300, order=1)
        out = SimulationMode().simulate_session(room, team=None, strategy="balanced", runs=5)
        self.assertIn("success_rate", out)
        self.assertEqual(out["runs"], 5)


class APITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.room = EscapeRoom.objects.create(
            name="R1",
            description="d",
            difficulty="medium",
            max_time=60,
            theme="t",
        )
        self.puzzle = Puzzle.objects.create(
            room=self.room,
            name="P1",
            description="pd",
            difficulty=5,
            expected_time=600,
            order=1,
        )
        self.team = Team.objects.create(name="Team")
        self.session = GameSession.objects.create(
            team=self.team,
            room=self.room,
            current_puzzle=self.puzzle,
            active=True,
        )

    def test_hint_endpoint(self):
        url = f"/api/sessions/{self.session.id}/hint/"
        r = self.client.post(url, {"auto_suggested": False, "hint_text": "x"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.session.refresh_from_db()
        self.assertEqual(self.session.hints_given, 1)

    def test_hint_without_puzzle_bad_request(self):
        self.session.current_puzzle = None
        self.session.save(update_fields=["current_puzzle"])
        url = f"/api/sessions/{self.session.id}/hint/"
        r = self.client.post(url, {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_end_session(self):
        url = f"/api/sessions/{self.session.id}/end/"
        r = self.client.post(url, {"success": True}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.session.refresh_from_db()
        self.assertFalse(self.session.active)
        self.assertTrue(self.session.success)

    def test_queue_includes_fairness(self):
        r = self.client.get("/api/queue/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("fairness", r.json())
