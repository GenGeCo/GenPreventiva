from .auth import router as auth_router
from .learning import router as learning_router
from .quotes import router as quotes_router
from .chat import router as chat_router

__all__ = ["auth_router", "learning_router", "quotes_router", "chat_router"]
