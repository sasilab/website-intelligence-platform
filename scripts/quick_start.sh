#!/bin/bash

# Quick start script for Website Intelligence Platform
# This script sets up and runs the platform locally for development/testing

set -e

echo "=========================================="
echo "Website Intelligence Platform - Quick Start"
echo "=========================================="
echo ""

# Check for required tools
echo "Checking requirements..."

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed"
    exit 1
fi

if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed"
    exit 1
fi

echo "✅ All requirements met"
echo ""

# Setup environment
echo "Setting up environment..."

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env file and add your API keys"
    echo "   Required: OPENAI_API_KEY or ANTHROPIC_API_KEY"
    echo ""
    read -p "Press Enter after updating .env file..."
fi

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Install Node dependencies
echo "Installing Node dependencies..."
npm install

# Install Playwright browsers
echo "Installing Playwright browsers..."
npx playwright install

# Start services with Docker Compose
echo ""
echo "Starting services with Docker Compose..."
docker-compose up -d mongodb redis chromadb

# Wait for services to be ready
echo "Waiting for services to be ready..."
sleep 10

# Check service health
echo "Checking service health..."
docker-compose ps

# Run database migrations/setup
echo ""
echo "Setting up database..."
python -c "
import asyncio
from src.models.database import db_manager

async def setup():
    await db_manager.connect()
    print('Database connected and initialized')
    await db_manager.disconnect()

asyncio.run(setup())
"

# Start the API server
echo ""
echo "Starting API server..."
echo "=========================================="
echo "Platform is starting at http://localhost:8000"
echo "API documentation at http://localhost:8000/docs"
echo "=========================================="
echo ""

# Run the API server
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000