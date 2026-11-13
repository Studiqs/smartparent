import sys
from pathlib import Path

# Ensure backend root is always on sys.path for test discovery
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
