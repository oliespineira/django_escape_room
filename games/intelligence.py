from django.utils import timezone
from django.db.models import Avg
from .models import GameSession, PuzzleAttempt

class QueueManager:
    def __init__(self):
        self.weights ={
            'stuck':0.5,
            'fairness':0.25,
            'urgency': 0.15,
            'preference':0.1,
        }

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
        if not session.current_puzzle:
            return 0
        attempt= PuzzleAttempt.objects.filter(
            session=session, puzzle=session.current_puzzle, completed=False
        ).first()
        if not attempt:
            return 0
        elapsed= (timezone.now()- attempt.start_time).total_seconds()
        expected = session.current_puzzle.expected_time
        if expected ==0:
            return 0
        return (elapsed-expected)/expected
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
