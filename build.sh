#!/bin/bash
set -e

echo "📦 Installing ffmpeg..."

# Try install via apt first
if command -v apt-get &> /dev/null; then
    apt-get update -qq
    apt-get install -y -qq ffmpeg > /dev/null 2>&1 || true
fi

# Verify installation
if command -v ffmpeg &> /dev/null; then
    echo "✅ ffmpeg installed successfully"
    ffmpeg -version | head -1
else
    echo "⚠️  ffmpeg tidak terinstall"
fi

# Copy to /tmp as backup
mkdir -p /tmp/bin
which ffmpeg > /dev/null && cp $(which ffmpeg) /tmp/ffmpeg 2>/dev/null || true
