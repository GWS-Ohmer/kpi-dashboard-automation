import os
import json
import math
import sys
import logging
import time
import traceback
from datetime import datetime
import io
import urllib.parse
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError

# ─── Logging Configuration ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────
ITH_DRIVE_FOLDER_ID = os.environ.get("ITH_DRIVE_FOLDER_ID")
ISSD_DRIVE_FOLDER_ID = os.environ.get("ISSD_DRIVE_FOLDER_ID")
COMBINED_DRIVE_FOLDER_ID = os.environ.get("COMBINED_DRIVE_FOLDER_ID")

CHUNK_SIZE = 4000

# ─── Retry Configuration ──────────────────────────────────────────────────────
MAX_RETRIES = 5
INITIAL_BACKOFF = 1  # seconds

# ─── Google Drive Helpers ─────────────────────────────────────────────────
def get_drive_service():
    """Authenticate with Google Drive using OAuth credentials."""
    creds_json = os.environ.get("GCP_USER_CREDENTIALS")
    if not creds_json:
        raise RuntimeError("GCP_USER_CREDENTIALS environment variable missing.")
    
    try:
        creds_dict = json.loads(creds_json)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse GCP_USER_CREDENTIALS as JSON: %s", e)
        raise
    
    # Validate required fields
    required_fields = ['refresh_token', 'client_id', 'client_secret']
    for field in required_fields:
        if field not in creds_dict:
            raise RuntimeError(f"GCP credentials missing required field: {field}")
    
    # Remove 'scopes' parameter since it is invalid for standard OAuth refresh tokens
    credentials = Credentials(
        token=None,
        refresh_token=creds_dict.get('refresh_token'),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=creds_dict.get('client_id'),
        client_secret=creds_dict.get('client_secret')
    )
    return build('drive', 'v3', credentials=credentials)

def download_json_from_drive(service, folder_id, filename):
    """Download JSON file from Drive folder."""
    query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    items = results.get('files', [])
    if not items:
        return None
    
    file_id = items[0]['id']
    request = service.files().get_media(fileId=file_id)
    file_data = request.execute()
    return json.loads(file_data.decode('utf-8'))

def upload_json_to_drive_with_retries(service, filename, data_dict, max_retries=MAX_RETRIES):
    """Upload JSON to Drive with exponential backoff retry logic."""
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Uploading {filename} (attempt {attempt}/{max_retries})")
            
            query = f"name='{filename}' and '{COMBINED_DRIVE_FOLDER_ID}' in parents and trashed=false"
            results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
            items = results.get('files', [])
            
            file_metadata = {'name': filename}
            media = MediaIoBaseUpload(
                io.BytesIO(json.dumps(data_dict).encode('utf-8')),
                mimetype='application/json',
                resumable=True
            )
            
            if items:
                file_id = items[0]['id']
                service.files().update(fileId=file_id, media_body=media).execute()
                logger.info(f"Updated existing file: {filename}")
            else:
                file_metadata['parents'] = [COMBINED_DRIVE_FOLDER_ID]
                service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                logger.info(f"Created new file: {filename}")
            
            return  # Success, exit retry loop
            
        except HttpError as e:
            logger.warning(f"Google Drive API error on attempt {attempt}/{max_retries}: {e}")
            if attempt == max_retries:
                logger.error(f"Max retries reached for {filename}. Giving up.")
                raise
        except Exception as e:
            logger.warning(f"Unexpected error on attempt {attempt}/{max_retries}: {e}")
            if attempt == max_retries:
                logger.error(f"Max retries reached for {filename}. Giving up.")
                raise
        
        # Exponential backoff with jitter
        sleep_time = min(60, (2 ** attempt) + (attempt * 0.1))
        logger.info(f"Retrying in {sleep_time:.1f} seconds...")
        time.sleep(sleep_time)

# ─── Cache Reading ────────────────────────────────────────────────────────
def read_cache_shards(service, folder_id, prefix):
    """Read all shards from a folder and combine into single list."""
    logger.info(f"Reading cache from folder {folder_id} with prefix '{prefix}'...")
    
    all_tickets = []
    shard_idx = 0
    while True:
        filename = f"{prefix}_{shard_idx}.json"
        try:
            shard_data = download_json_from_drive(service, folder_id, filename)
            if shard_data is None:
                break
            
            # Handle both direct array and wrapped format
            if isinstance(shard_data, list):
                all_tickets.extend(shard_data)
            else:
                all_tickets.extend(shard_data)
            
            logger.info(f"Read shard {shard_idx}: {len(shard_data)} tickets")
            shard_idx += 1
        except Exception as e:
            logger.warning(f"Error reading shard {shard_idx}: {e}")
            break
    
    logger.info(f"Total tickets read from {folder_id}: {len(all_tickets)}")
    return all_tickets

def add_source_tag(tickets, source):
    """Add source field to all tickets."""
    for ticket in tickets:
        ticket["source"] = source
    return tickets

