# Use a lightweight Python base image
FROM python:3.11-slim

# Ensure logs are printed immediately (no buffering)
ENV PYTHONUNBUFFERED=1

# Set the working directory inside the container
WORKDIR /app

# ---------------------------------------------------------
# Install system dependencies (if needed)
# Currently empty, but kept for future requirements.
# ---------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------
# Install Python dependencies
# ---------------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------
# Copy the application code into the container
# ---------------------------------------------------------
COPY . .

# ---------------------------------------------------------
# Flask environment variables
# ---------------------------------------------------------
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5000

# Expose the port Flask will run on
EXPOSE 5000

# ---------------------------------------------------------
# Default command: run the Flask development server
# ---------------------------------------------------------
CMD ["flask", "run"]