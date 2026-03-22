import urllib.request
import json
import time

try:
    req = urllib.request.Request("http://127.0.0.1:8001/api/dashboard/sales")
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        print("Pie Chart Labels:")
        print(data.get("store_pie", {}).get("labels", []))
except Exception as e:
    print(f"Error: {e}")
