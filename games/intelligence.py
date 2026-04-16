import random
from dataclasses import dataclass
from typing import Any

from django.db.models import Avg, Count, Min
from django.utils import timezone

from .models import EscapeRoom, GameSession, HintEvent, Puzzle, PuzzleAttempt, Team

class QueueManager:
    def __init__(self):
        self.weights ={
            'stuck':0.5,
            'fairness':0.25,
            'urgency': 0.15,
            'preference':0.1,
        }

    #sorts from highest to lowest priority.
    def rank_sessions(self, sessions):
        scores=[]
        for session in sessions:
            score= self.compute_priority(session)
            scores.append((session, score))
        return sorted(scores, key=lambda x: x[1], reverse=True)
    
    def compute_priority(self, session):
        stuck = self._stuck_score(session)
        fairness= self._fairness_deficit(session)
        urgency = self._time_urgency(session)
        preference = self._preference_boost(session)
        priority =(
            self.weights['stuck']* stuck +
            self.weights['fairness']*fairness +
            self.weights['urgency']*urgency +
            self.weights['preference']*preference 

        )
        return max(0, min(1, priority))
    def _stuck_score(self, session):
        if session.current_puzzle is None:
            return 0
        attempt = PuzzleAttempt.objects.filter(
            session=session,
            puzzle=session.current_puzzle,
            completed=False
        ).first()
        if not attempt:
            return 0
        elapsed = (timezone.now() - attempt.start_time).total_seconds()
        expected = session.current_puzzle.expected_time
        if expected == 0:
            return 0
        return max(0.0, (elapsed - expected) / expected)  # ← clamp: never negative
    def _fairness_deficit(self, session):
        avg = GameSession.objects.filter(active=True).aggregate(
            Avg('hints_given')
        )['hints_given__avg'] or 0
        deficit = (avg - session.hints_given) / max(1, avg)
        return max(0, deficit)

    def _time_urgency(self, session):
        elapsed = (timezone.now() - session.start_time).total_seconds()
        total = session.room.max_time * 60
        remaining = total - elapsed
        if remaining <= 0:
            return 1.0
        return max(0, min(1, 1 - (remaining / total)))

    def _preference_boost(self, session):
        pref_map = {'none': 0.5, 'low': 0.8, 'normal': 1.0, 'frequent': 1.2}
        players = session.team.players.all()
        scores = [pref_map.get(p.hint_preference, 1.0) for p in players]
        return sum(scores) / max(1, len(scores))


class HintRecommender:
    def suggest_hint(self, session):
        if not session.current_puzzle:
            return {'action': 'wait', 'reason': 'No active puzzle', 'confidence': 0.5}
        attempt = PuzzleAttempt.objects.filter(
            session=session, puzzle=session.current_puzzle, completed=False
        ).first()
        if not attempt:
            return {'action': 'wait', 'reason': 'Puzzle attempt not started', 'confidence': 0.3}
        elapsed = (timezone.now() - attempt.start_time).total_seconds()
        expected = session.current_puzzle.expected_time
        ratio = elapsed / expected if expected > 0 else 1
        if ratio > 1.5:
            return {
                'action': 'hint',
                'reason': f'Team stuck for {int(elapsed)}s (expected {expected}s)',
                'confidence': 0.9
            }
        elif ratio > 1.0:
            return {
                'action': 'monitor',
                'reason': f'Slightly over expected time ({ratio:.1f}x)',
                'confidence': 0.6
            }
        return {'action': 'wait', 'reason': 'Team is on track', 'confidence': 0.8}


