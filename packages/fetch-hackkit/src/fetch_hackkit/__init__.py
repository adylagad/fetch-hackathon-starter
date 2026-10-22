"""fetch-hackkit: batteries for Fetch.ai hackathon agents.

from fetch_hackkit import HackAgent, cards, ASI1
"""

from . import cards
from .agent import HackAgent, Inbound, Reply, text_message
from .asi1 import ASI1, ASI1Error, Tool, history, remember, tool
from .cards import Card, CardError, parse_selection
from .register import connect_mailbox, handle_available, resolve, validate_handle

__version__ = "0.1.0"

__all__ = [
    "ASI1",
    "ASI1Error",
    "Card",
    "CardError",
    "HackAgent",
    "Inbound",
    "Reply",
    "Tool",
    "cards",
    "connect_mailbox",
    "handle_available",
    "history",
    "parse_selection",
    "remember",
    "resolve",
    "text_message",
    "tool",
    "validate_handle",
]
