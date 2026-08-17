web: python migrations/run_all.py && gunicorn -k eventlet -w 1 run:app --bind 0.0.0.0:$PORT --timeout 120
