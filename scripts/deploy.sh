#!/bin/bash
set -e

echo "🚀 Deploying Hephaestus..."

# Check prerequisites
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed"
    exit 1
fi

if [ ! -f .env ]; then
    echo "❌ .env file not found. Please copy .env.example to .env and configure it."
    exit 1
fi

# Create data directories
mkdir -p data logs docs

# Build and start services
echo "📦 Building and starting services..."
docker-compose up -d --build

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check status
docker-compose ps

echo "✅ Deployment complete!"
echo "   - MCP Server: http://localhost:8000"
echo "   - Qdrant: http://localhost:6333"
echo "   - Logs: ./logs/"
