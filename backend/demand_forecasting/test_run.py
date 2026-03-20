import uvicorn
import threading
import time
import sys

sys.path.insert(0, '.')

# Start server in thread
def run():
    uvicorn.run('app.main:app', port=8003, reload=False, log_level='critical')

thread = threading.Thread(target=run, daemon=True)
thread.start()

# Wait for startup (data loading takes time)
print('Waiting 90 seconds for forecast app startup...')
time.sleep(90)

# Test endpoint
import requests
try:
    r = requests.get('http://localhost:8003/health', timeout=5)
    print(f'Forecast app health response: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        model_trained = data.get('model_trained')
        data_loaded = data.get('data_loaded')
        print(f'Model trained: {model_trained}')
        print(f'Data loaded: {data_loaded}')
        print('✅ Forecast app working!')
except Exception as e:
    print(f'❌ Error: {e}')
    import traceback
    traceback.print_exc()

time.sleep(1)
