FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required for Google Chrome
RUN apt-get update && apt-get install -y wget gnupg

# Add Google's official GPG key
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -

# Set up the Chrome repository
RUN sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list'

# Update and install Google Chrome
RUN apt-get update && apt-get install -y google-chrome-stable

# Clean up the apt cache to reduce image size
RUN rm -rf /var/lib/apt/lists/*

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose the dynamic port (not required by Render, but good for convention)
EXPOSE 10000

# ✅ Dynamic port bind (REQUIRED for Render)
CMD ["sh", "-c", "gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:${PORT} --timeout 120"]
