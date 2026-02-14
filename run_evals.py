#!/usr/bin/env python
"""Wrapper script to run evaluations with correct paths."""

import sys
from pathlib import Path

# Get project root
project_root = Path(__file__).parent.resolve()
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "app"))

# Change to project root for relative paths
import os
os.chdir(project_root)

# Now run the actual runner
from tests.evals.runner import main

if __name__ == "__main__":
    main()
