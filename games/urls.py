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
    path("rooms/<int:pk>/", views.room_detail_view, name="room_detail"),
    path("simulation/", views.simulation_view, name="simulation"),
    path("setup/", views.setup_view, name="setup"),
]
