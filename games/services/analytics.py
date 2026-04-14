from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.db.models import Avg, Count, Q
from django.utils import timezone

from games.models import EscapeRoom, GameSession, HintEvent, Puzzle, PuzzleAttempt


@dataclass(frozen=True)
class AnalyticsEngine:
    """
    ORM-powered analytics used by the ERIS dashboard/templates.
    Returns JSON-serializable Python primitives (lists/dicts/numbers/strings).
    """

    def puzzle_difficulty_report(self) -> list[dict[str, Any]]:
        # Avg solve time for completed attempts; also compare to expected_time
        qs = (
            Puzzle.objects.all()
            .annotate(
                attempts=Count("puzzleattempt", distinct=True),
                completed_attempts=Count("puzzleattempt", filter=Q(puzzleattempt__completed=True), distinct=True),
                avg_hints=Avg("puzzleattempt__hints_used"),
            )
            .values(
                "id",
                "name",
                "room__name",
                "expected_time",
                "difficulty",
                "attempts",
                "completed_attempts",
                "avg_hints",
            )
        )

        # We compute avg solve time in python because SQLite can't easily do (end-start) as seconds portably
        results: list[dict[str, Any]] = []
        for row in qs:
            puzzle_id = row["id"]
            attempts = (
                PuzzleAttempt.objects.filter(puzzle_id=puzzle_id, completed=True, end_time__isnull=False)
                .values_list("start_time", "end_time")
            )
            durations = [(end - start).total_seconds() for start, end in attempts]
            avg_solve = (sum(durations) / len(durations)) if durations else 0.0
            expected = float(row["expected_time"] or 0)
            ratio = (avg_solve / expected) if expected > 0 else 0.0

            results.append(
                {
                    "puzzle_id": puzzle_id,
                    "puzzle": row["name"],
                    "room": row["room__name"],
                    "difficulty": row["difficulty"],
                    "expected_seconds": int(expected),
                    "avg_solve_seconds": int(avg_solve),
                    "avg_vs_expected_ratio": round(ratio, 2),
                    "attempts": int(row["attempts"] or 0),
                    "completed_attempts": int(row["completed_attempts"] or 0),
                    "completion_rate": round(
                        (float(row["completed_attempts"] or 0) / float(row["attempts"] or 1)), 2
                    ),
                    "avg_hints": round(float(row["avg_hints"] or 0.0), 2),
                }
            )

        # Sort by ratio descending (hardest / slowest vs expected)
        return sorted(results, key=lambda r: r["avg_vs_expected_ratio"], reverse=True)

    def room_performance(self) -> list[dict[str, Any]]:
        rooms = EscapeRoom.objects.all()
        out: list[dict[str, Any]] = []

        for room in rooms:
            sessions = GameSession.objects.filter(room=room, active=False, end_time__isnull=False)
            total = sessions.count()
            success_rate = sessions.filter(success=True).count() / max(1, total)
            avg_hints = sessions.aggregate(avg=Avg("hints_given"))["avg"] or 0.0

            # avg duration in minutes
            times = sessions.values_list("start_time", "end_time")
            durations_min = [(end - start).total_seconds() / 60 for start, end in times if end and start]
            avg_duration = (sum(durations_min) / len(durations_min)) if durations_min else 0.0

            out.append(
                {
                    "room_id": room.id,
                    "room": room.name,
                    "difficulty": room.difficulty,
                    "max_time": room.max_time,
                    "sessions": total,
                    "success_rate": round(success_rate, 2),
                    "avg_hints": round(float(avg_hints), 2),
                    "avg_duration_minutes": round(avg_duration, 1),
                }
            )

        return sorted(out, key=lambda r: (r["difficulty"], -r["success_rate"]))

    def team_size_analysis(self) -> list[dict[str, Any]]:
        # Build in python (M2M count across DBs can be awkward without extra joins).
        sessions = GameSession.objects.filter(active=False).select_related("team")
        buckets: dict[int, list[bool]] = {}
        for s in sessions:
            size = s.team.players.count()
            buckets.setdefault(size, []).append(bool(s.success))

        out = []
        for size, outcomes in sorted(buckets.items(), key=lambda x: x[0]):
            success_rate = (sum(1 for o in outcomes if o) / max(1, len(outcomes))) if outcomes else 0.0
            out.append({"team_size": size, "sessions": len(outcomes), "success_rate": round(success_rate, 2)})
        return out

    def hint_timing_analysis(self, bucket_minutes: int = 5, max_minutes: int = 90) -> list[dict[str, Any]]:
        # Bucket hint events by minutes since session start.
        events = (
            HintEvent.objects.select_related("session")
            .filter(session__active=False)
            .values_list("session__start_time", "timestamp")
        )

        buckets: dict[int, int] = {m: 0 for m in range(0, max_minutes + 1, bucket_minutes)}
        for start, ts in events:
            if not start or not ts:
                continue
            minutes = int((ts - start).total_seconds() / 60)
            minutes = max(0, min(max_minutes, minutes))
            bucket = (minutes // bucket_minutes) * bucket_minutes
            buckets[bucket] = buckets.get(bucket, 0) + 1

        return [{"minute_bucket": k, "hint_events": v} for k, v in sorted(buckets.items(), key=lambda x: x[0])]

    def bottleneck_puzzles(self, top_n: int = 8) -> list[dict[str, Any]]:
        report = self.puzzle_difficulty_report()
        # High ratio + high avg hints is a strong bottleneck indicator
        scored = []
        for r in report:
            score = (r["avg_vs_expected_ratio"] * 0.7) + (float(r["avg_hints"]) * 0.1) + (r["completion_rate"] * -0.2)
            scored.append((score, r))
        return [r for _, r in sorted(scored, key=lambda x: x[0], reverse=True)[:top_n]]

    def game_balance_score(self, room: EscapeRoom) -> dict[str, Any]:
        sessions = GameSession.objects.filter(room=room, active=False, end_time__isnull=False)
        total = sessions.count()
        if total == 0:
            return {"room_id": room.id, "room": room.name, "balance_score": 0.0, "notes": "No sessions"}

        success_rate = sessions.filter(success=True).count() / max(1, total)
        avg_hints = float(sessions.aggregate(avg=Avg("hints_given"))["avg"] or 0.0)

        durations = [
            (end - start).total_seconds()
            for start, end in sessions.values_list("start_time", "end_time")
            if start and end
        ]
        if not durations:
            return {"room_id": room.id, "room": room.name, "balance_score": 0.0, "notes": "No durations"}

        avg_dur = sum(durations) / len(durations)
        var = sum((d - avg_dur) ** 2 for d in durations) / max(1, len(durations))
        std = var**0.5

        # Normalize terms into 0..1-ish bands and combine
        # - ideal success around 0.65
        success_term = max(0.0, 1.0 - abs(success_rate - 0.65) / 0.65)
        # - lower variance better; normalize by max_time
        max_seconds = room.max_time * 60
        variance_term = max(0.0, 1.0 - min(1.0, (std / max(1.0, max_seconds))))
        # - fewer hints tends to mean less intervention; but too low might mean too easy; keep gentle penalty
        hint_term = max(0.0, 1.0 - min(1.0, avg_hints / 12.0))

        balance = (0.45 * success_term) + (0.35 * variance_term) + (0.20 * hint_term)
        return {
            "room_id": room.id,
            "room": room.name,
            "difficulty": room.difficulty,
            "sessions": total,
            "success_rate": round(success_rate, 2),
            "avg_hints": round(avg_hints, 2),
            "duration_std_minutes": round(std / 60.0, 1),
            "balance_score": round(balance, 3),
        }

    def session_summary(self, session: GameSession) -> dict[str, Any]:
        attempts = (
            PuzzleAttempt.objects.filter(session=session)
            .select_related("puzzle")
            .order_by("puzzle__order")
        )
        hint_events = HintEvent.objects.filter(session=session).select_related("puzzle").order_by("timestamp")

        duration_min = 0.0
        if session.end_time and session.start_time:
            duration_min = (session.end_time - session.start_time).total_seconds() / 60

        return {
            "session_id": session.id,
            "team": session.team.name,
            "room": session.room.name,
            "active": session.active,
            "success": session.success,
            "start_time": session.start_time,
            "end_time": session.end_time,
            "duration_minutes": round(duration_min, 1),
            "hints_given": session.hints_given,
            "attempts": [
                {
                    "puzzle": a.puzzle.name,
                    "order": a.puzzle.order,
                    "expected_seconds": a.puzzle.expected_time,
                    "start_time": a.start_time,
                    "end_time": a.end_time,
                    "completed": a.completed,
                    "hints_used": a.hints_used,
                    "duration_seconds": int((a.end_time - a.start_time).total_seconds())
                    if a.start_time and a.end_time
                    else None,
                }
                for a in attempts
            ],
            "hint_events": [
                {
                    "timestamp": h.timestamp,
                    "puzzle": h.puzzle.name,
                    "auto_suggested": h.auto_suggested,
                    "accepted": h.accepted,
                    "hint_text": h.hint_text,
                    "minute": int((h.timestamp - session.start_time).total_seconds() / 60)
                    if h.timestamp and session.start_time
                    else None,
                }
                for h in hint_events
            ],
        }

    def recent_active_snapshot(self) -> dict[str, Any]:
        now = timezone.now()
        active_sessions = GameSession.objects.filter(active=True).count()
        hints_last_30m = HintEvent.objects.filter(timestamp__gte=now - timedelta(minutes=30)).count()
        return {"active_sessions": active_sessions, "hints_last_30m": hints_last_30m}

