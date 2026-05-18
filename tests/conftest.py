"""Pytest configuration and fixtures."""
import sys
from unittest.mock import MagicMock

# Mock supabase module before any imports
sys.modules['supabase'] = MagicMock()
