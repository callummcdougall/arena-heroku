"""Template context processors for the pages app."""

from .views import ALLOWED_CHAT_MODELS, DEFAULT_CHAT_MODEL


def chat_models(request):
    """
    Expose the chat model allowlist to every template.

    base.html renders its model <select> from this, so the dropdown options and
    the models chat_api will accept can never drift apart.
    """
    return {
        "chat_models": ALLOWED_CHAT_MODELS,
        "default_chat_model": DEFAULT_CHAT_MODEL,
    }
