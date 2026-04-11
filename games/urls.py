from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import GameSessionViewSet, PuzzleViewSet, TeamViewSet, queue_view

#Creates API generator
router = DefaultRouter() #creates an object that will, collect all the APIs and generate URLs automatically

'''Register endpoints: eg create an API at sessions using Game SessionViewSet

example one line creates:
GET     /sessions/        → list sessions
GET     /sessions/1/      → get one session
POST    /sessions/        → create session
PATCH   /sessions/1/      → update session
DELETE  /sessions/1/      → delete session
POST    /sessions/1/hint/ → your custom action
POST    /sessions/1/end/  → your custom action

'''
#defines endpoint
router.register(r'sessions', GameSessionViewSet)
router.register(r'puzzles', PuzzleViewSet)
router.register(r'teams', TeamViewSet)


#activates them
urlpatterns = [
    path('', include(router.urls)),
    path('queue/', queue_view)
    
]

