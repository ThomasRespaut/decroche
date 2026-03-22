from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),

    path(
        "dashboard/knowledge/add/<int:agent_id>/",
        views.add_knowledge_source,
        name="add_knowledge_source",
    ),
    path(
        "dashboard/source/<int:source_id>/update/",
        views.update_knowledge_source,
        name="update_knowledge_source",
    ),
    path(
        "dashboard/source/<int:source_id>/delete/",
        views.delete_knowledge_source,
        name="delete_knowledge_source",
    ),
    path(
        "dashboard/source/<int:source_id>/export/",
        views.export_knowledge_source,
        name="export_knowledge_source",
    ),
    path(
        "dashboard/sources/export/<int:agent_id>/",
        views.export_knowledge_sources,
        name="export_knowledge_sources",
    ),

    path(
        "agents/<int:agent_id>/knowledge/clean/",
        views.clean_knowledge_sources,
        name="clean_knowledge_sources",
    ),

    path(
        "knowledge/source/<int:source_id>/optimize/",
        views.optimize_knowledge_source,
        name="optimize_knowledge_source",
    ),

    path("dashboard/preview-voice/", views.preview_voice, name="preview_voice"),

    path("agent/test/", views.test_agent, name="test_agent"),
]