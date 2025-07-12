FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required for Chrome in headless mode
RUN apt-get update && apt-get install -y \
    wget gnupg curl unzip ca-certificates fonts-liberation \
    libglib2.0-0 libnss3 libgconf-2-4 libxss1 libappindicator1 libasound2 xdg-utils --no-install-recommends

# Add Google’s official GPG key and Chrome repo
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
RUN echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google.list

# Install Google Chrome
RUN apt-get update && apt-get install -y google-chrome-stable && rm -rf /var/lib/apt/lists/*

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app files
COPY . .

# Expose port (optional)
EXPOSE 10000

# Start FastAPI app with uvicorn (Render uses dynamic ${PORT})
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
