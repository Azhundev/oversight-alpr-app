# Metabase Setup Guide - Advanced BI for ALPR

**Purpose**: Set up Metabase for advanced business intelligence, analytics, and reporting on ALPR data.

---

## Overview

**Metabase** is an open-source business intelligence tool that makes it easy to:
- Create interactive dashboards without SQL knowledge
- Build custom SQL queries and reports
- Share insights with stakeholders
- Schedule automated reports
- Drill down into data with filters

**Why Metabase for ALPR?**
- ✅ User-friendly drag-and-drop interface
- ✅ Connects to TimescaleDB (PostgreSQL) natively
- ✅ Lightweight (only ~512MB RAM)
- ✅ Great for executive dashboards and reports
- ✅ Complements Grafana (real-time metrics) and OpenSearch Dashboards (search)

---

## Initial Setup

### Step 1: Access Metabase

**URL**: http://localhost:3001

On first access, you'll see the **Welcome to Metabase** screen.

### Step 2: Create Admin Account

1. **What's your preferred language?**: Select **English**
2. Click **Let's get started**

3. **What should we call you?**
   - First name: **Admin** (or your name)
   - Last name: **User**
   - Email: **admin@alpr.local** (or your email)
   - Company: **ALPR Project**
   - Password: **Create a strong password** (save this!)

4. Click **Next**

### Step 3: Add Your Data (TimescaleDB Connection)

This is where you'll connect Metabase to your ALPR database.

1. **Database type**: Select **PostgreSQL**

2. **Display name**: `ALPR Database`

3. **Connection settings**:
   - **Host**: `timescaledb`
   - **Port**: `5432`
   - **Database name**: `alpr_db`
   - **Username**: `alpr`
   - **Password**: `alpr_secure_pass`

4. **Advanced options** (expand):
   - **Use a secure connection (SSL)**: Leave unchecked (local deployment)
   - **Tunnel**: None

5. Click **Next**

6. **Usage data preference**:
   - Select your preference (I recommend unchecking "Allow Metabase to collect anonymous usage data")
   - Click **Next**

