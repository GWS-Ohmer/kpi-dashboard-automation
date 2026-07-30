#!/usr/bin/env python3
"""
Deploy KPI Dashboard to new Apps Script project
"""
import json
import subprocess
import sys
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

def load_credentials():
    """Load GCP credentials from environment or file"""
    # Try to load from environment variable first
    cred_json = os.getenv('GCP_USER_CREDENTIALS')
    if cred_json:
        cred_dict = json.loads(cred_json)
    else:
        # Fall back to credentials.json
        cred_file = Path('credentials.json')
        if cred_file.exists():
            with open(cred_file) as f:
                cred_dict = json.load(f)
        else:
            raise ValueError("No credentials found. Set GCP_USER_CREDENTIALS or credentials.json")
    
    return Credentials.from_service_account_info(
        cred_dict,
        scopes=['https://www.googleapis.com/auth/script.projects']
    )

def create_script_project(title):
    """Create a new Apps Script project"""
    credentials = load_credentials()
    service = build('script', 'v1', credentials=credentials)
    
    request_body = {
        'title': title
    }
    
    request = service.projects().create(body=request_body)
    result = request.execute()
    
    return result['scriptId']

def push_files(script_id):
    """Push files to Apps Script via clasp"""
    # Update .clasp.json with script ID
    clasp_config = {
        'scriptId': script_id,
        'rootDir': '.'
    }
    
    with open('.clasp.json', 'w') as f:
        json.dump(clasp_config, f, indent=2)
    
    # Run clasp push
    result = subprocess.run(['npx', 'clasp', 'push', '-f'], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Push failed: {result.stderr}")
        return False
    
    print(f"Push succeeded: {result.stdout}")
    return True

if __name__ == '__main__':
    import os
    
    print("Creating new Apps Script project...")
    try:
        script_id = create_script_project('KPI Dashboard [ISSD/ITH]')
        print(f"✅ Project created: {script_id}")
        
        print("Pushing files...")
        if push_files(script_id):
            print("✅ Files deployed successfully!")
            print(f"Script ID: {script_id}")
            sys.exit(0)
        else:
            print("❌ Push failed")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
