from django.urls import path

from .views import (
    chapter_view,
    chat_api,
    download_papers_api,
    faq,
    home,
    map_view,
    section_api,
    setup,
    static_context_api,
    token_count_api,
)

urlpatterns = [
    path("", home, name="home"),
    path("map/", map_view, name="map"),
    path("setup/", setup, name="setup"),
    path("faq/", faq, name="faq"),
    # API endpoint for fetching section content (used by JavaScript)
    path("api/<str:chapter_id>/<str:section_id>/", section_api, name="section_api"),
    # API endpoint for token counting
    path("api/token-count/", token_count_api, name="token_count_api"),
    # API endpoint for chat
    path("api/chat/", chat_api, name="chat_api"),
    # API endpoint for static page context (for chat on non-chapter pages)
    path("api/static-context/", static_context_api, name="static_context_api"),
    # API endpoint for downloading papers
    path("api/download-papers/", download_papers_api, name="download_papers_api"),
    # Chapter overview (no section selected)
    path("<str:chapter_id>/", chapter_view, name="chapter"),
    # Section view (with optional subsection)
    path("<str:chapter_id>/<str:section_id>/", chapter_view, name="section"),
    path("<str:chapter_id>/<str:section_id>/<str:subsection_id>/", chapter_view, name="subsection"),
]
