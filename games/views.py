import json
import logging

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views

from .intelligence import FairnessEngine, HintRecommender, QueueManager, SimulationMode
from .models import EscapeRoom, GameSession, HintEvent, Player, Puzzle, PuzzleAttempt, Team
from .serializers import GameSessionSerializer, PuzzleSerializer, TeamSerializer
from .services.analytics import AnalyticsEngine

from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication, BasicAuthentication

# Create your views here.
logger = logging.getLogger(__name__)


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
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Start a pending or paused session."""
        session = self.get_object()
        if session.status == GameSession.STATUS_PAUSED:
            # Resuming from pause — accumulate paused duration
            paused_seconds = (timezone.now() - session.paused_at).total_seconds()
            session.paused_duration += int(paused_seconds)
            session.paused_at = None
            session.active = True
            session.save()
            return Response({'status': 'resumed'})
        if session.status == GameSession.STATUS_PENDING:
            start_ts = timezone.now()
            first_puzzle = Puzzle.objects.filter(room=session.room).order_by('order').first()
            if not first_puzzle:
                logger.warning(
                    'Cannot start session %s: room %s has no puzzles',
                    session.id,
                    session.room_id,
                )
                return Response(
                    {'detail': 'Cannot start session: this room has no puzzles configured.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            session.start_time = start_ts
            session.active = True
            session.current_puzzle = first_puzzle
            session.save()

            PuzzleAttempt.objects.get_or_create(
                session=session,
                puzzle=first_puzzle,
                completed=False,
                defaults={'start_time': start_ts},
            )
            logger.info(
                'Session %s started on puzzle %s',
                session.id,
                first_puzzle.id,
            )
            return Response({'status': 'started', 'current_puzzle': first_puzzle.name})
        return Response(
            {'detail': 'Session is already active or ended.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    @action(detail=True, methods=['post'])
    def complete_puzzle(self, request, pk=None):
        """Mark current puzzle as completed and advance to the next one."""
        session = self.get_object()
        if session.status != GameSession.STATUS_ACTIVE:
            return Response(
                {'detail': 'Only active sessions can complete puzzles.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not session.current_puzzle:
            return Response(
                {'detail': 'No active puzzle to complete.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        current_puzzle = session.current_puzzle

        # Mark current attempt as completed
        attempt = PuzzleAttempt.objects.filter(
            session=session,
            puzzle=current_puzzle,
            completed=False
        ).order_by('-start_time').first()
        now = timezone.now()
        if not attempt:
            # Recover gracefully if previous start failed to create attempt.
            attempt = PuzzleAttempt.objects.create(
                session=session,
                puzzle=current_puzzle,
                start_time=now,
                completed=True,
                end_time=now,
            )
            logger.warning(
                'Recovered missing PuzzleAttempt for session %s puzzle %s during complete_puzzle',
                session.id,
                current_puzzle.id,
            )
        else:
            attempt.completed = True
            attempt.end_time = now
            attempt.save()

        # Find next puzzle in order
        next_puzzle = Puzzle.objects.filter(
            room=session.room,
            order__gt=current_puzzle.order
        ).order_by('order').first()

        if next_puzzle:
            session.current_puzzle = next_puzzle
            session.save()
            PuzzleAttempt.objects.get_or_create(
                session=session,
                puzzle=next_puzzle,
                completed=False,
                defaults={'start_time': now},
            )
            return Response({'status': 'advanced', 'next_puzzle': next_puzzle.name})
        else:
            # No more puzzles — session completed successfully
            session.current_puzzle = None
            session.active = False
            session.end_time = timezone.now()
            session.success = True
            session.save()
            return Response({'status': 'completed', 'next_puzzle': None})

    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """Pause an active session."""
        session = self.get_object()
        if session.status != GameSession.STATUS_ACTIVE:
            return Response(
                {'detail': 'Only active sessions can be paused.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        session.paused_at = timezone.now()
        session.active = False
        session.save()
        return Response({'status': 'paused'})



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
    sessions = GameSession.objects.exclude(
        end_time__isnull=False
    ).select_related('team', 'room', 'current_puzzle')
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
            'current_puzzle_order': session.current_puzzle.order if session.current_puzzle else None,
            'hints_given': session.hints_given,
            'priority_score': round(score, 3),
            'recommendation': rec,
            'elapsed_minutes': int(session.elapsed_seconds / 60),
            'status': session.status,
        })
    report = fairness.fairness_report()
    outliers = fairness.detect_outliers()
    return JsonResponse({
        'queue': result,
        'fairness': {**report, 'outliers': outliers},
    })


def _dashboard_queue_context():
    # Include pending and paused sessions too, not just active
    sessions = GameSession.objects.exclude(
        end_time__isnull=False
    ).select_related('team', 'room', 'current_puzzle')

    manager = QueueManager()
    recommender = HintRecommender()
    fairness = FairnessEngine()

    # Only rank active sessions — pending/paused don't get a priority score
    active_sessions = [s for s in sessions if s.status == GameSession.STATUS_ACTIVE]
    ranked_active = manager.rank_sessions(active_sessions)

    # Build rows: ranked active first, then paused, then pending
    ranked_ids = [s.id for s, _ in ranked_active]
    paused = [s for s in sessions if s.status == GameSession.STATUS_PAUSED]
    pending = [s for s in sessions if s.status == GameSession.STATUS_PENDING]

    rows = []
    for session, score in ranked_active:
        rec = recommender.suggest_hint(session)
        rows.append({
            'session': session,
            'priority_score': round(score, 3),
            'recommendation': rec,
            'elapsed_minutes': int(session.elapsed_seconds / 60),
        })
    for session in paused:
        rows.append({
            'session': session,
            'priority_score': None,
            'recommendation': {'action': 'wait', 'reason': 'Session paused'},
            'elapsed_minutes': int(session.elapsed_seconds / 60),
        })
    for session in pending:
        rows.append({
            'session': session,
            'priority_score': None,
            'recommendation': {'action': 'wait', 'reason': 'Not started yet'},
            'elapsed_minutes': 0,
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

@login_required
def setup_view(request):
    """GM setup page — create teams and assign them to rooms before starting."""
    rooms = EscapeRoom.objects.all().order_by('name')

    if request.method == 'POST':
        selected_room_ids = request.POST.getlist('rooms')
        errors = []

        for room_id in selected_room_ids:
            try:
                room = EscapeRoom.objects.get(pk=room_id)
            except EscapeRoom.DoesNotExist:
                continue

            team_name = request.POST.get(f'team_name_{room_id}', '').strip()
            player_names_raw = request.POST.get(f'players_{room_id}', '').strip()

            if not team_name:
                errors.append(f'Room "{room.name}" needs a team name.')
                continue

            # Create team
            team = Team.objects.create(name=team_name)

            # Create players — one name per line
            if player_names_raw:
                for line in player_names_raw.splitlines():
                    name = line.strip()
                    if name:
                        player = Player.objects.create(
                            name=name,
                            experience_level='intermediate',
                            hint_preference='normal',
                        )
                        team.players.add(player)

            # Create session — pending, not started yet
            GameSession.objects.create(
                team=team,
                room=room,
                active=False,
            )

        if errors:
            return render(request, 'games/setup.html', {
                'rooms': rooms,
                'errors': errors,
            })

        return redirect('dashboard')

    return render(request, 'games/setup.html', {'rooms': rooms})