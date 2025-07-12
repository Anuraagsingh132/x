# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for Google Chrome
RUN apt-get update && apt-get install -y wget gnupg

# Add Google's official GPG key
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -

# Set up the repository
RUN sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list'

# Update and install Google Chrome
RUN apt-get update && apt-get install -y google-chrome-stable

# Clean up the apt cache to reduce image size
RUN rm -rf /var/lib/apt/lists/*

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code
COPY . .

# Expose the port Render will run on (Render sets the PORT env var, typically to 10000)
EXPOSE 10000

# Command to run the application using gunicorn
# The --timeout flag is increased to handle potentially long scraping tasks
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:10000", "--timeout", "120"]
