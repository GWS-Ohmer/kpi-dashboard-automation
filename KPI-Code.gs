/**
 * KPI Dashboard [ISSD/ITH Combined] — Backend Logic
 * 
 * Combines ITH and ISSD ticket caches into a single read-only dashboard.
 * Filters: Time, Status, Scope, Source (All/ITH/ISSD)
 * Tabs: All / ITH Only / ISSD Only / Automated (L0) / Manual (L1/L2)
 * Metrics: Total, Automated %, Manual %, ITH count, ISSD count, Status breakdown
 */

const CONFIG = {
  COMBINED_FOLDER_ID: PropertiesService.getScriptProperties().getProperty('COMBINED_FOLDER_ID') || 'YOUR_FOLDER_ID_HERE',
  CACHE_LIFETIME_MINUTES: 5
};

/**
 * Web App entry point — serves the dashboard HTML
 */
function doGet(e) {
  const htmlTemplate = HtmlService.createTemplateFromFile('Dashboard');
  htmlTemplate.scriptUrl = ScriptApp.getUrl();
  return htmlTemplate.evaluate()
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .setSandboxMode(HtmlService.SandboxMode.NATIVE);
}

/**
 * Fetch and parse combined dashboard data from Drive cache
 * Returns: { tickets: [...], metadata: {...}, metrics: {...} }
 */
function loadDashboard() {
  try {
    const cacheKey = 'kpi_dashboard_data';
    const cache = CacheService.getScriptCache();
    const cached = cache.get(cacheKey);
    
    if (cached) {
      return JSON.parse(cached);
    }

    const folderID = CONFIG.COMBINED_FOLDER_ID;
    if (!folderID || folderID === 'YOUR_FOLDER_ID_HERE') {
      return {
        error: 'COMBINED_FOLDER_ID not configured. Set in Script Properties.',
        tickets: [],
        metadata: null,
        metrics: null
      };
    }

    const folder = DriveApp.getFolderById(folderID);
    const files = folder.getFilesByName('dash_tickets_all_shard_0.json');
    
    if (!files.hasNext()) {
      return {
        error: 'Metadata file not found in Drive cache. Sync may still be in progress.',
        tickets: [],
        metadata: null,
        metrics: null
      };
    }

    // Load all shards
    const allTickets = [];
    let shardIndex = 0;
    let hasMore = true;

    while (hasMore) {
      const shardName = `dash_tickets_all_shard_${shardIndex}.json`;
      const shardFiles = folder.getFilesByName(shardName);
      
      if (!shardFiles.hasNext()) {
        hasMore = false;
        break;
      }

      const shardFile = shardFiles.next();
      const shardContent = shardFile.getBlob().getDataAsString();
      const shardData = JSON.parse(shardContent);
      
      if (Array.isArray(shardData)) {
        allTickets.push(...shardData);
      }
      
      shardIndex++;
    }

    // Load metadata
    let metadata = null;
    const metaFiles = folder.getFilesByName('dash_tickets_all_meta.json');
    if (metaFiles.hasNext()) {
      const metaContent = metaFiles.next().getBlob().getDataAsString();
      metadata = JSON.parse(metaContent);
    }

    // Load metrics/summary
    let metrics = null;
    const summaryFiles = folder.getFilesByName('dash_tickets_summary.json');
    if (summaryFiles.hasNext()) {
      const summaryContent = summaryFiles.next().getBlob().getDataAsString();
      metrics = JSON.parse(summaryContent);
    }

    const result = {
      tickets: allTickets,
      metadata: metadata,
      metrics: metrics,
      error: null
    };

    // Cache for 5 minutes
    cache.put(cacheKey, JSON.stringify(result), CONFIG.CACHE_LIFETIME_MINUTES * 60);

    return result;
  } catch (error) {
    Logger.log('loadDashboard error: ' + error.toString());
    return {
      error: error.toString(),
      tickets: [],
      metadata: null,
      metrics: null
    };
  }
}

/**
 * Apply filters to ticket list
 * Filters: timeRange, status, scope, source, automation
 */
