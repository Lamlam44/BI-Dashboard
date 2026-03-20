import sys
sys.path.insert(0, '.')

from backend.main import app

# Check available routes
print("Available routes in the app:")
for route in app.routes:
    path = getattr(route, 'path', None)
    methods = getattr(route, 'methods', None)
    name = getattr(route, 'name', None)
    print(f"  Path: {path}, Methods: {methods}, Name: {name}")
