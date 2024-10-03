# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Create logs and state directories
RUN mkdir -p logs state

# Copy the rest of the application code into the container
COPY . .

# Expose port for the Flask status endpoint
EXPOSE 8000

# Command to run the application
CMD ["python", "app.py"]
