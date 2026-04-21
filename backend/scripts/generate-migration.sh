#!/bin/bash
# Generate an Alembic migration for Paperless-AIssist.
# Usage: ./scripts/generate-migration.sh "description of change"
set -e

cd /Users/theobald/Developer/paperless-aissist/backend
DATA_DIR=../data .venv/bin/alembic revision --autogenerate -m "$1"
echo "Migration generated. Review it before committing."