"""
Pytest configuration
"""

import pytest
import sys
import os

# Ensure the project root is in the path
# Add src directory to path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(root_dir, 'src'))
