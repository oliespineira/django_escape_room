from django.contrib import admin

from .models import (
    EscapeRoom,
    GameSession,
    HintEvent,
    Player,
    Puzzle,
    PuzzleAttempt,
    Team,
)


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "experience_level", "hint_preference")
    list_filter = ("experience_level", "hint_preference")
    search_fields = ("name",)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "created_at")
    search_fields = ("name",)
    filter_horizontal = ("players",)


@admin.register(EscapeRoom)
class EscapeRoomAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "difficulty", "max_time", "theme")
    list_filter = ("difficulty",)
    search_fields = ("name", "theme")


@admin.register(Puzzle)
class PuzzleAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "room", "order", "difficulty", "expected_time")
    list_filter = ("room",)
    search_fields = ("name",)
    ordering = ("room", "order")


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "team", "room", "active", "success", "start_time", "hints_given")
    list_filter = ("active", "success", "room")
    search_fields = ("team__name", "room__name")
    raw_id_fields = ("team", "room", "current_puzzle")


@admin.register(PuzzleAttempt)
class PuzzleAttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "puzzle", "completed", "hints_used", "start_time")
    list_filter = ("completed",)
    raw_id_fields = ("session", "puzzle")


@admin.register(HintEvent)
class HintEventAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "puzzle", "timestamp", "auto_suggested", "accepted")
    list_filter = ("auto_suggested", "accepted")
    raw_id_fields = ("session", "puzzle")
