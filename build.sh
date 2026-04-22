#!/bin/bash
echo "📦 Installing ffmpeg static binary..."

# Download static ffmpeg binary (no sudo needed)
curl -sL https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz -o /tmp/ffmpeg.tar.xz
cd /tmp
tar -xf ffmpeg.tar.xz
cp ffmpeg-*-amd64-static/ffmpeg /tmp/ffmpeg
cp ffmpeg-*-amd64-static/ffprobe /tmp/ffprobe
chmod +x /tmp/ffmpeg /tmp/ffprobe
rm -rf ffmpeg-*-amd64-static ffmpeg.tar.xz

echo "✅ ffmpeg installed to /tmp/"
