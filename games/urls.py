from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("analytics/", views.analytics_view, name="analytics"),
    path("sessions/<int:pk>/", views.session_detail_view, name="session_detail"),
    path("rooms/", views.room_list_view, name="room_list"),
    path("rooms/create/", views.room_create_view, name="room_create"),
    path("rooms/<int:pk>/edit/", views.room_edit_view, name="room_edit"),
    path("players/", views.player_list_view, name="player_list"),
    path("players/create/", views.player_create_view, name="player_create"),
    path("players/<int:pk>/edit/", views.player_edit_view, name="player_edit"),
    path("players/<int:pk>/delete/", views.player_delete_view, name="player_delete"),
    path("rooms/<int:pk>/", views.room_detail_view, name="room_detail"),
    path("simulation/", views.simulation_view, name="simulation"),
    path("setup/", views.setup_view, name="setup"),
]
