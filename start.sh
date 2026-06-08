#!/bin/bash
source .venv/bin/activate
uvicorn summary_generator.main:app --reload --port 8000
