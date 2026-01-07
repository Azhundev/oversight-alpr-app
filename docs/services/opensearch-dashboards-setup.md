# OpenSearch Dashboards Setup Guide

**Purpose**: Configure OpenSearch Dashboards to visualize and explore ALPR event data.

---

## Overview

OpenSearch Dashboards is the web UI for OpenSearch (similar to Kibana for Elasticsearch). It provides:
- **Discover**: Search and filter event data
- **Visualize**: Create charts and graphs
- **Dashboard**: Build monitoring dashboards
- **Dev Tools**: Query OpenSearch directly

**Current Data in OpenSearch**:
```bash
# Check indices and document counts
curl http://localhost:9200/_cat/indices?v | grep alpr-events

# Sample output:
# alpr-events-2025.12   117 documents
# alpr-events-2026.01    22 documents
```

---

## Initial Setup

### Step 1: Access OpenSearch Dashboards

**URL**: http://localhost:5601

**Note**: OpenSearch Dashboards uses the `analytics` profile in docker-compose.yml, so it must be started explicitly:

```bash
# Start with analytics profile
docker compose --profile analytics up -d

# Or if already running without profile
docker compose up -d opensearch-dashboards
```

### Step 2: Create Index Pattern

When you first access OpenSearch Dashboards, you need to create an **index pattern** to tell Dashboards which indices to query.

1. **Navigate to Stack Management**:
   - Click the hamburger menu (☰) in top-left
   - Go to **Management** → **Stack Management**
   - Click **Index Patterns** (under Dashboards Management)

2. **Create Index Pattern**:
   - Click **Create index pattern**
   - **Index pattern name**: `alpr-events-*`
     - This matches all ALPR event indices (alpr-events-2025.12, alpr-events-2026.01, etc.)
   - Click **Next step**

3. **Configure Time Field**:
   - **Time field**: Select `captured_at`
     - This is the timestamp when the plate was captured
   - Click **Create index pattern**

✅ **Done!** Your index pattern is now created.

---

## Using Discover (Explore Data)

### Step 1: Navigate to Discover

- Click the hamburger menu (☰)
- Click **Discover** (under OpenSearch Dashboards)

### Step 2: Select Index Pattern

- In the top-left dropdown, select **alpr-events-***
- You should now see your ALPR events!

### Step 3: Explore the Data

**Time Range** (top-right):
- Default: Last 15 minutes
- Change to: **Last 7 days** or **Last 30 days** to see all data

**Available Fields** (left sidebar):
- `event_id`: Unique event identifier
- `captured_at`: Timestamp
- `camera_id`: Camera identifier
- `track_id`: Vehicle track ID
- `plate.text`: Raw plate text
- `plate.normalized_text`: Normalized plate text
- `plate.confidence`: OCR confidence score
- `plate.region`: Plate region (US-FL, etc.)
- `vehicle.type`: Vehicle type (car, truck, etc.)
- `vehicle.color`: Vehicle color
- `vehicle.make`: Vehicle make
- `vehicle.model`: Vehicle model
- `images.plate_url`: Plate image URL
- `location.site_id`: Site identifier
- `location.host_id`: Edge device identifier

**Search Examples**:

```bash
# Find specific plate
plate.normalized_text: "ABC123"

# Find high-confidence reads
plate.confidence >= 0.9

# Find specific camera
camera_id: "CAM1"

# Find specific vehicle type
vehicle.type: "truck"

# Combine filters
plate.confidence >= 0.8 AND camera_id: "CAM1"
```

### Step 4: Add/Remove Columns

- Click the **+** icon next to fields to add them as columns
- Recommended columns:
  - `captured_at`
  - `camera_id`
  - `plate.normalized_text`
  - `plate.confidence`
  - `vehicle.type`

---

## Creating Visualizations

### Example 1: Top 10 Plates (Bar Chart)

1. **Navigate to Visualize**:
   - Hamburger menu → **Visualize**
   - Click **Create visualization**
   - Select **Bar** (vertical bar chart)