class FairnessEngine:
    """
    Fairness metrics across sessions: avoid over/under-hinting.
    """

    def fairness_report(self) -> dict[str, Any]:
        active = GameSession.objects.filter(active=True)
        avg_hints = float(active.aggregate(avg=Avg("hints_given"))["avg"] or 0.0)

        first_hint = (
            HintEvent.objects.filter(session__active=True)
            .values("session_id")
            .annotate(first=Min("timestamp"))
        )
        # Map: session_id -> minutes to first hint
        mins_to_first: list[float] = []
        for row in first_hint:
            session = active.filter(id=row["session_id"]).values_list("start_time", flat=True).first()
            if session and row["first"]:
                mins_to_first.append((row["first"] - session).total_seconds() / 60.0)

        avg_time_to_first = (sum(mins_to_first) / len(mins_to_first)) if mins_to_first else 0.0

        hints_per_puzzle = (
            HintEvent.objects.filter(session__active=True)
            .values("puzzle__name")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        return {
            "active_sessions": active.count(),
            "avg_hints_active": round(avg_hints, 2),
            "avg_time_to_first_hint_minutes": round(avg_time_to_first, 1),
            "hints_per_puzzle": [{"puzzle": r["puzzle__name"], "hint_events": r["count"]} for r in hints_per_puzzle],
        }

    def session_fairness_score(self, session: GameSession) -> float:
        # Score 0..1 where 1 is most "fair/normal" relative to active average
        avg = GameSession.objects.filter(active=True).aggregate(Avg("hints_given"))["hints_given__avg"] or 0.0
        avg = float(avg)
        if avg <= 0.01:
            return 1.0
        delta = abs(session.hints_given - avg) / avg
        return max(0.0, min(1.0, 1.0 - delta))

    def detect_outliers(self, z_threshold: float = 1.2) -> list[dict[str, Any]]:
        active = list(GameSession.objects.filter(active=True).select_related("team", "room"))
        if not active:
            return []
        hints = [s.hints_given for s in active]
        mean = sum(hints) / len(hints)
        var = sum((h - mean) ** 2 for h in hints) / max(1, len(hints))
        std = var**0.5
        if std <= 0.01:
            return []
        out = []
        for s in active:
            z = (s.hints_given - mean) / std
            if abs(z) >= z_threshold:
                out.append(
                    {
                        "session_id": s.id,
                        "team": s.team.name,
                        "room": s.room.name,
                        "hints_given": s.hints_given,
                        "z": round(z, 2),
                    }
                )
        return sorted(out, key=lambda r: abs(r["z"]), reverse=True)


@dataclass(frozen=True)
class SimulationResult:
    strategy: str
    success_rate: float
    avg_hints: float
    avg_duration_minutes: float


class SimulationMode:
    """
    Run synthetic sessions to compare hint strategies without creating DB rows.
    """

    def simulate_session(
        self,
        room: EscapeRoom,
        team: Team | None = None,
        strategy: str = "balanced",
        runs: int = 50,
    ) -> dict[str, Any]:
        puzzles = list(Puzzle.objects.filter(room=room).order_by("order"))
        if not puzzles:
            return {"room": room.name, "strategy": strategy, "runs": 0, "error": "Room has no puzzles"}

        team_profile = self._team_profile(team) if team else {"skill": 0.5, "hint_pref": "normal"}
        params = self._strategy_params(strategy)

        successes = 0
        total_hints = 0
        total_duration = 0.0

        for _ in range(runs):
            duration_seconds = 0
            hints = 0
            for p in puzzles:
                # baseline duration from expected_time and skill
                skill_factor = 1.18 - (0.40 * team_profile["skill"])
                noise = random.uniform(0.75, 1.45)
                d = p.expected_time * skill_factor * noise

                # strategy adds/subtracts time and changes hint propensity
                over_ratio = max(0.0, (d - p.expected_time) / max(1.0, p.expected_time))
                hint_pref_factor = {"none": 0.2, "low": 0.6, "normal": 1.0, "frequent": 1.35}.get(
                    team_profile["hint_pref"], 1.0
                )
                expected_hints = (
                    params["hint_base"]
                    + params["hint_scale"] * over_ratio
                    + (0.15 * hint_pref_factor)
                )
                h = int(round(min(3, max(0, random.gauss(expected_hints, 0.6)))))

                # hints reduce time depending on strategy effectiveness
                d = max(30.0, d * (1.0 - params["hint_time_reduction"] * h))

                duration_seconds += d
                hints += h

            total_hints += hints
            total_duration += duration_seconds / 60.0

            # success depends on finishing within max_time and room difficulty
            base_success = {"easy": 0.78, "medium": 0.62, "hard": 0.48}.get(room.difficulty, 0.6)
            strategy_boost = params["success_boost"]
            skill_boost = (team_profile["skill"] - 0.5) * 0.25
            within_time = duration_seconds <= (room.max_time * 60)
            p_success = base_success + strategy_boost + skill_boost + (0.08 if within_time else -0.22)
            p_success = max(0.05, min(0.95, p_success))
            successes += 1 if random.random() < p_success else 0

        result = SimulationResult(
            strategy=strategy,
            success_rate=successes / max(1, runs),
            avg_hints=total_hints / max(1, runs),
            avg_duration_minutes=total_duration / max(1, runs),
        )
        return {
            "room_id": room.id,
            "room": room.name,
            "difficulty": room.difficulty,
            "strategy": result.strategy,
            "runs": runs,
            "success_rate": round(result.success_rate, 2),
            "avg_hints": round(result.avg_hints, 2),
            "avg_duration_minutes": round(result.avg_duration_minutes, 1),
        }

    def _strategy_params(self, strategy: str) -> dict[str, float]:
        strategy = (strategy or "balanced").lower()
        if strategy == "aggressive":
            return {"hint_base": 0.6, "hint_scale": 1.1, "hint_time_reduction": 0.10, "success_boost": 0.05}
        if strategy == "conservative":
            return {"hint_base": 0.2, "hint_scale": 0.55, "hint_time_reduction": 0.06, "success_boost": -0.03}
        return {"hint_base": 0.4, "hint_scale": 0.85, "hint_time_reduction": 0.08, "success_boost": 0.0}

    def _team_profile(self, team: Team | None) -> dict[str, Any]:
        if not team:
            return {"skill": 0.5, "hint_pref": "normal"}
        players = list(team.players.all())
        if not players:
            return {"skill": 0.5, "hint_pref": "normal"}

        exp_weights = {"beginner": 0.0, "intermediate": 0.5, "expert": 1.0}
        skill = sum(exp_weights.get(p.experience_level, 0.5) for p in players) / len(players)

        hint_rank = {"none": 0, "low": 1, "normal": 2, "frequent": 3}
        avg_hint_rank = sum(hint_rank.get(p.hint_preference, 2) for p in players) / len(players)
        hint_pref = min(hint_rank, key=lambda k: abs(hint_rank[k] - avg_hint_rank))
        return {"skill": skill, "hint_pref": hint_pref}