function getFilteredTickets(filters) {
  try {
    const data = loadDashboard();
    if (data.error) {
      return { error: data.error, tickets: [], count: 0 };
    }

    let tickets = data.tickets || [];

    // Filter by source (ITH / ISSD / All)
    if (filters.source && filters.source !== 'All') {
      tickets = tickets.filter(t => t.source === filters.source);
    }

    // Filter by automation (L0 / L1/L2 / All)
    if (filters.automation && filters.automation !== 'All') {
      if (filters.automation === 'Automated') {
        tickets = tickets.filter(t => t.isAutomated === true);
      } else if (filters.automation === 'Manual') {
        tickets = tickets.filter(t => t.isAutomated === false);
      }
    }

    // Filter by time range
    if (filters.timeRange && filters.timeRange !== 'All Time') {
      const now = new Date();
      let startDate;

      switch (filters.timeRange) {
        case 'This Year':
          startDate = new Date(now.getFullYear(), 0, 1);
          break;
        case 'This Month':
          startDate = new Date(now.getFullYear(), now.getMonth(), 1);
          break;
        case 'Last 14 Days':
          startDate = new Date(now.getTime() - 14 * 24 * 60 * 60 * 1000);
          break;
        case 'Custom':
          if (filters.customStartDate) {
            startDate = new Date(filters.customStartDate);
          }
          break;
        default:
          startDate = null;
      }

      if (startDate) {
        tickets = tickets.filter(t => {
          const created = new Date(t.created);
          return created >= startDate;
        });
      }
    }

    // Filter by status
    if (filters.status && filters.status !== 'All') {
      tickets = tickets.filter(t => {
        const status = t.status ? t.status.toLowerCase() : '';
        if (filters.status === 'Open') {
          return status.includes('open') || status.includes('in progress');
        } else if (filters.status === 'Resolved') {
          return status.includes('resolved') || status.includes('done') || status.includes('closed');
        }
        return true;
      });
    }

    // Filter by scope
    if (filters.scope && filters.scope !== 'All') {
      tickets = tickets.filter(t => t.scope === filters.scope);
    }

    return {
      tickets: tickets,
      count: tickets.length,
      error: null
    };
  } catch (error) {
    Logger.log('getFilteredTickets error: ' + error.toString());
    return { error: error.toString(), tickets: [], count: 0 };
  }
}

/**
 * Calculate dashboard metrics
 */
function getMetrics(filters) {
  try {
    const data = loadDashboard();
    if (data.error) {
      return { error: data.error };
    }

    const allTickets = data.tickets || [];
    const filtered = getFilteredTickets(filters).tickets || [];

    const metrics = {
      total: filtered.length,
      automated: filtered.filter(t => t.isAutomated === true).length,
      manual: filtered.filter(t => t.isAutomated === false).length,
      ith_count: filtered.filter(t => t.source === 'ITH').length,
      issd_count: filtered.filter(t => t.source === 'ISSD').length,
      open: filtered.filter(t => {
        const s = (t.status || '').toLowerCase();
        return s.includes('open') || s.includes('in progress');
      }).length,
      resolved: filtered.filter(t => {
        const s = (t.status || '').toLowerCase();
        return s.includes('resolved') || s.includes('done') || s.includes('closed');
      }).length,
      automated_percent: filtered.length > 0 ? Math.round((filtered.filter(t => t.isAutomated === true).length / filtered.length) * 100) : 0,
      manual_percent: filtered.length > 0 ? Math.round((filtered.filter(t => t.isAutomated === false).length / filtered.length) * 100) : 0
    };

    return metrics;
  } catch (error) {
    Logger.log('getMetrics error: ' + error.toString());
    return { error: error.toString() };
  }
}

/**
 * Get dashboard data for display (all info + filtered list)
 */
function getDashboardData(filters) {
  try {
    const data = loadDashboard();
    if (data.error) {
      return { error: data.error };
    }

    const filtered = getFilteredTickets(filters);
    const metrics = getMetrics(filters);

    return {
      tickets: filtered.tickets,
      metrics: metrics,
      summary: data.metrics,
      error: null
    };
  } catch (error) {
    Logger.log('getDashboardData error: ' + error.toString());
    return { error: error.toString() };
  }
}