2. **Configure**:
   - **Index pattern**: `alpr-events-*`
   - **Metrics** (Y-axis):
     - Aggregation: **Count**
   - **Buckets** (X-axis):
     - Click **Add** → **X-axis**
     - Aggregation: **Terms**
     - Field: `plate.normalized_text.keyword`
     - Order by: **Metric: Count**
     - Order: **Descending**
     - Size: **10**
   - Click **Update** (▶)

3. **Save**:
   - Click **Save** (top-right)
   - Title: "Top 10 Plates"

### Example 2: Events Over Time (Line Chart)

1. **Create visualization**:
   - Select **Line** chart

2. **Configure**:
   - **Index pattern**: `alpr-events-*`
   - **Metrics** (Y-axis):
     - Aggregation: **Count**
   - **Buckets** (X-axis):
     - Click **Add** → **X-axis**
     - Aggregation: **Date Histogram**
     - Field: `captured_at`
     - Interval: **Auto** or **Hourly**
   - Click **Update** (▶)

3. **Save**:
   - Title: "Events Over Time"

### Example 3: Events by Camera (Pie Chart)

1. **Create visualization**:
   - Select **Pie** chart

2. **Configure**:
   - **Metrics**:
     - Aggregation: **Count**
   - **Buckets**:
     - Click **Add** → **Split slices**
     - Aggregation: **Terms**
     - Field: `camera_id.keyword`
     - Size: **10**
   - Click **Update** (▶)

3. **Save**:
   - Title: "Events by Camera"

### Example 4: Average Confidence by Camera

1. **Create visualization**:
   - Select **Bar** chart

2. **Configure**:
   - **Metrics** (Y-axis):
     - Aggregation: **Average**
     - Field: `plate.confidence`
   - **Buckets** (X-axis):
     - Aggregation: **Terms**
     - Field: `camera_id.keyword`
   - Click **Update** (▶)

3. **Save**:
   - Title: "Average OCR Confidence by Camera"

---

## Creating a Dashboard

### Step 1: Create Dashboard

1. **Navigate to Dashboard**:
   - Hamburger menu → **Dashboard**
   - Click **Create dashboard**

2. **Add Visualizations**:
   - Click **Add** (top-left)
   - Select the visualizations you created:
     - Top 10 Plates
     - Events Over Time
     - Events by Camera
     - Average OCR Confidence by Camera

3. **Arrange**:
   - Drag and resize panels to your preference
   - Click **Save** (top-right)
   - Title: "ALPR System Overview"

### Step 2: Set Time Range

- Use the time picker (top-right) to set the time range
- Common ranges:
  - **Last 15 minutes**: Real-time monitoring
  - **Last 24 hours**: Daily overview
  - **Last 7 days**: Weekly trends
  - **Last 30 days**: Monthly analysis

### Step 3: Auto-Refresh (Optional)

- Click the time picker
- Click **Auto-refresh**
- Select interval: **10 seconds**, **30 seconds**, **1 minute**, etc.
- This keeps the dashboard live-updating

---

## Using Dev Tools (Advanced)

### Access Dev Tools

- Hamburger menu → **Dev Tools**

### Example Queries

```json
# Get all events from CAM1
GET /alpr-events-*/_search
{
  "query": {
    "match": {
      "camera_id": "CAM1"
    }
  },
  "size": 10
}

# Aggregation: Top 10 plates
GET /alpr-events-*/_search
{
  "size": 0,
  "aggs": {
    "top_plates": {
      "terms": {
        "field": "plate.normalized_text.keyword",
        "size": 10
      }
    }
  }
}

# Count events per hour
GET /alpr-events-*/_search
{
  "size": 0,
  "aggs": {
    "events_per_hour": {
      "date_histogram": {
        "field": "captured_at",
        "calendar_interval": "hour"
      }
    }
  }
}

# High-confidence reads only
GET /alpr-events-*/_search
{
  "query": {
    "range": {
      "plate.confidence": {
        "gte": 0.9
      }
    }
  }
}

# Complex query: High-confidence trucks from CAM1
GET /alpr-events-*/_search
{
  "query": {
    "bool": {
      "must": [
        { "match": { "camera_id": "CAM1" } },
        { "match": { "vehicle.type": "truck" } },
        { "range": { "plate.confidence": { "gte": 0.8 } } }
      ]
    }
  }
}
```

