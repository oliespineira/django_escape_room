import json
import logging

from django.contrib import messages
from django.db.models import Count
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .intelligence import (
    FairnessEngine,
    HintRecommender,
    QueueManager,
    SimulationMode,
    get_available_puzzles,
)
from .models import (
    EscapeRoom,
    GameSession,
    HintEvent,
    OutputAcquired,
    Player,
    Puzzle,
    PuzzleAttempt,
    Team,
)
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
            available_puzzles = sorted(get_available_puzzles(session), key=lambda p: p.order)
            first_puzzle = available_puzzles[0] if available_puzzles else None
            if not first_puzzle:
                first_puzzle = (
                    Puzzle.objects.filter(room=session.room, dependencies__isnull=True)
                    .order_by("order")
                    .first()
                )
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
    @action(detail=True, methods=['post'], url_path='complete-puzzle')
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

        for output in current_puzzle.outputs.all():
            OutputAcquired.objects.get_or_create(session=session, output=output)

        available_next = sorted(get_available_puzzles(session), key=lambda p: p.order)
        next_puzzle = available_next[0] if available_next else None

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
        available = get_available_puzzles(session)
        completed_count = PuzzleAttempt.objects.filter(session=session, completed=True).count()
        total = Puzzle.objects.filter(room=session.room).count()
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
            'available_puzzles': [p.name for p in available],
            'locked_puzzles_count': max(0, total - len(available) - completed_count),
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
    paused = [s for s in sessions if s.status == GameSession.STATUS_PAUSED]
    pending = [s for s in sessions if s.status == GameSession.STATUS_PENDING]

    rows = []
    for session, score in ranked_active:
        rec = recommender.suggest_hint(session)
        available = get_available_puzzles(session)
        completed_count = PuzzleAttempt.objects.filter(session=session, completed=True).count()
        total = Puzzle.objects.filter(room=session.room).count()
        locked_count = max(0, total - len(available) - completed_count)
        rows.append({
            'session': session,
            'priority_score': round(score, 3),
            'recommendation': rec,
            'elapsed_minutes': int(session.elapsed_seconds / 60),
            'available_puzzles': available,
            'locked_puzzles_count': locked_count,
        })
    for session in paused:
        available = get_available_puzzles(session)
        completed_count = PuzzleAttempt.objects.filter(session=session, completed=True).count()
        total = Puzzle.objects.filter(room=session.room).count()
        locked_count = max(0, total - len(available) - completed_count)
        rows.append({
            'session': session,
            'priority_score': None,
            'recommendation': {'action': 'wait', 'reason': 'Session paused'},
            'elapsed_minutes': int(session.elapsed_seconds / 60),
            'available_puzzles': available,
            'locked_puzzles_count': locked_count,
        })
    for session in pending:
        available = get_available_puzzles(session)
        completed_count = PuzzleAttempt.objects.filter(session=session, completed=True).count()
        total = Puzzle.objects.filter(room=session.room).count()
        locked_count = max(0, total - len(available) - completed_count)
        rows.append({
            'session': session,
            'priority_score': None,
            'recommendation': {'action': 'wait', 'reason': 'Not started yet'},
            'elapsed_minutes': 0,
            'available_puzzles': available,
            'locked_puzzles_count': locked_count,
        })

    available_puzzles = {row['session'].id: row['available_puzzles'] for row in rows}

    return {
        'queue_rows': rows,
        'available_puzzles': available_puzzles,
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

    acquired_by_puzzle = {}
    for oa in OutputAcquired.objects.filter(session=session).select_related('output'):
        acquired_by_puzzle.setdefault(oa.output.puzzle_id, []).append(oa.output)

    attempts_out = []
    for a in summary['attempts']:
        pid = a['puzzle_id']
        outputs = acquired_by_puzzle.get(pid, [])
        attempts_out.append({
            **a,
            'outputs_acquired': [
                {'label': (o.label or o.output_value or '').strip()}
                for o in outputs
            ],
        })
    summary = {**summary, 'attempts': attempts_out}

    completed_ids = set(
        PuzzleAttempt.objects.filter(session=session, completed=True).values_list(
            'puzzle_id', flat=True
        )
    )
    available_ids = {p.id for p in get_available_puzzles(session)}

    puzzle_graph = []
    for puzzle in Puzzle.objects.filter(room=session.room).order_by('order').prefetch_related(
        'dependencies', 'outputs', 'dependencies__requires_output'
    ):
        if puzzle.id in completed_ids:
            status = 'completed'
        elif puzzle.id in available_ids:
            status = 'available'
        else:
            status = 'locked'
        puzzle_graph.append({
            'puzzle': puzzle,
            'requires': [d.requires_output.label for d in puzzle.dependencies.all()],
            'produces': [o.label for o in puzzle.outputs.all()],
            'status': status,
        })

    room_rows = {r['room_id']: r for r in engine.room_performance()}
    room_avg = room_rows.get(session.room_id, {})
    return render(request, 'games/session_detail.html', {
        'session': session,
        'summary': summary,
        'room_avg': room_avg,
        'puzzle_graph': puzzle_graph,
    })

@login_required
def player_list_view(request):
    players = Player.objects.all().order_by('name').prefetch_related('team_set')
    rows = [
        {'player': p, 'team_names': list(p.team_set.values_list('name', flat=True))}
        for p in players
    ]
    return render(request, 'games/players.html', {
        'players': rows,
        'hint_choices': Player.HINT_CHOICES,
        'exp_choices': Player.EXPERIENCE_CHOICES,
    })


@login_required
def player_create_view(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        exp = request.POST.get('experience_level', 'intermediate')
        hint = request.POST.get('hint_preference', 'normal')
        if not name:
            messages.error(request, 'Name is required.')
        else:
            Player.objects.create(name=name, experience_level=exp, hint_preference=hint)
            messages.success(request, f'Player "{name}" created.')
    return redirect('player_list')


@login_required
def player_edit_view(request, pk):
    player = get_object_or_404(Player, pk=pk)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        exp = request.POST.get('experience_level', player.experience_level)
        hint = request.POST.get('hint_preference', player.hint_preference)
        if name:
            player.name = name
            player.experience_level = exp
            player.hint_preference = hint
            player.save()
            messages.success(request, f'Player "{name}" updated.')
        else:
            messages.error(request, 'Name cannot be empty.')
    return redirect('player_list')


@login_required
def player_delete_view(request, pk):
    player = get_object_or_404(Player, pk=pk)
    if request.method == 'POST':
        name = player.name
        player.delete()
        messages.success(request, f'Player "{name}" deleted.')
    return redirect('player_list')


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
    puzzles = list(
        Puzzle.objects.filter(room=room)
        .order_by('order')
        .prefetch_related('dependencies__requires_output', 'outputs')
    )
    puzzle_stats = {p['puzzle_id']: p for p in engine.puzzle_difficulty_report()}
    puzzle_rows = [
        {
            'puzzle': p,
            'stat': puzzle_stats.get(p.id),
            'requires': [d.requires_output.label for d in p.dependencies.all()],
            'produces': [o.label for o in p.outputs.all()],
        }
        for p in puzzles
    ]
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

from django.contrib.auth.decorators import login_not_required

@login_not_required
def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})


