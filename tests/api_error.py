import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from localsub import api
try:
    print(api.test_connection({"base_url": "https://api.openai.com/v1", "api_key": "sk-fake"}))
except api.ApiError as e:
    print("ApiError:", e)