---

## Troubleshooting

### No data showing in Discover

**Check 1: Time range**
- Expand time range to **Last 30 days** or **Last year**
- Your test data might be older than the default 15-minute window

**Check 2: Index pattern**
- Go to **Management** → **Index Patterns**
- Verify `alpr-events-*` exists and has the correct time field (`captured_at`)
- Click **Refresh field list** (⟳ icon)

**Check 3: OpenSearch has data**
```bash
# Check indices
curl http://localhost:9200/_cat/indices?v | grep alpr-events

# Check document count
curl http://localhost:9200/alpr-events-*/_count

# Sample a document
curl http://localhost:9200/alpr-events-*/_search?size=1 | python3 -m json.tool
```

### Index pattern not updating

**Solution**: Refresh field list
- Go to **Management** → **Index Patterns**
- Click **alpr-events-***
- Click **Refresh field list** (⟳ icon, top-right)
- This updates the field mappings

### OpenSearch Dashboards not starting

**Check docker-compose profile**:
```bash
# OpenSearch Dashboards uses the 'analytics' profile
docker compose --profile analytics up -d opensearch-dashboards

# Or check if it's running
docker ps | grep opensearch-dashboards
```

**Check logs**:
```bash
docker logs alpr-opensearch-dashboards
```

### Visualizations not showing data

**Check**:
1. Index pattern is correct (`alpr-events-*`)
2. Time range includes your data
3. Field names are exact (use autocomplete)
4. Data exists in OpenSearch (use Dev Tools)

---

## Recommended Dashboard Layout

### ALPR System Overview Dashboard

**Row 1** (Full width):
- Events Over Time (Line chart) - Shows activity trends

**Row 2** (2 columns):
- Top 10 Plates (Bar chart) - Most frequently seen plates
- Events by Camera (Pie chart) - Camera distribution

**Row 3** (2 columns):
- Average OCR Confidence by Camera (Bar chart) - Quality metrics
- Vehicle Type Distribution (Pie chart) - Vehicle mix

**Row 4** (Full width):
- Recent Events (Data table) - Latest 20 events with key fields

---

## Data Retention

**Current Setup**:
- OpenSearch indices are created monthly: `alpr-events-2026.01`, `alpr-events-2026.02`, etc.
- No automatic deletion (all data retained)

**To set up retention** (future):
- Use OpenSearch ISM (Index State Management) policies
- Example: Delete indices older than 90 days

---

## Performance Tips

1. **Use time filters**: Always filter by time range to reduce query load
2. **Limit size**: Use `size: 10` or `size: 100` instead of fetching all documents
3. **Use aggregations**: For analytics, use aggregations instead of fetching all docs
4. **Index specific fields**: When searching, specify fields (e.g., `plate.text` instead of `_all`)
5. **Avoid wildcards**: `ABC*` is slower than exact match `ABC123`

---

## Related Documentation

- [Query API Search Endpoints](../alpr/query-api-guide.md)
- [OpenSearch Integration](../alpr/opensearch-integration.md)
- [Incremental Startup Guide](incremental-startup.md)

---

## Quick Reference

**Access**:
- OpenSearch Dashboards: http://localhost:5601
- OpenSearch API: http://localhost:9200
- Query API (REST): http://localhost:8000/docs

**Key Commands**:
```bash
# Check OpenSearch health
curl http://localhost:9200/_cluster/health?pretty

# List indices
curl http://localhost:9200/_cat/indices?v

# Count documents
curl http://localhost:9200/alpr-events-*/_count

# Start OpenSearch Dashboards
docker compose --profile analytics up -d opensearch-dashboards

# View logs
docker logs -f alpr-opensearch-dashboards
```

**Index Pattern**: `alpr-events-*`
**Time Field**: `captured_at`
**Auto-refresh**: 10s - 1m for real-time monitoring