def calculate_combined_metrics(ith_tickets, issd_tickets):
    """Calculate combined metrics from both sources."""
    all_tickets = ith_tickets + issd_tickets
    
    automated_count = sum(1 for t in all_tickets if t.get("isAutomated", False))
    manual_count = len(all_tickets) - automated_count
    
    metrics = {
        "total": len(all_tickets),
        "ith_count": len(ith_tickets),
        "issd_count": len(issd_tickets),
        "automated": automated_count,
        "automated_percent": round(100 * automated_count / len(all_tickets), 1) if len(all_tickets) > 0 else 0,
        "manual": manual_count,
        "manual_percent": round(100 * manual_count / len(all_tickets), 1) if len(all_tickets) > 0 else 0,
        "categories": {
            "Shared Drive Creation": sum(1 for t in all_tickets if t.get("category") == "Shared Drive Creation"),
            "Google Group Creation": sum(1 for t in all_tickets if t.get("category") == "Google Group Creation"),
            "Bookable Meeting Room": sum(1 for t in all_tickets if t.get("category") == "Bookable Meeting Room"),
            "Other": sum(1 for t in all_tickets if t.get("category") == "Other")
        }
    }
    
    return metrics

# ─── Main Pipeline ────────────────────────────────────────────────────────
def run_pipeline():
    """Main sync pipeline: read both caches, combine, calculate metrics, upload."""
    if not COMBINED_DRIVE_FOLDER_ID:
        logger.error("COMBINED_DRIVE_FOLDER_ID missing. Exiting.")
        raise RuntimeError("COMBINED_DRIVE_FOLDER_ID environment variable not set")
    
    if not ITH_DRIVE_FOLDER_ID or not ISSD_DRIVE_FOLDER_ID:
        logger.error("ITH_DRIVE_FOLDER_ID or ISSD_DRIVE_FOLDER_ID missing. Exiting.")
        raise RuntimeError("ITH/ISSD folder IDs not set")
    
    logger.info("Authenticating with Google Drive...")
    service = get_drive_service()
    logger.info("Google Drive authentication successful")
    
    # 1. Read ITH cache
    logger.info("Reading ITH Dashboard cache...")
    ith_tickets = read_cache_shards(service, ITH_DRIVE_FOLDER_ID, "dash_tickets_all_shard")
    ith_tickets = add_source_tag(ith_tickets, "ITH")
    logger.info(f"Read {len(ith_tickets)} tickets from ITH")
    
    # 2. Read ISSD cache
    logger.info("Reading ISSD Dashboard cache...")
    issd_tickets = read_cache_shards(service, ISSD_DRIVE_FOLDER_ID, "dash_tickets_all_shard")
    issd_tickets = add_source_tag(issd_tickets, "ISSD")
    logger.info(f"Read {len(issd_tickets)} tickets from ISSD")
    
    # 3. Combine tickets
    final_tickets = ith_tickets + issd_tickets
    logger.info(f"Combined total: {len(final_tickets)} tickets")
    
    # 4. Sort by created date descending (newest first)
    def get_date(t):
        try:
            return datetime.strptime(t.get("created", ""), "%Y-%m-%dT%H:%M:%S.%f%z")
        except:
            return datetime.min
    final_tickets.sort(key=get_date, reverse=True)
    
    # 5. Calculate combined metrics
    logger.info("Calculating combined metrics...")
    metrics = calculate_combined_metrics(ith_tickets, issd_tickets)
    logger.info(f"Metrics: {metrics['total']} total ({metrics['ith_count']} ITH + {metrics['issd_count']} ISSD)")
    logger.info(f"Automated: {metrics['automated']} ({metrics['automated_percent']}%), Manual: {metrics['manual']} ({metrics['manual_percent']}%)")
    
    # 6. Upload to Drive
    logger.info("Starting Drive upload phase...")
    
    # Upload summary
    summary_payload = {
        "savedAt": datetime.utcnow().isoformat() + "Z",
        "key": "dash_tickets_summary",
        "data": metrics
    }
    upload_json_to_drive_with_retries(service, "dash_tickets_summary.json", summary_payload)
    
    # Clean up old shards
    logger.info("Cleaning up old shards...")
    try:
        query = f"name contains 'dash_tickets_all_shard_' and '{COMBINED_DRIVE_FOLDER_ID}' in parents and trashed=false"
        old_shards = service.files().list(q=query, spaces='drive', fields='files(id)').execute().get('files', [])
        for f in old_shards:
            service.files().delete(fileId=f['id']).execute()
        logger.info(f"Deleted {len(old_shards)} old shard(s)")
    except Exception as e:
        logger.warning(f"Error cleaning up old shards: {e}")
    
    # Upload shards
    shard_count = math.ceil(len(final_tickets) / CHUNK_SIZE)
    if shard_count == 0:
        shard_count = 1
    
    logger.info(f"Uploading {shard_count} shard(s) with {CHUNK_SIZE} tickets per shard...")
    for i in range(shard_count):
        chunk = final_tickets[i*CHUNK_SIZE : (i+1)*CHUNK_SIZE]
        upload_json_to_drive_with_retries(service, f"dash_tickets_all_shard_{i}.json", chunk)
    
    # Upload metadata
    meta_payload = {
        "savedAt": datetime.utcnow().isoformat() + "Z",
        "key": "dash_tickets_all",
        "count": len(final_tickets),
        "shards": shard_count,
        "chunkSize": CHUNK_SIZE
    }
    upload_json_to_drive_with_retries(service, "dash_tickets_all_meta.json", meta_payload)
    logger.info("Drive sync complete!")

def main():
    """Main entry point with top-level error handling."""
    try:
        logger.info("=== STARTING COMBINED KPI DASHBOARD SYNC ===")
        
        run_pipeline()
        logger.info("=== SYNC COMPLETED SUCCESSFULLY ===")
        
    except Exception as e:
        logger.error(f"SYNC FAILED: {e}")
        logger.error("Full traceback:")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
