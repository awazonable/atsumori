# Start from a base image
FROM python:3.10-alpine

# Install dependencies
RUN apk update && apk add --no-cache \
    wget \
    make \
    gcc \
    g++ \
    openssl-dev \
    bzip2-dev \
    libffi-dev \
    zlib-dev \
    sqlite-dev

# Set the working directory
WORKDIR /app

# Install ffmpeg
RUN apk add --no-cache ffmpeg

# Copy requirements.txt
COPY requirements.txt .

# Install python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your app's source code from your host to your image filesystem.
COPY . .

# Run py background
CMD ["python3.10", "main.py"]