from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import GameSessionViewSet, PuzzleViewSet, TeamViewSet, queue_view

router = DefaultRouter()
router.register(r"sessions", GameSessionViewSet)
router.register(r"puzzles", PuzzleViewSet)
router.register(r"teams", TeamViewSet)

urlpatterns = [
    path("", include(router.urls)),
    path("queue/", queue_view),
]
