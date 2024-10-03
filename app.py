import requests
import time
import logging
import json
import os
from urllib3.exceptions import InsecureRequestWarning
from flask import Flask, jsonify
import threading
from werkzeug.serving import make_server
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Disable SSL warnings
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

# Configure logging with detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler("logs/app.log"),
        logging.StreamHandler()
    ]
)

app = Flask(__name__)

class VideoRecorderMonitor:
    def __init__(self, poll_interval, state_file='state/state.json'):
        self.poll_interval = poll_interval
        self.state_file = state_file
        self.lock = threading.Lock()  # Add lock for thread safety

        # Read API base URLs from environment variables or use default values
        self.api_base_url = os.environ.get('PRIMARY_API_BASE_URL', 'https://10.1.83.21:4230')
        self.dvr_api_base_url = os.environ.get('DVR_API_BASE_URL', 'http://10.1.85.53:8080')

        self.session = requests.Session()
        self.session.verify = False  # Ignore SSL warnings

        # Implement retries with exponential backoff for transient errors
        retries = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "PUT"]
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        # Mapping of ingestId to logical names
        self.ingest_id_map = {
            "9C64992CFF3A4A3FA3C635BB7D9B6071": "PCR 1",
            "9526F8488B06423C8C81B942B3D04B89": "PCR 2",
            "69774E0644F94C89A87785972AB7057A": "PCR 3",
            "53994615DC194483B753424DAD50EFE5": "PCR 4"
        }

        # Mapping of logical names to DVR source IDs
        self.logical_name_to_dvr_source_id = {
            "PCR 1": 0,
            "PCR 2": 1,
            "PCR 3": 2,
            "PCR 4": 3
        }

        # Load previous state if exists
        self.load_state()

    def load_state(self):
        if os.path.isfile(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    # Validate data format
                    if isinstance(data, dict):
                        # Convert keys back to tuples
                        self.previous_active_jobs = {
                            tuple(k.split('|')): v for k, v in data.items()
                        }
                    else:
                        logging.error("Invalid state file format. Expected a dictionary.")
                        self.previous_active_jobs = {}
                logging.info("Loaded previous state from file.")
            except (IOError, PermissionError) as e:
                logging.error(f"Failed to read state file: {e}")
                self.previous_active_jobs = {}
            except json.JSONDecodeError as e:
                logging.error(f"JSON decoding error in state file: {e}")
                self.previous_active_jobs = {}
            except Exception as e:
                logging.error(f"Unexpected error loading state file: {e}")
                self.previous_active_jobs = {}
        else:
            self.previous_active_jobs = {}
            logging.info("No previous state file found. Starting fresh.")

    def save_state(self):
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            # Convert tuple keys to strings for JSON serialization
            data = {'|'.join(k): v for k, v in self.previous_active_jobs.items()}
            with open(self.state_file, 'w') as f:
                json.dump(data, f)
           # logging.info("Saved current state to file.")
        except (IOError, PermissionError) as e:
            logging.error(f"Failed to save state file: {e}")
        except Exception as e:
            logging.error(f"Unexpected error saving state file: {e}")

    def run_monitoring_loop(self):
        while True:
            try:
                self.process_polling_cycle()
                time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                logging.info("Gracefully shutting down the application.")
                break  # Exit the loop on Ctrl+C
            except Exception as e:
                logging.error(f'An unexpected error occurred in the monitoring loop: {e}')

    def process_polling_cycle(self):
        active_jobs_info = self.get_active_jobs_info()
        current_active_jobs = {}

        # Process active jobs
        for ingest in active_jobs_info:
            ingest_id = ingest.get('ingestId')
            logical_name = self.ingest_id_map.get(ingest_id, "Unknown Ingest")
            for job in ingest.get('activeJobsInfo', []):
                job_id = job.get('id')
                basename = self.extract_basename(ingest_id, job_id)
                if basename:
                    current_active_jobs[(ingest_id, job_id)] = {
                        'basename': basename,
                        'logical_name': logical_name
                    }

        # Use lock only when updating shared state
        with self.lock:
            # Detect new jobs
            new_jobs = set(current_active_jobs.keys()) - set(self.previous_active_jobs.keys())
            for key in new_jobs:
                job_info = current_active_jobs[key]
                self.start_secondary_recording(job_info['basename'], job_info['logical_name'])

            # Detect stopped jobs
            stopped_jobs = set(self.previous_active_jobs.keys()) - set(current_active_jobs.keys())
            for key in stopped_jobs:
                job_info = self.previous_active_jobs.get(key)
                if job_info:
                    self.stop_secondary_recording(job_info['basename'], job_info['logical_name'])

            # Update the state
            self.previous_active_jobs = current_active_jobs.copy()
            self.save_state()

    def get_active_jobs_info(self):
        url = f'{self.api_base_url}/ingests/activejobsinfo'
        try:
            response = self.session.get(url, timeout=5)
            response.raise_for_status()
            try:
                data = response.json()
                if isinstance(data, list):
                    return data
                else:
                    logging.error("Invalid active jobs info format. Expected a list.")
                    return []
            except json.JSONDecodeError as e:
                logging.error(f"JSON decoding error while getting active jobs info: {e}")
                return []
        except requests.RequestException as e:
            logging.error(f"Failed to get active jobs info: {e}")
            return []

    def extract_basename(self, ingest_id, job_id):
        files_info = self.get_files_info(ingest_id, job_id)
        return self.extract_primary_file_basename(files_info)

    def get_files_info(self, ingest_id, job_id):
        url = f'{self.api_base_url}/ingests/{ingest_id}/jobs/{job_id}/files'
        try:
            response = self.session.get(url, timeout=5)
            response.raise_for_status()
            try:
                data = response.json()
                if isinstance(data, dict):
                    return data
                else:
                    logging.error(f"Invalid files info format for ingest {ingest_id}, job {job_id}. Expected a dictionary.")
                    return {}
            except json.JSONDecodeError as e:
                logging.error(f"JSON decoding error while getting files info for ingest {ingest_id}, job {job_id}: {e}")
                return {}
        except requests.RequestException as e:
            logging.error(f"Failed to get files info for ingest {ingest_id}, job {job_id}: {e}")
            return {}

    def extract_primary_file_basename(self, files_info):
        for file_data in files_info.get('data', []):
            if file_data.get('presetTag') == 'Primary':
                file_name = file_data.get('fileName')
                if file_name:
                    return file_name.rsplit('.', 1)[0]  # Remove file extension
        return None

    def is_job_still_active(self, ingest_id, job_id):
        # Optionally re-fetch the active jobs info or check the current state
        # For this example, we'll assume it's still active
        return True

    def start_secondary_recording(self, basename, logical_name):
        # Get the DVR source ID for the logical name
        dvr_source_id = self.logical_name_to_dvr_source_id.get(logical_name)
        if dvr_source_id is None:
            logging.error(f"No DVR source ID found for logical name {logical_name}")
            return

        # Check if DVR is already recording
        is_recording = self.is_dvr_recording(dvr_source_id)
        if is_recording:
            logging.info(f"DVR for {logical_name} is already recording")
            return

        # Set the recording name
        recording_name_url = f'{self.dvr_api_base_url}/sources/{dvr_source_id}/recording_name'
        payload = {
            "recording_name": basename
        }
        try:
            response = requests.put(recording_name_url, json=payload, timeout=5)
            response.raise_for_status()
            logging.info(f"Set recording name to {basename} for {logical_name}")
        except requests.RequestException as e:
            logging.error(f"Failed to set recording name for {logical_name}: {e}")
            return

        # Start the recording
        start_recording_url = f'{self.dvr_api_base_url}/sources/{dvr_source_id}/record'
        try:
            response = requests.get(start_recording_url, timeout=5)
            response.raise_for_status()
            logging.info(f"Started DVR recording for {logical_name}")
        except requests.RequestException as e:
            logging.error(f"Failed to start DVR recording for {logical_name}: {e}")
            return

    def stop_secondary_recording(self, basename, logical_name):
        # Get the DVR source ID for the logical name
        dvr_source_id = self.logical_name_to_dvr_source_id.get(logical_name)
        if dvr_source_id is None:
            logging.error(f"No DVR source ID found for logical name {logical_name}")
            return

        # Check if DVR is recording
        is_recording = self.is_dvr_recording(dvr_source_id)
        if not is_recording:
            logging.info(f"DVR for {logical_name} is not recording")
            return

        # Stop the recording
        stop_recording_url = f'{self.dvr_api_base_url}/sources/{dvr_source_id}/stop'
        try:
            response = requests.get(stop_recording_url, timeout=5)
            response.raise_for_status()
            logging.info(f"Stopped DVR recording for {logical_name}")
        except requests.RequestException as e:
            logging.error(f"Failed to stop DVR recording for {logical_name}: {e}")
            return

    def is_dvr_recording(self, dvr_source_id):
        sources_url = f'{self.dvr_api_base_url}/sources'
        try:
            response = requests.get(sources_url, timeout=5)
            response.raise_for_status()
            try:
                sources = response.json()
                if isinstance(sources, list):
                    # Ensure the source index is within bounds
                    if 0 <= dvr_source_id < len(sources):
                        source = sources[dvr_source_id]
                        return source.get('is_recording', False)
                    else:
                        logging.error(f"DVR source ID {dvr_source_id} is out of range.")
                else:
                    logging.error("Invalid sources data format. Expected a list.")
            except json.JSONDecodeError as e:
                logging.error(f"JSON decoding error while getting DVR sources: {e}")
        except requests.RequestException as e:
            logging.error(f"Failed to get DVR sources: {e}")
        return False

    def get_current_status(self):
        with self.lock:
            # Return a copy of the current active jobs
            return {
                '|'.join(k): v.copy() for k, v in self.previous_active_jobs.items()
            }

# Flask endpoint to get current statuses
@app.route('/status', methods=['GET'])
def get_status():
    data = monitor.get_current_status()
    return jsonify(data)

class FlaskServerThread(threading.Thread):
    def __init__(self, app, host='0.0.0.0', port=8000):
        threading.Thread.__init__(self)
        self.srv = make_server(host, port, app)
        self.ctx = app.app_context()
        self.ctx.push()
        self.daemon = True  # Allow thread to be killed when main thread exits

    def run(self):
        try:
            logging.info("Starting Flask server...")
            self.srv.serve_forever()
        except Exception as e:
            logging.error(f"Flask server encountered an error: {e}")

    def shutdown(self):
        logging.info("Shutting down Flask server...")
        self.srv.shutdown()

if __name__ == '__main__':
    # Get poll interval from environment variable or default to 5 seconds
    poll_interval = int(os.environ.get('POLL_INTERVAL', '5'))
    monitor = VideoRecorderMonitor(poll_interval=poll_interval)  # Poll every X seconds

    # Start the Flask app using Werkzeug server in a separate thread
    flask_port = int(os.environ.get('FLASK_PORT', '8001'))
    flask_server = FlaskServerThread(app, host='0.0.0.0', port=flask_port)
    flask_server.start()

    try:
        # Run the monitoring loop
        monitor.run_monitoring_loop()
    except KeyboardInterrupt:
        logging.info("Received KeyboardInterrupt, shutting down...")
    except Exception as e:
        logging.error(f"An unexpected error occurred in the main thread: {e}")
    finally:
        # Ensure that the Flask server is shut down
        flask_server.shutdown()
        logging.info("Application has been gracefully shut down.")
