# KPI Dashboard [ISSD/ITH] — Automated Sync

Unified KPI Dashboard combining ITH and ISSD Jira tickets into a single read-only dashboard with identical architecture to both source dashboards.

## Architecture

```
ITH Drive Cache (34k tickets)  ─┐
                                ├──→ [Python Sync] ──→ COMBINED Drive Cache ──→ [Web App UI]
ISSD Drive Cache (2.5k tickets)─┘
```

## Features

- **Read-only:** No mutations, pure data display
- **Combined metrics:** Total tickets, automated vs manual counts/percentages, category breakdown
- **Same filters as source dashboards:** Time (This Year/Month/14 Days/Custom), Status (All/Resolved/Open), Scope (All/Shared Drive/Google Group/Meeting Room)
- **New "Source" filter:** View All / ITH Only / ISSD Only
- **Syncs every 15 minutes:** Balanced freshness without overhead
- **Error handling + retries:** Exponential backoff with comprehensive logging
- **Artifact logging:** Full sync logs uploaded after every run

## Setup

### 1. Google Drive Folder

Create a new Google Drive folder for the combined cache. Note the folder ID.

### 2. GitHub Repository Secrets

Set these secrets in the GitHub repository settings:

```
ITH_DRIVE_FOLDER_ID           → 1LGqIZeyA41RcY0QJ3QstSAbnXN7qfYWB (ITH cache folder)
ISSD_DRIVE_FOLDER_ID          → 1iShbY4fuMunzpnca0zvPmhTRVwPsj-5F (ISSD cache folder)
COMBINED_DRIVE_FOLDER_ID      → (new folder ID created above)
GCP_USER_CREDENTIALS          → (existing OAuth credentials JSON)
```

### 3. Deploy

Push to GitHub and the workflow will run automatically every 15 minutes.

**Manual trigger:** `gh workflow run sync.yml --repo GWS-Ohmer/kpi-dashboard-automation`

## Sync Process

1. **Read ITH cache:** Fetch all shards from ITH Drive folder
2. **Read ISSD cache:** Fetch all shards from ISSD Drive folder
3. **Add source tag:** Mark each ticket with `source: "ITH"` or `source: "ISSD"`
4. **Combine:** Merge both arrays
5. **Calculate metrics:** Total, automated %, manual %, category breakdown
6. **Upload to COMBINED folder:**
   - `dash_tickets_summary.json` — metrics
   - `dash_tickets_all_meta.json` — metadata (shard count, chunk size)
   - `dash_tickets_all_shard_0.json`, `dash_tickets_all_shard_1.json`, etc. — combined tickets (4000 per shard)

## Troubleshooting

### Sync logs

Check GitHub Actions → Workflow runs → select run → Artifacts → `sync-logs-*`

### Common errors

- **GCP_USER_CREDENTIALS missing:** Check GitHub secrets
- **Drive API quota exceeded:** Retries with exponential backoff; wait a few minutes
- **Folder not found:** Verify folder IDs in secrets
- **No tickets read:** Check ITH/ISSD cache folders have recent files

### Local testing

```bash
export ITH_DRIVE_FOLDER_ID=1LGqIZeyA41RcY0QJ3QstSAbnXN7qfYWB
export ISSD_DRIVE_FOLDER_ID=1iShbY4fuMunzpnca0zvPmhTRVwPsj-5F
export COMBINED_DRIVE_FOLDER_ID=<your-folder-id>
export GCP_USER_CREDENTIALS='{"refresh_token":"...","client_id":"...","client_secret":"..."}'

pip install -r requirements.txt
python sync.py
```

## Files

- `sync.py` — Main sync pipeline (read both caches, combine, upload)
- `requirements.txt` — Python dependencies
- `.github/workflows/sync.yml` — GitHub Actions workflow (every 15 minutes)
- `README.md` — This file

## References

- ITH Dashboard: `1Jh23848hVKFBVZ2fjAuq-RIUD603wFZlucAdSAgvUf1qivTt7LrNY_H4` (read-only, do not modify)
- ISSD Dashboard: `1DvcwgjwJHKyZgS2k_QiVL3mSlP6XbyXY0hq2_YPLcPdjSoWhI0GsEH9J`
- Template: `GWS-Ohmer/issd-dashboard-automation` — ISSD sync pattern
