# **Video Recorder Monitor Application**

## **Overview**

The **Video Recorder Monitor** is a Python application designed to synchronize recording operations between a primary ingest recorder system (referred to as **Playbox**) and a secondary DVR recording system (**MovieRecorder by Softron**). The application monitors active recording jobs on the Playbox system and starts or stops corresponding recordings on the DVR system to ensure redundancy and synchronization.

## **Table of Contents**

- Overview
- Features
- Workflow
- Architecture
- Installation
  - Prerequisites
  - Clone the Repository
  - Install Dependencies
- Configuration
- Usage
  - Running Locally
  - Running with Docker Compose
  - Accessing the Status Endpoint
- API Endpoints
  - Playbox API (Initial API to the ingest System)
  - DVR API (MovieRecorder by Softron)
- Logging
- Deployment
  - Docker Deployment
  - Environment Variables
  - Persistent Volumes
- Troubleshooting
- Contributing
  - Development Setup
- License

## **Features**

- **Automated Monitoring**: Continuously polls the Playbox API to detect active recording jobs.
- **Synchronized Recording**: Starts and stops recordings on the DVR system to match the Playbox system.
- **Thread-Safe Operations**: Utilizes threading and locks to ensure safe concurrent operations.
- **Error Handling**: Implements robust exception handling and retry logic for network operations.
- **State Persistence**: Saves and loads application state to handle restarts gracefully.
- **Status Endpoint**: Provides a Flask-based HTTP endpoint to query the current recording status.
- **Configurable Parameters**: Allows customization via environment variables for flexibility.
- **Dockerized Deployment**: Supports containerization using Docker and Docker Compose.

## **Workflow**

The application operates in a continuous loop, performing the following steps:

1. **Polling the Playbox System**:
   - Fetches active recording jobs from the Playbox API endpoint.
   - Extracts relevant information such as `ingestId`, `jobId`, and `basename` for each active job.
2. **Comparing Current and Previous States**:
   - Compares the current active jobs with the previous state to detect new or stopped jobs.
3. **Starting DVR Recordings**:
   - For each new job detected:
     - Maps the logical name (e.g., "PCR 1") to the corresponding DVR source ID.
     - Sets the recording name on the DVR system using the `basename` from the Playbox system.
     - Starts the recording on the DVR system.
4. **Stopping DVR Recordings**:
   - For each job that has stopped:
     - Stops the corresponding recording on the DVR system.
5. **State Update and Persistence**:
   - Updates the internal state with the current active jobs.
   - Saves the state to a file (`state.json`) to handle restarts.
6. **Error Handling and Retries**:
   - Implements retries with exponential backoff for transient network errors.
   - Handles exceptions to prevent crashes and ensure the application continues running.
7. **Providing Status Information**:
   - Exposes a `/status` endpoint via Flask to provide the current recording status in JSON format.

## **Architecture**

The application consists of the following components:

- **Main Application (`app.py`)**: Contains the `VideoRecorderMonitor` class, which implements the monitoring and synchronization logic.
- **Flask Server**: Runs in a separate thread to provide the `/status` endpoint.
- **Docker Configuration**: `Dockerfile` and `docker-compose.yml` for containerization.
- **Logging**: Configured to output logs to both the console and a log file (`logs/app.log`).
- **State File**: Persists application state in `state/state.json` for recovery after restarts.

## **Installation**

### **Prerequisites**

- **Python 3.10 or higher**
- **Docker** and **Docker Compose** (if deploying via Docker)

### **Clone the Repository**

bash

Copy code

`git clone https://github.com/yourusername/video-recorder-monitor.git`

`cd video-recorder-monitor`

### **Install Dependencies**

#### **Option 1: Running Locally**

bash

Copy code

`pip install -r requirements.txt`

#### **Option 2: Using Docker**

No manual installation is needed; Docker will handle dependencies.

## **Configuration**

The application can be configured using environment variables:

- **PRIMARY_API_BASE_URL**: Base URL for the Playbox API (default: `https://10.1.83.21:4230`)
- **DVR_API_BASE_URL**: Base URL for the DVR API (default: `http://10.1.85.53:8080`)
- **POLL_INTERVAL**: Polling interval in seconds (default: `5`)
- **FLASK_PORT**: Port for the Flask server (default: `8001`)

You can set these variables in your environment or configure them in the `docker-compose.yml` file.

## **Usage**

### **Running Locally**

bash

Copy code

`python app.py`

### **Running with Docker Compose**

Build and run the application using Docker Compose:

bash

Copy code

`docker-compose up -d`

### **Accessing the Status Endpoint**

Visit the following URL to access the current recording status:

bash

Copy code

`http://localhost:8001/status`

## **API Endpoints**

### **Playbox API (Initial API to the ingest System)**

- **Get Active Jobs Info**: `GET /ingests/activejobsinfo`
- **Get Files Info for a Job**: `GET /ingests/{ingestId}/jobs/{jobId}/files`

### **DVR API (MovieRecorder by Softron)**

- **Get List of Sources**: `GET /sources`
- **Set Recording Name**: `PUT /sources/{sourceId}/recording_name`
  - Payload: `{ "recording_name": "{basename}" }`
- **Start Recording**: `GET /sources/{sourceId}/record`
- **Stop Recording**: `GET /sources/{sourceId}/stop`

## **Logging**

Logs are written to both the console and a log file located at `logs/app.log`. The logging configuration includes timestamps and log levels for better traceability.

## **Deployment**

### **Docker Deployment**

**Build the Docker Image**  
bash  
Copy code  
`docker-compose build`

1.

**Run the Docker Container**  
bash  
Copy code  
`docker-compose up -d`

2.

**Check Running Containers**  
bash  
Copy code  
`docker ps`

3.

### **Environment Variables**

You can adjust environment variables in the `docker-compose.yml` file or set them directly in your deployment environment.

### **Persistent Volumes**

The application uses Docker volumes to persist logs and state files:

- **Logs**: Mapped to `./logs` on the host.
- **State**: Mapped to `./state` on the host.

## **Troubleshooting**

- **Cannot Access Status Endpoint**
  - Ensure the application is running and the port is correctly mapped.
  - Check firewall settings that might be blocking the port.
- **DVR Recordings Not Starting**
  - Verify that the DVR API is accessible from the application.
  - Check the mappings between logical names and DVR source IDs.
- **Application Crashes**
  - Review the logs in `logs/app.log` for error messages.
  - Ensure that all dependencies are installed and environment variables are correctly set.

## **Contributing**

Contributions are welcome\! Please submit a pull request or open an issue to discuss improvements or report bugs.

### **Development Setup**

**Clone the Repository**  
bash  
Copy code  
`git clone https://github.com/yourusername/video-recorder-monitor.git`

`cd video-recorder-monitor`

1.

**Create a Virtual Environment**  
bash  
Copy code  
`python -m venv venv`

`` source venv/bin/activate  # On Windows use `venv\Scripts\activate` ``

2.

**Install Dependencies**  
bash  
Copy code  
`pip install -r requirements.txt`

3.

**Run the Application**  
bash  
Copy code  
`python app.py`

4.

## **License**

This project is licensed under the MIT License. See the LICENSE file for details.

---

_For any questions or support, please contact yourname@yourdomain.com._
