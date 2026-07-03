import sys
import os
from fastapi.testclient import TestClient

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.dependencies import get_current_user

# Mock a simple authenticated user ID (UUID string)
def mock_get_current_user():
    return "22222222-2222-4222-8222-222222222222"

app.dependency_overrides[get_current_user] = mock_get_current_user

client = TestClient(app)
response = client.get("/api/v1/task-templates/search?q=")
print("Response status:", response.status_code)
print("Response data:", response.json())
