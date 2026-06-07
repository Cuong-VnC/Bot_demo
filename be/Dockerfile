FROM python:3.12-slim

# Prevent python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set environment variables for Playwright shared browser paths
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/local/share/ms-playwright

# Set the working directory
WORKDIR /app

# Install system dependencies including FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file and install python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser and dependencies to shared path as root
RUN mkdir -p $PLAYWRIGHT_BROWSERS_PATH && \
    playwright install chromium && \
    playwright install-deps chromium && \
    chmod -R 777 $PLAYWRIGHT_BROWSERS_PATH

# Copy the application code
COPY . .

# Create directories for data persistence, music library, and temporary files
RUN mkdir -p /app/data /app/music_library /app/temp && \
    chown -R 1000:1000 /app && \
    chmod -R 777 /app

# Set Hugging Face non-root user
USER 1000

# Hugging Face Spaces runs on port 7860
EXPOSE 7860

# Run the app using python main.py
CMD ["python", "main.py"]
