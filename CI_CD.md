# Video Recorder Monitor - CI/CD Pipeline Documentation

## Overview

Python application that monitors PlayBox ingest system and synchronizes recordings with MovieRecorder DVR. Automated CI/CD via Woodpecker CI to Docker Swarm.

## Infrastructure

**Docker Swarm Cluster:**
- Nodes: 10.1.81.50, 10.1.81.51, 10.1.81.52
- Portainer: https://10.1.81.50:9443
- Network: VLAN 81

**External Services:**
- PlayBox Ingest API: http://10.1.83.21:4230
- MovieRecorder DVR API: http://10.1.85.53:8080
- Woodpecker CI: https://ci.tvwmedia.net
- Docker Registry: Docker Hub (scottftvw organization)
- Storage: CephFS (/mnt/cephfs/swarm-volumes/dvr-trigger/)

**Status Endpoint:**
- Monitoring: http://dvr-trigger.local.tvw.org:8001/status (if exposed)

## CI/CD Pipeline

### Pipeline Trigger

Runs automatically on:
- **Push events** to `main` branch (via GitHub webhook)
- **Manual triggers** from Woodpecker UI
- **Cron schedule** (periodic checks)

### Pipeline Steps

1. **check-if-built** (cron only)
   - Checks Docker Hub if image exists for commit SHA
   - Skips build if found
   - Only runs on cron events to avoid duplicate builds

2. **test**
   - Runs `pip install` and `python -m py_compile app.py`
   - Uses Python 3.10-slim image
   - No formal test suite configured yet

3. **build**
   - Builds Docker image with Python 3.10-slim
   - Tags with `:latest` and `:${COMMIT_SHA}` (first 8 chars)
   - Pushes to Docker Hub: `scottftvw/video-recorder-monitor`

4. **update-stack**
   - Updates `stack.yml` with commit SHA tag
   - Connects to Portainer API
   - Updates or creates stack named `dvr-trigger`
   - Forces service redeployment

### Required Secrets

- `docker_username` - Docker Hub username
- `docker_password` - Docker Hub access token
- `portainer_token` - Portainer API key

## Deployment Process

### Automated Deployment

1. Push to `main` branch
2. GitHub webhook triggers Woodpecker
3. Image built and pushed to Docker Hub
4. Portainer stack updated
5. Docker Swarm deploys new image

**Deployment time:** 3-5 minutes

### Manual Deployment

```bash
# Via Woodpecker CI
https://ci.tvwmedia.net → TVWIT/MovieRecord-from-PlaybBox-injest → Run Pipeline

# Via Portainer UI
https://10.1.81.50:9443 → Stacks → dvr-trigger → Update
```

### Rollback

```bash
ssh ubuntu@10.1.81.50
sudo docker service update dvr-trigger_dvr-monitor \
  --image scottftvw/video-recorder-monitor:PREVIOUS_SHA
```

## Service Configuration

**Service: `dvr-monitor`**
- Image: `scottftvw/video-recorder-monitor:{commit-sha}`
- Replicas: 1 (must remain 1 to avoid duplicate recording triggers)
- Placement: manager nodes only