def _puzzles_payload_for_room(room):
    """Serializable puzzle graph for the room edit form (JSON)."""
    out = []
    for p in (
        Puzzle.objects.filter(room=room)
        .order_by('order')
        .prefetch_related('outputs', 'dependencies__requires_output')
    ):
        out.append({
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'category': p.category,
            'subtype': p.subtype or '',
            'difficulty': p.difficulty,
            'expected_time_min': max(1, (p.expected_time or 60) // 60),
            'is_parallel': p.is_parallel,
            'outputs': [
                {
                    'label': o.label,
                    'output_type': o.output_type,
                    'output_value': o.output_value,
                }
                for o in p.outputs.all()
            ],
            'dependencies': [
                {
                    'label': (d.requires_output.label or '').strip().lower(),
                    'all_required': d.all_required,
                }
                for d in p.dependencies.all()
            ],
        })
    return out


def _apply_puzzle_graph(request, room):
    """Create/update puzzles, outputs, and dependencies from POST; drop puzzles not in the form."""
    from .models import PuzzleDependency, PuzzleOutput

    puzzle_names = request.POST.getlist('puzzle_name')
    puzzle_ids = request.POST.getlist('puzzle_id')
    puzzle_categories = request.POST.getlist('puzzle_category')
    puzzle_difficulties = request.POST.getlist('puzzle_difficulty')
    puzzle_expected = request.POST.getlist('puzzle_expected_time')
    puzzle_descriptions = request.POST.getlist('puzzle_description')
    puzzle_subtypes = request.POST.getlist('puzzle_subtype')

    created_or_updated = []
    created_puzzles = []
    all_outputs_by_label = {}

    order = 0
    for i, pname in enumerate(puzzle_names):
        pname = pname.strip()
        if not pname:
            continue
        order += 1
        is_parallel = bool(request.POST.get(f'puzzle_is_parallel_{i}'))
        try:
            exp_time = int(puzzle_expected[i]) * 60 if i < len(puzzle_expected) else 300
        except (ValueError, TypeError):
            exp_time = 300

        pid_raw = puzzle_ids[i].strip() if i < len(puzzle_ids) else ''
        puzzle = None
        if pid_raw.isdigit():
            puzzle = Puzzle.objects.filter(pk=int(pid_raw), room=room).first()
        if puzzle is not None and puzzle.pk:
            puzzle.dependencies.all().delete()
            puzzle.outputs.all().delete()
        if puzzle is None:
            puzzle = Puzzle(room=room)

        puzzle.name = pname
        puzzle.description = puzzle_descriptions[i] if i < len(puzzle_descriptions) else ''
        puzzle.category = puzzle_categories[i] if i < len(puzzle_categories) else 'logical'
        puzzle.subtype = puzzle_subtypes[i] if i < len(puzzle_subtypes) else ''
        puzzle.difficulty = int(puzzle_difficulties[i]) if i < len(puzzle_difficulties) else 5
        puzzle.expected_time = exp_time
        puzzle.order = order
        puzzle.is_parallel = is_parallel
        puzzle.room = room
        puzzle.save()

        created_or_updated.append(puzzle)
        created_puzzles.append((i, puzzle))

        oi = 0
        while f'puzzle_{i}_output_label_{oi}' in request.POST:
            label = request.POST.get(f'puzzle_{i}_output_label_{oi}', '').strip()
            otype = request.POST.get(f'puzzle_{i}_output_type_{oi}', 'code')
            value = request.POST.get(f'puzzle_{i}_output_value_{oi}', '').strip()
            if label:
                output = PuzzleOutput.objects.create(
                    puzzle=puzzle, output_type=otype,
                    output_value=value, label=label,
                )
                all_outputs_by_label[label.lower()] = output
            oi += 1

    for i, puzzle in created_puzzles:
        di = 0
        while f'puzzle_{i}_dep_label_{di}' in request.POST:
            dep_label = request.POST.get(f'puzzle_{i}_dep_label_{di}', '').strip().lower()
            all_required = request.POST.get(f'puzzle_{i}_dep_required_{di}', '1') == '1'
            if dep_label and dep_label in all_outputs_by_label:
                PuzzleDependency.objects.get_or_create(
                    puzzle=puzzle,
                    requires_output=all_outputs_by_label[dep_label],
                    defaults={'all_required': all_required},
                )
            di += 1

    kept_pks = {p.pk for p in created_or_updated}
    if kept_pks:
        Puzzle.objects.filter(room=room).exclude(pk__in=kept_pks).delete()


@login_required
def room_create_view(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        difficulty = request.POST.get('difficulty', 'medium')
        max_time = request.POST.get('max_time', '60')
        theme = request.POST.get('theme', '').strip()

        puzzle_names = request.POST.getlist('puzzle_name')

        errors = []
        if not name:
            errors.append('Room name is required.')
        if not theme:
            errors.append('Theme is required.')
        if not [n.strip() for n in puzzle_names if n.strip()]:
            errors.append('Add at least one puzzle.')

        if errors:
            return render(request, 'games/room_create.html', {
                'errors': errors,
                'form_data': {
                    'name': name, 'description': description,
                    'difficulty': difficulty, 'max_time': max_time, 'theme': theme,
                },
            })

        room = EscapeRoom.objects.create(
            name=name, description=description,
            difficulty=difficulty, max_time=int(max_time), theme=theme,
        )
        _apply_puzzle_graph(request, room)

        return redirect('room_detail', pk=room.pk)

    return render(request, 'games/room_create.html', {})


@login_required
def room_edit_view(request, pk):
    room = get_object_or_404(EscapeRoom, pk=pk)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        difficulty = request.POST.get('difficulty', 'medium')
        max_time = request.POST.get('max_time', '60')
        theme = request.POST.get('theme', '').strip()
        puzzle_names = request.POST.getlist('puzzle_name')

        errors = []
        if not name:
            errors.append('Room name is required.')
        if not theme:
            errors.append('Theme is required.')
        if not [n.strip() for n in puzzle_names if n.strip()]:
            errors.append('Add at least one puzzle.')

        if errors:
            return render(request, 'games/room_edit.html', {
                'room': room,
                'errors': errors,
                'form_data': {
                    'name': name, 'description': description,
                    'difficulty': difficulty, 'max_time': max_time, 'theme': theme,
                },
                'initial_puzzles': _puzzles_payload_for_room(room),
            })

        room.name = name
        room.description = description
        room.difficulty = difficulty
        room.max_time = int(max_time)
        room.theme = theme
        room.save()

        _apply_puzzle_graph(request, room)
        messages.success(request, f'Room "{room.name}" updated.')
        return redirect('room_detail', pk=room.pk)

    return render(request, 'games/room_edit.html', {
        'room': room,
        'form_data': {
            'name': room.name,
            'description': room.description,
            'difficulty': room.difficulty,
            'max_time': str(room.max_time),
            'theme': room.theme,
        },
        'initial_puzzles': _puzzles_payload_for_room(room),
    })


def _add_players_to_team_from_setup(team, room_id, request):
    """Attach selected existing players and new lines (create or match by name) to team."""
    for pid in request.POST.getlist(f'player_ids_{room_id}'):
        try:
            team.players.add(Player.objects.get(pk=int(pid)))
        except (ValueError, Player.DoesNotExist):
            continue

    raw = request.POST.get(f'players_{room_id}', '')
    for line in raw.splitlines():
        name = line.strip()
        if not name:
            continue
        existing = Player.objects.filter(name__iexact=name).first()
        if existing:
            team.players.add(existing)
        else:
            team.players.add(
                Player.objects.create(
                    name=name,
                    experience_level='intermediate',
                    hint_preference='normal',
                )
            )


@login_required
def setup_view(request):
    """GM setup page — assign teams (new or existing) to rooms before starting."""
    rooms = EscapeRoom.objects.all().order_by('name')
    teams = (
        Team.objects.annotate(player_count=Count('players'))
        .order_by('name')
        .prefetch_related('players')
    )
    all_players = Player.objects.all().order_by('name')

    def setup_state_for_room(room, post=None):
        rid = str(room.id)
        default_source = 'existing' if teams.exists() else 'new'
        st = {
            'team_source': default_source,
            'team_name': '',
            'existing_team': '',
            'players_text': '',
            'player_ids': [],
        }
        if post is not None:
            st['team_source'] = post.get(f'team_source_{rid}', default_source)
            if not teams.exists():
                st['team_source'] = 'new'
            st['team_name'] = post.get(f'team_name_{rid}', '')
            st['existing_team'] = post.get(f'existing_team_{rid}', '')
            st['players_text'] = post.get(f'players_{rid}', '')
            st['player_ids'] = post.getlist(f'player_ids_{rid}')
        return st

    room_rows = [
        {'room': r, 'setup': setup_state_for_room(r, request.POST if request.method == 'POST' else None)}
        for r in rooms
    ]

    if request.method == 'POST':
        selected_room_ids = request.POST.getlist('rooms')
        errors = []

        for room_id in selected_room_ids:
            try:
                room = EscapeRoom.objects.get(pk=room_id)
            except (EscapeRoom.DoesNotExist, ValueError):
                continue

            rid = str(room.id)
            team_source = request.POST.get(f'team_source_{rid}', 'new')
            if not teams.exists():
                team_source = 'new'

            team = None
            if team_source == 'existing':
                tid = request.POST.get(f'existing_team_{rid}', '').strip()
                if not tid.isdigit():
                    errors.append(f'Room "{room.name}": choose an existing team.')
                    continue
                team = Team.objects.filter(pk=int(tid)).first()
                if not team:
                    errors.append(f'Room "{room.name}": team not found.')
                    continue
            else:
                team_name = request.POST.get(f'team_name_{rid}', '').strip()
                if not team_name:
                    errors.append(
                        f'Room "{room.name}": enter a new team name or select an existing team.'
                    )
                    continue
                team = Team.objects.create(name=team_name)

            _add_players_to_team_from_setup(team, rid, request)

            GameSession.objects.create(
                team=team,
                room=room,
                active=False,
            )

        if errors:
            return render(request, 'games/setup.html', {
                'room_rows': room_rows,
                'teams': teams,
                'all_players': all_players,
                'errors': errors,
                'posted_room_ids': [int(x) for x in selected_room_ids if str(x).isdigit()],
            })

        return redirect('dashboard')

    return render(request, 'games/setup.html', {
        'room_rows': room_rows,
        'teams': teams,
        'all_players': all_players,
        'posted_room_ids': [],
    })