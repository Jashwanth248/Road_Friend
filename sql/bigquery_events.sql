CREATE TABLE IF NOT EXISTS `PROJECT_ID.roadmate.agent_events` (
  event_id STRING,
  event_ts TIMESTAMP,
  session_id STRING,
  event_type STRING,
  intent STRING,
  tool_name STRING,
  latency_ms FLOAT64,
  success BOOL,
  latitude FLOAT64,
  longitude FLOAT64,
  payload JSON
)
PARTITION BY DATE(event_ts)
CLUSTER BY event_type, intent;