**Environment Variables:**
- `PRIMARY_API_URL` - PlayBox API URL (http://10.1.83.21:4230)
- `DVR_API_URL` - MovieRecorder API URL (http://10.1.85.53:8080)
- `LOG_LEVEL` - Logging level (info)
- `CHECK_INTERVAL` - Polling interval in milliseconds (60000 = 1 minute)

**CephFS Volumes:**
- `/mnt/cephfs/swarm-volumes/dvr-trigger/logs` → `/app/logs`
- `/mnt/cephfs/swarm-volumes/dvr-trigger/state` → `/app/state`

**No Traefik Labels:**
- Background monitoring service with no web UI
- Status endpoint available on port 8001 (not exposed externally)

## Monitoring and Troubleshooting

### Check Service Status

```bash
ssh ubuntu@10.1.81.50
sudo docker stack services dvr-trigger
sudo docker service logs dvr-trigger_dvr-monitor --tail 100
sudo docker service ps dvr-trigger_dvr-monitor
```

### Check Application Logs

```bash
# View logs on CephFS
ssh ubuntu@10.1.81.50
cat /mnt/cephfs/swarm-volumes/dvr-trigger/logs/app.log

# View state file
cat /mnt/cephfs/swarm-volumes/dvr-trigger/state/state.json
```

### Check Recording Status

```bash
# Query status endpoint (if port is exposed)
curl http://10.1.81.50:8001/status

# Check PlayBox API directly
curl http://10.1.83.21:4230/ingests/activejobsinfo

# Check DVR API directly
curl http://10.1.85.53:8080/sources
```

### Common Issues

**Issue: Recordings not starting on DVR**
```
Playbox shows active jobs but DVR doesn't start
```
**Solution:**
- Verify network connectivity to both APIs
- Check logical name to source ID mapping in app.py
- Review logs for API errors: `docker service logs dvr-trigger_dvr-monitor`
- Ensure DVR sources are available and not already recording

**Issue: State file corruption**
```
Application fails to start or behaves erratically
```
**Solution:**
- SSH into any Swarm node
- Delete state file: `rm /mnt/cephfs/swarm-volumes/dvr-trigger/state/state.json`
- Restart service: `docker service update --force dvr-trigger_dvr-monitor`

**Issue: API connection errors**
```
Failed to connect to PlayBox or DVR API
```
**Solution:**
- Verify APIs are accessible from Swarm nodes
- Test connectivity: `curl http://10.1.83.21:4230/ingests/activejobsinfo`
- Check firewall rules between VLAN 81 and VLAN 83/85
- Ensure API endpoints are running

**Issue: Duplicate recordings**
```
Multiple recordings started for same job
```
**Solution:**
- **Critical:** Service must have exactly 1 replica
- Check: `docker service inspect dvr-trigger_dvr-monitor --format '{{.Spec.Mode.Replicated.Replicas}}'`
- If >1, scale down: `docker service scale dvr-trigger_dvr-monitor=1`

## Stack File Reference

```yaml
version: '3.8'

services:
  dvr-monitor:
    image: scottftvw/video-recorder-monitor:latest
    environment:
      - PRIMARY_API_URL=http://10.1.83.21:4230
      - DVR_API_URL=http://10.1.85.53:8080
      - LOG_LEVEL=info
      - CHECK_INTERVAL=60000
    volumes:
      - dvr-logs:/app/logs
      - dvr-state:/app/state
    networks:
      - dvr-network
    deploy:
      replicas: 1
      placement:
        constraints:
          - node.role == manager
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3

volumes:
  dvr-logs:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/cephfs/swarm-volumes/dvr-trigger/logs
  dvr-state:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/cephfs/swarm-volumes/dvr-trigger/state

networks:
  dvr-network:
    driver: overlay
```

## Development Workflow

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export PRIMARY_API_URL=http://10.1.83.21:4230
export DVR_API_URL=http://10.1.85.53:8080

# Run application
python app.py
```

### Making Changes

1. Create feature branch
2. Make changes and test locally
3. Commit and push
4. Create PR to `main`
5. Merge triggers automatic deployment

## Application Architecture

### Core Components

**VideoRecorderMonitor Class (app.py):**
- Main monitoring loop
- Polls PlayBox API every minute
- Compares current vs previous state
- Starts/stops DVR recordings as needed
- Saves state to JSON file

**Flask Status Server:**
- Runs in separate thread
- Provides `/status` endpoint
- Returns JSON with current recording status
- Port 8001 (not exposed externally in current config)

**State Management:**
- Persists active recordings to `/app/state/state.json`
- Enables graceful restarts without duplicate triggers
- Prevents missed recordings during downtime

### API Integration

**PlayBox Ingest API:**
- Endpoint: `GET /ingests/activejobsinfo`
- Returns active recording jobs with `ingestId`, `jobId`, `basename`
- Polled every 60 seconds (configurable)

**MovieRecorder DVR API:**
- `GET /sources` - List available recording sources
- `PUT /sources/{id}/recording_name` - Set recording filename
- `GET /sources/{id}/record` - Start recording
- `GET /sources/{id}/stop` - Stop recording

**Source ID Mapping:**
Logical names from PlayBox map to DVR source IDs (configured in app.py):
- "PCR 1" → Source ID 1
- "PCR 2" → Source ID 2
- etc.

### Data Flow

1. Poll PlayBox API → Get active jobs
2. Compare with previous state → Detect changes
3. For new jobs → Start DVR recording
4. For stopped jobs → Stop DVR recording
5. Update state file → Save current jobs
6. Sleep 60 seconds → Repeat

## Security Considerations

- No authentication on PlayBox or DVR APIs (internal network only)
- Services must be on same network as APIs
- State file contains recording info (not sensitive)
- No secrets required for this application

## Maintenance

### Updating Dependencies

```bash
pip install --upgrade -r requirements.txt
pip freeze > requirements.txt
git commit -am "Update Python dependencies"
git push origin main  # Triggers CI/CD
```

### Monitoring Logs

```bash
# View recent logs
tail -f /mnt/cephfs/swarm-volumes/dvr-trigger/logs/app.log

# Search for errors
grep ERROR /mnt/cephfs/swarm-volumes/dvr-trigger/logs/app.log

# Check state
cat /mnt/cephfs/swarm-volumes/dvr-trigger/state/state.json | jq .
```

### Scaling

**WARNING:** This service must NOT be scaled beyond 1 replica. Multiple instances would trigger duplicate recordings.

## Important Notes

- **Single Replica Only:** Multiple instances will cause duplicate recording triggers
- **Network Dependencies:** Requires access to VLANs 83 and 85 from VLAN 81
- **Polling Interval:** 60 seconds default (configurable via CHECK_INTERVAL)
- **No Web UI:** Background service only, status endpoint for monitoring
- **Stateful Service:** Uses state file to track recordings across restarts

---

**Last Updated:** 2025-11-05
**Pipeline Status:** https://ci.tvwmedia.net/repos/5
**Portainer Stack:** https://10.1.81.50:9443