7. **Skip** the "Take me to Metabase" tour (or complete it if you're new to Metabase)

8. Click **Take me to Metabase**

✅ **Success!** You're now in the Metabase home screen.

---

## Understanding the Data Structure

Before creating dashboards, let's understand the ALPR database schema:

### Key Tables

| Table | Description | Key Columns |
|-------|-------------|-------------|
| `plate_reads` | Main ALPR events | event_id, plate_text, normalized_text, confidence, captured_at, camera_id, track_id |
| `cameras` | Camera metadata | camera_id, camera_name, location, status |
| `vehicles` (optional) | Vehicle metadata | vehicle_id, vehicle_type, color, make, model |

### Sample Data Exploration

1. **Click** "Browse Data" (top-right)
2. **Select** "ALPR Database"
3. **Click** "plate_reads" table
4. You'll see a preview of your ALPR events

**Key Fields**:
- `captured_at`: Timestamp of detection (use for time-based analysis)
- `plate_text`: Raw OCR result
- `normalized_text`: Cleaned plate number (use for searches/grouping)
- `confidence`: OCR confidence score (0.0-1.0)
- `camera_id`: Camera identifier
- `track_id`: Vehicle tracking ID
- `vehicle_type`: Type of vehicle (car, truck, etc.)
- `plate_image_url`: S3 URL to plate crop image

---

## Creating Your First Dashboard

### Dashboard 1: Executive Overview

This dashboard provides a high-level view of ALPR system activity.

#### Step 1: Create Dashboard

1. Click **New** (top-right) → **Dashboard**
2. **Name**: `ALPR Executive Overview`
3. **Description**: `High-level ALPR system metrics and trends`
4. Click **Create**

#### Step 2: Add Questions (Widgets)

Now we'll add several cards to this dashboard.

---

### Question 1: Total Plate Reads (Today)

1. **Click** "+"  (Add a question)
2. **Choose**: "Native query" (we'll write SQL)
3. **Select database**: ALPR Database
4. **SQL Query**:
```sql
SELECT COUNT(*) as total_reads
FROM plate_reads
WHERE captured_at >= CURRENT_DATE;
```
5. **Click** "▶ Run"
6. **Visualization**: Should automatically show as a Number
7. **Click** "Save" → Name: `Total Reads Today` → Save
8. **Add to dashboard**: Select "ALPR Executive Overview"

---

### Question 2: Reads Over Time (Last 24 Hours)

1. **New Question** → **Native query**
2. **SQL**:
```sql
SELECT
  DATE_TRUNC('hour', captured_at) as hour,
  COUNT(*) as reads
FROM plate_reads
WHERE captured_at >= NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour;
```
3. **Run** → **Visualization** → Select "Line chart"
4. **Settings**:
   - X-axis: `hour`
   - Y-axis: `reads`
5. **Save**: `Hourly Reads (24h)` → Add to dashboard

---

### Question 3: Top 10 Plates (Last 7 Days)

1. **New Question** → **Native query**
2. **SQL**:
```sql
SELECT
  normalized_text as plate,
  COUNT(*) as occurrences,
  AVG(confidence)::NUMERIC(4,2) as avg_confidence
FROM plate_reads
WHERE captured_at >= NOW() - INTERVAL '7 days'
GROUP BY normalized_text
ORDER BY occurrences DESC
LIMIT 10;
```
3. **Run** → **Visualization** → Select "Bar chart"
4. **Settings**:
   - X-axis: `plate`
   - Y-axis: `occurrences`
5. **Save**: `Top 10 Plates (7d)` → Add to dashboard

---

### Question 4: Reads by Camera (Today)

1. **New Question** → **Native query**
2. **SQL**:
```sql
SELECT
  camera_id,
  COUNT(*) as reads
FROM plate_reads
WHERE captured_at >= CURRENT_DATE
GROUP BY camera_id
ORDER BY reads DESC;
```
3. **Run** → **Visualization** → Select "Pie chart"
4. **Settings**:
   - Dimension: `camera_id`
   - Metric: `reads`
5. **Save**: `Reads by Camera (Today)` → Add to dashboard

---

### Question 5: Average OCR Confidence (Last 24h)

1. **New Question** → **Native query**
2. **SQL**:
```sql
SELECT
  AVG(confidence)::NUMERIC(4,2) * 100 as avg_confidence_percent
FROM plate_reads
WHERE captured_at >= NOW() - INTERVAL '24 hours';
```
3. **Run** → **Visualization** → Number
4. **Formatting**:
   - Add suffix: `%`
5. **Save**: `Avg OCR Confidence (24h)` → Add to dashboard

---

### Question 6: Reads by Vehicle Type (Last 7 Days)

1. **New Question** → **Native query**
2. **SQL**:
```sql
SELECT
  COALESCE(vehicle_type, 'unknown') as type,
  COUNT(*) as count
FROM plate_reads
WHERE captured_at >= NOW() - INTERVAL '7 days'
GROUP BY vehicle_type
ORDER BY count DESC;
```
3. **Run** → **Visualization** → Pie chart
4. **Save**: `Vehicle Types (7d)` → Add to dashboard

---

### Step 3: Arrange Dashboard

1. **Edit** dashboard (top-right pencil icon)
2. **Drag and resize** cards to your preference

**Suggested layout**:
```
Row 1: [Total Reads Today] [Avg OCR Confidence]
Row 2: [Hourly Reads (24h) - Full width]
Row 3: [Top 10 Plates] [Reads by Camera]
Row 4: [Vehicle Types (7d)]
```

3. **Save** dashboard
4. **Set auto-refresh** (optional): Click ⚙️ → Auto-refresh → 5 minutes

✅ **Done!** You now have a live executive dashboard.

---

## Creating More Advanced Dashboards

### Dashboard 2: Camera Performance Analysis

**Purpose**: Compare camera performance and identify issues.

**Questions to add**:

1. **Reads per Camera per Hour**:
```sql
SELECT
  camera_id,
  DATE_TRUNC('hour', captured_at) as hour,
  COUNT(*) as reads
FROM plate_reads
WHERE captured_at >= NOW() - INTERVAL '24 hours'
GROUP BY camera_id, hour
ORDER BY hour, camera_id;
```
Visualization: Line chart (multi-series)

2. **Average Confidence by Camera**:
```sql
SELECT
  camera_id,
  AVG(confidence)::NUMERIC(4,2) * 100 as avg_confidence,
  COUNT(*) as total_reads
FROM plate_reads
WHERE captured_at >= NOW() - INTERVAL '7 days'
GROUP BY camera_id
ORDER BY avg_confidence DESC;
```
Visualization: Bar chart

3. **Low Confidence Reads by Camera** (< 80%):
```sql
SELECT
  camera_id,
  COUNT(*) as low_confidence_reads,
  (COUNT(*) * 100.0 / (SELECT COUNT(*) FROM plate_reads WHERE camera_id = pr.camera_id))::NUMERIC(4,2) as percentage
FROM plate_reads pr
WHERE confidence < 0.80
  AND captured_at >= NOW() - INTERVAL '7 days'
GROUP BY camera_id
ORDER BY low_confidence_reads DESC;
```
Visualization: Table

---

### Dashboard 3: Plate Recognition Quality Report

**Purpose**: Monitor OCR quality and identify areas for model improvement.

**Questions to add**:

1. **Confidence Distribution**:
```sql
SELECT
  CASE
    WHEN confidence >= 0.95 THEN '95-100%'
    WHEN confidence >= 0.90 THEN '90-95%'
    WHEN confidence >= 0.80 THEN '80-90%'
    WHEN confidence >= 0.70 THEN '70-80%'
    ELSE '< 70%'
  END as confidence_range,
  COUNT(*) as count
FROM plate_reads
WHERE captured_at >= NOW() - INTERVAL '7 days'
GROUP BY confidence_range
ORDER BY confidence_range DESC;
```
Visualization: Bar chart

2. **Daily OCR Quality Trend**:
```sql
SELECT
  DATE_TRUNC('day', captured_at) as day,
  AVG(confidence)::NUMERIC(4,2) * 100 as avg_confidence,
  MIN(confidence)::NUMERIC(4,2) * 100 as min_confidence,
  MAX(confidence)::NUMERIC(4,2) * 100 as max_confidence
FROM plate_reads
WHERE captured_at >= NOW() - INTERVAL '30 days'
GROUP BY day
ORDER BY day;
```
Visualization: Line chart (multi-metric)

---

### Dashboard 4: Time-based Analytics

**Purpose**: Understand traffic patterns and peak hours.

**Questions to add**:

1. **Reads by Hour of Day (Last 7 Days)**:
```sql
SELECT
  EXTRACT(HOUR FROM captured_at) as hour_of_day,
  COUNT(*) as total_reads
FROM plate_reads
WHERE captured_at >= NOW() - INTERVAL '7 days'
GROUP BY hour_of_day
ORDER BY hour_of_day;
```
Visualization: Bar chart

2. **Reads by Day of Week**:
```sql
SELECT
  TO_CHAR(captured_at, 'Day') as day_of_week,
  EXTRACT(DOW FROM captured_at) as dow_num,
  COUNT(*) as total_reads
FROM plate_reads
WHERE captured_at >= NOW() - INTERVAL '30 days'
GROUP BY day_of_week, dow_num
ORDER BY dow_num;
```
Visualization: Bar chart

3. **Busiest Hours**:
```sql
SELECT
  camera_id,
  EXTRACT(HOUR FROM captured_at) as hour,
  COUNT(*) as reads
FROM plate_reads
WHERE captured_at >= NOW() - INTERVAL '7 days'
GROUP BY camera_id, hour
ORDER BY reads DESC
LIMIT 20;
```
Visualization: Table

---

## Using Filters on Dashboards

### Adding Date Range Filter

1. **Edit dashboard**
2. **Click** "Add a filter"
3. **Select** "Time" → "All Options"
4. **Name**: `Date Range`
5. **Save**

6. **Connect filter to questions**:
   - Click on each question's filter icon
   - Map filter to `captured_at` column
   - Save

Now users can change the date range for all questions at once!

### Adding Camera Filter

1. **Add filter** → **Text or Category** → **Dropdown**
2. **Name**: `Camera`
3. **Values source**: From connected database column
4. **Connect to questions** → Map to `camera_id`

---

## Sharing Dashboards

### Option 1: Public Link (Read-only)

1. **Open dashboard**
2. **Click** 🔗 (share icon, top-right)
3. **Enable sharing** → Copy link
4. **Share** link with stakeholders (no login required)

**Note**: Anyone with the link can view the dashboard!

### Option 2: Create Additional Users

1. **Settings** (⚙️ icon, top-right) → **Admin** → **People**
2. **Invite someone**
3. **Email**: Enter email address
4. **Groups**: Select permissions (e.g., "Analysts" for read-only)
5. **Send invitation**

---

## Scheduled Reports (Email Delivery)

### Set Up Email Delivery

1. **Open dashboard**
2. **Click** 📧 (subscriptions, top-right)
3. **Set up a dashboard subscription**
4. **Configure**:
   - **Frequency**: Daily, Weekly, or Monthly
   - **Time**: Choose delivery time
   - **Recipients**: Add email addresses
   - **Attach results**: PDF or PNG
5. **Create subscription**

**Example**: Daily executive summary at 8:00 AM

---

## Advanced Features

### Custom SQL Questions

For complex queries, use "Native query":

**Example: Repeat Visitors (Seen 3+ times in 7 days)**:
```sql
SELECT
  normalized_text as plate,
  COUNT(*) as visit_count,
  MIN(captured_at) as first_seen,
  MAX(captured_at) as last_seen,
  COUNT(DISTINCT camera_id) as unique_cameras
FROM plate_reads
WHERE captured_at >= NOW() - INTERVAL '7 days'
GROUP BY normalized_text
HAVING COUNT(*) >= 3
ORDER BY visit_count DESC;
```

### Parameterized Queries

Add variables to SQL queries:

```sql
SELECT *
FROM plate_reads
WHERE normalized_text = {{plate_number}}
  AND captured_at >= {{start_date}}
  AND captured_at <= {{end_date}};
```

Users can input parameters when running the query!

---

## Performance Tips

### 1. Use Indexes

Ensure these indexes exist in TimescaleDB:

```sql
-- Check existing indexes
SELECT indexname FROM pg_indexes WHERE tablename = 'plate_reads';

-- Recommended indexes (if missing)
CREATE INDEX idx_plate_reads_captured_at ON plate_reads(captured_at DESC);
CREATE INDEX idx_plate_reads_camera_id ON plate_reads(camera_id);
CREATE INDEX idx_plate_reads_normalized_text ON plate_reads(normalized_text);
```

### 2. Limit Date Ranges

Always include a date filter in queries:
```sql
WHERE captured_at >= NOW() - INTERVAL '7 days'
```

### 3. Use Caching

Metabase automatically caches query results. Configure in:
- **Settings** → **Admin** → **Caching**
- Set cache TTL (e.g., 5 minutes for dashboards)

### 4. Optimize Slow Queries

- Use `EXPLAIN ANALYZE` to identify bottlenecks
- Avoid `SELECT *` in production queries
- Use aggregations instead of fetching all rows

---

## Troubleshooting

### Connection Failed to TimescaleDB

**Error**: "Failed to connect to database"

**Solutions**:
1. Verify TimescaleDB is running: `docker ps | grep timescaledb`
2. Check credentials in Metabase match docker-compose.yml
3. Ensure Metabase can reach `timescaledb` container (same Docker network)

**Test connection**:
```bash
docker exec alpr-metabase curl timescaledb:5432
```

### Dashboard Loading Slowly

**Solutions**:
1. Add date filters to limit data scanned
2. Check query performance in TimescaleDB
3. Increase Metabase memory: Edit docker-compose.yml:
   ```yaml
   JAVA_OPTS: -Xmx1024m  # Increase from 512m to 1024m
   ```
4. Restart Metabase: `docker restart alpr-metabase`

### Forgot Admin Password

**Reset**:
```bash
# Enter Metabase container
docker exec -it alpr-metabase bash

# Reset admin password (inside container)
java -jar metabase.jar reset-password admin@alpr.local

# Exit container
exit
```

### Questions Not Showing Recent Data

**Solution**: Clear cache
- **Settings** → **Admin** → **Caching**
- **Clear cache**

Or refresh specific question:
- Open question → Click ⚙️ → **Refresh**

---

## Best Practices

### 1. Organize with Collections

Create collections to organize dashboards:
- **Executive Dashboards**
- **Operational Reports**
- **Camera Performance**
- **Quality Analysis**

### 2. Use Consistent Naming

- Prefix dashboards: `[ALPR]` or `[PROD]`
- Include date range in names: `Daily Report (Last 24h)`
- Use clear descriptions

### 3. Document Your Queries

Add comments to SQL queries:
```sql
-- Get top 10 most frequent plates in last 7 days
-- Used for identifying regular visitors or potential watchlist candidates
SELECT normalized_text, COUNT(*) as visits
FROM plate_reads
WHERE captured_at >= NOW() - INTERVAL '7 days'
GROUP BY normalized_text
ORDER BY visits DESC
LIMIT 10;
```

### 4. Set Up Alerts (Metabase Pro Feature)

For the open-source version, use:
- **Alert Engine** (already deployed) for real-time Kafka-based alerts
- **Grafana** for metric-based alerts
- **Scheduled reports** in Metabase for periodic summaries

---

## Metabase vs Other Tools

| Feature | Metabase | Grafana | OpenSearch Dashboards |
|---------|----------|---------|----------------------|
| **Real-time metrics** | ❌ No | ✅ Yes | ✅ Yes |
| **SQL queries** | ✅ Excellent | ⚠️ Limited | ❌ No |
| **User-friendly** | ✅ Very easy | ⚠️ Moderate | ⚠️ Moderate |
| **Custom reports** | ✅ Yes | ⚠️ Limited | ✅ Yes |
| **Email delivery** | ✅ Yes | ✅ Yes (paid) | ❌ No |
| **Best for** | Business analytics, executive dashboards | Real-time monitoring, DevOps | Full-text search, log analysis |

**Recommendation**: Use all three together!
- **Grafana**: Real-time system health and performance
- **Metabase**: Business analytics and executive reports
- **OpenSearch Dashboards**: Search and log analysis

---

## Sample Dashboards Summary

### 1. Executive Overview
- Total reads (today, week, month)
- Hourly trends
- Top plates
- Camera distribution
- OCR confidence
- Vehicle types

### 2. Camera Performance
- Reads per camera
- Confidence by camera
- Low-quality detections
- Camera uptime/downtime

### 3. Quality Report
- Confidence distribution
- Daily quality trends
- Low-confidence reads analysis
- Model improvement recommendations

### 4. Time-based Analytics
- Peak hours
- Day of week patterns
- Traffic trends
- Seasonal analysis

### 5. Security/Watchlist (Optional)
- Repeat visitors
- Multi-camera crossings
- Unusual patterns
- Watchlist matches (if configured)

---

## Related Documentation

- [Grafana Dashboards Guide](grafana-dashboards.md)
- [OpenSearch Dashboards Setup](opensearch-dashboards-setup.md)
- [Query API Guide](../alpr/query-api-guide.md)
- [TimescaleDB Schema](../alpr/database-schema.md)

---

## Quick Reference

**Access**:
- Metabase UI: http://localhost:3001
- Admin Settings: http://localhost:3001/admin
- Database: timescaledb:5432 / alpr_db

**Key Commands**:
```bash
# Start Metabase
docker compose up -d metabase

# View logs
docker logs -f alpr-metabase

# Restart
docker restart alpr-metabase

# Access container
docker exec -it alpr-metabase bash

# Check health
curl http://localhost:3001/api/health
```

**Database Connection**:
- Type: PostgreSQL
- Host: timescaledb
- Port: 5432
- Database: alpr_db
- User: alpr
- Password: alpr_secure_pass

**Key Tables**:
- `plate_reads`: Main ALPR events
- `cameras`: Camera metadata

---

**Happy analyzing!** 📊
