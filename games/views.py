import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views

from .intelligence import FairnessEngine, HintRecommender, QueueManager, SimulationMode
from .models import EscapeRoom, GameSession, HintEvent, Puzzle, PuzzleAttempt, Team
from .serializers import GameSessionSerializer, PuzzleSerializer, TeamSerializer
from .services.analytics import AnalyticsEngine

from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication, BasicAuthentication

# Create your views here.
class GameSessionViewSet(viewsets.ModelViewSet):
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = GameSession.objects.all()
    serializer_class = GameSessionSerializer

    #this customises what data is returned
    def get_queryset(self):
        qs = GameSession.objects.all()
        if self.request.query_params.get('active'): #only retrieves active data
            qs = qs.filter(active=True)
        return qs
    
    @action(detail=True, methods=['post'])
    def hint(self, request, pk=None):
        session = self.get_object()
        puzzle = session.current_puzzle
        if not puzzle:
            return Response(
                {'detail': 'No current puzzle set for this session.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        HintEvent.objects.create(
            session=session,
            puzzle=puzzle,
            auto_suggested=request.data.get('auto_suggested', False),
            accepted=True,
            hint_text=request.data.get('hint_text', '')
        )
        session.hints_given += 1
        session.last_hint_time = timezone.now()
        session.save()
        attempt = PuzzleAttempt.objects.filter(
            session=session, puzzle=puzzle, completed=False
        ).first()
        if attempt:
            attempt.hints_used += 1
            attempt.save()
        return Response({'status': 'hint logged'})

    @action(detail=True, methods=['post'])
    def end(self, request, pk=None):
        session = self.get_object()
        session.active = False
        session.end_time = timezone.now()
        session.success = request.data.get('success', False)
        session.save()
        return Response({'status': 'session ended'})

class PuzzleViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Puzzle.objects.all()
    serializer_class = PuzzleSerializer

class TeamViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Team.objects.all()
    serializer_class = TeamSerializer

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

@api_view(['GET'])
@permission_classes([IsAuthenticated])    
def queue_view(request):
    sessions = GameSession.objects.filter(active=True).select_related(
        'team', 'room', 'current_puzzle'
    )
    manager = QueueManager()
    recommender = HintRecommender()
    fairness = FairnessEngine()
    ranked = manager.rank_sessions(list(sessions))
    result = []
    for session, score in ranked:
        rec = recommender.suggest_hint(session)
        result.append({
            'session_id': session.id,
            'team': session.team.name,
            'room': session.room.name,
            'current_puzzle': session.current_puzzle.name if session.current_puzzle else None,
            'hints_given': session.hints_given,
            'priority_score': round(score, 3),
            'recommendation': rec,
            'elapsed_minutes': int((timezone.now() - session.start_time).total_seconds() / 60),
        })
    report = fairness.fairness_report()
    outliers = fairness.detect_outliers()
    return JsonResponse({
        'queue': result,
        'fairness': {**report, 'outliers': outliers},
    })


def _dashboard_queue_context():
    sessions = GameSession.objects.filter(active=True).select_related(
        'team', 'room', 'current_puzzle'
    )
    manager = QueueManager()
    recommender = HintRecommender()
    fairness = FairnessEngine()
    ranked = manager.rank_sessions(list(sessions))
    rows = []
    for session, score in ranked:
        rec = recommender.suggest_hint(session)
        rows.append({
            'session': session,
            'priority_score': round(score, 3),
            'recommendation': rec,
            'elapsed_minutes': int((timezone.now() - session.start_time).total_seconds() / 60),
        })
    return {
        'queue_rows': rows,
        'fairness': fairness.fairness_report(),
        'fairness_outliers': fairness.detect_outliers(),
    }

@login_required
def dashboard_view(request):
    ctx = _dashboard_queue_context()
    return render(request, 'games/dashboard.html', ctx)

@login_required
def analytics_view(request):
    engine = AnalyticsEngine()
    puzzle_report = engine.puzzle_difficulty_report()[:14]
    room_perf = engine.room_performance()
    team_sizes = engine.team_size_analysis()
    hint_timing = engine.hint_timing_analysis()
    bottlenecks = engine.bottleneck_puzzles(8)
    balance = [engine.game_balance_score(r) for r in EscapeRoom.objects.all()]

    chart_labels = [f"{p['puzzle'][:18]}" for p in puzzle_report]
    chart_expected = [round(p['expected_seconds'] / 60.0, 2) for p in puzzle_report]
    chart_actual = [round(p['avg_solve_seconds'] / 60.0, 2) for p in puzzle_report]

    doughnut_labels = [r['room'] for r in room_perf]
    doughnut_values = [r['success_rate'] for r in room_perf]

    timing_labels = [f"{b['minute_bucket']}m" for b in hint_timing]
    timing_values = [b['hint_events'] for b in hint_timing]

    team_labels = [f"Size {t['team_size']}" for t in team_sizes]
    team_values = [t['success_rate'] for t in team_sizes]

    return render(request, 'games/analytics.html', {
        'puzzle_report': puzzle_report,
        'room_perf': room_perf,
        'team_sizes': team_sizes,
        'hint_timing': hint_timing,
        'bottlenecks': bottlenecks,
        'balance_scores': balance,
        'chart_labels_json': json.dumps(chart_labels),
        'chart_expected_json': json.dumps(chart_expected),
        'chart_actual_json': json.dumps(chart_actual),
        'doughnut_labels_json': json.dumps(doughnut_labels),
        'doughnut_values_json': json.dumps(doughnut_values),
        'timing_labels_json': json.dumps(timing_labels),
        'timing_values_json': json.dumps(timing_values),
        'team_labels_json': json.dumps(team_labels),
        'team_values_json': json.dumps(team_values),
    })

@login_required
def session_detail_view(request, pk):
    session = get_object_or_404(
        GameSession.objects.select_related('team', 'room'),
        pk=pk,
    )
    engine = AnalyticsEngine()
    summary = engine.session_summary(session)
    room_rows = {r['room_id']: r for r in engine.room_performance()}
    room_avg = room_rows.get(session.room_id, {})
    return render(request, 'games/session_detail.html', {
        'session': session,
        'summary': summary,
        'room_avg': room_avg,
    })

@login_required
def room_list_view(request):
    engine = AnalyticsEngine()
    rooms = EscapeRoom.objects.all().order_by('name')
    scores = [engine.game_balance_score(r) for r in rooms]
    return render(request, 'games/rooms.html', {
        'rooms_with_scores': list(zip(rooms, scores)),
    })

@login_required
def room_detail_view(request, pk):
    room = get_object_or_404(EscapeRoom, pk=pk)
    engine = AnalyticsEngine()
    perf = next((r for r in engine.room_performance() if r['room_id'] == room.id), None)
    puzzles = list(Puzzle.objects.filter(room=room).order_by('order'))
    puzzle_stats = {p['puzzle_id']: p for p in engine.puzzle_difficulty_report()}
    puzzle_rows = [{'puzzle': p, 'stat': puzzle_stats.get(p.id)} for p in puzzles]
    return render(request, 'games/room_detail.html', {
        'room': room,
        'perf': perf,
        'puzzle_rows': puzzle_rows,
        'balance': engine.game_balance_score(room),
    })

@login_required
def simulation_view(request):
    rooms = EscapeRoom.objects.all().order_by('name')
    teams = Team.objects.all().order_by('name')
    sim = SimulationMode()
    results = None
    compare = None
    selected_room_id = None
    selected_team_id = None
    selected_strategy = None

    if request.method == 'POST':
        selected_room_id = request.POST.get('room')
        selected_team_id = request.POST.get('team') or ''
        selected_strategy = request.POST.get('strategy', 'balanced')
        room = get_object_or_404(EscapeRoom, pk=selected_room_id)
        team = None
        if selected_team_id:
            team = get_object_or_404(Team, pk=selected_team_id)
        compare = [sim.simulate_session(room, team=team, strategy=s, runs=40) for s in ('conservative', 'balanced', 'aggressive')]
        results = sim.simulate_session(room, team=team, strategy=selected_strategy, runs=60)

    return render(request, 'games/simulation.html', {
        'rooms': rooms,
        'teams': teams,
        'results': results,
        'compare': compare,
        'selected_room_id': selected_room_id,
        'selected_team_id': selected_team_id,
        'selected_strategy': selected_strategy or 'balanced',
    })

