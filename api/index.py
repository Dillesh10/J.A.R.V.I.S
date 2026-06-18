import sys
import os

# Add the parent directory to the path so server.py and core/ memory/ etc. can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app
