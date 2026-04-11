from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .models import *
from .serializers import *

# Create your views here.
class GameSessionViewSet(viewsets.ModelViewSet):
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
    queryset = Puzzle.objects.all()
    serializer_class = PuzzleSerializer

class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    


