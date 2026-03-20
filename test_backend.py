import requests
import json

try:
    # Test health check on port 8002 (forecast app)
    response = requests.get('http://localhost:8002/health', timeout=5)
    print(f'Forecast health response: {response.status_code}')
    health_data = response.json()
    print(json.dumps(health_data, indent=2))
    
    print('\n---\n')
    
    # Test forecast endpoint on port 8002
    response = requests.get('http://localhost:8002/forecast/310?days_ahead=7', timeout=10)
    print(f'Forecast response code: {response.status_code}')
    if response.status_code == 200:
        data = response.json()
        product_name = data.get('product_name')
        forecast_points = data.get('forecast_points', [])
        print(f'Product: {product_name}')
        print(f'Forecast points: {len(forecast_points)}')
        if forecast_points:
            print(f'First forecast: {forecast_points[0]}')
        print('✅ Forecast API working!')
    else:
        print('Error:', response.json())
        
    print('\n---\n')
    
    # Test data management on port 8001
    response = requests.get('http://localhost:8001/schema', timeout=5)
    print(f'Data management schema response: {response.status_code}')
    if response.status_code == 200:
        print('✅ Data Management API working!')
        
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
    import traceback
    traceback.print_exc()
