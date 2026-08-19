from .base import BaseEngine
from .mock_engine import MockEngine, RandomMockEngine
from .retry import RetryPolicy, RetryManager
from .rate_limiter import RateLimiter, RateLimiterConfig

try:
    from .claude_engine import ClaudeEngine
except ImportError:
    # Claude engine requires anthropic SDK
    ClaudeEngine = None

try:
    from .openai_engine import OpenAIEngine
except ImportError:
    # OpenAI engine requires openai SDK
    OpenAIEngine = None

__all__ = [
    "BaseEngine",
    "MockEngine",
    "RandomMockEngine",
    "RetryPolicy",
    "RetryManager",
    "RateLimiter",
    "RateLimiterConfig",
]

if ClaudeEngine is not None:
    __all__.append("ClaudeEngine")
if OpenAIEngine is not None:
    __all__.append("OpenAIEngine")
