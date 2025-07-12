FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required for Google Chrome
RUN apt-get update && apt-get install -y wget gnupg ca-certificates curl unzip fonts-liberation libglib2.0-0 libnss3 libgconf-2-4 libxss1 libappindicator1 libindicator7 libasound2 xdg-utils --no-install-recommends

# Add Google's official GPG key
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -

# Set up the Chrome repository
RUN sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list'

# Update and install Google Chrome
RUN apt-get update && apt-get install -y google-chrome-stable

# Clean up the apt cache to reduce image size
RUN rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the dynamic port
EXPOSE 10000

# ✅ Run Uvicorn directly (not gunicorn!) for SSE to work on Render
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
