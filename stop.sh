#!/bin/bash
lsof -ti :8000 | xargs kill -9 2>/dev/null && echo "Server stopped" || echo "No server running on port 8000"
