from rest_framework import serializers
from .models import Player, Team, EscapeRoom, Puzzle, GameSession, PuzzleAttempt, HintEvent #these are the objects we want to convert into JSON


class PlayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Player
        fields = '__all__'
class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = '__all__'

class PuzzleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Puzzle
        fields = '__all__'

class GameSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GameSession
        fields = '__all__'
class HintEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = HintEvent
        fields = '__all__'
