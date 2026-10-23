# Cropwise API Client for Python

[Читать на русском](README.ru.md)

A Python client library wrapper for the **Cropwise Operations (Cropio) API v3** featuring automated pagination, request retries, and optional spatial GIS data processing capabilities.

> ⚠️ **Development Status: Beta**  
> This library is currently in its **Beta stage**. It is fully functional for the implemented endpoints, but the codebase is actively growing. New Cropwise API endpoints will be added in future releases, and minor breaking changes to the interface may occur as the architecture matures.


## ✨ Supported API Endpoints & Features

This library provides direct access to specific Cropwise Operations API v3 endpoints, returning data structured as pandas DataFrames:

- **Core Infrastructure Directories:** 
  - `fields`
  - `machines` & `machine_groups`
  - `implements`
  - `crops` & `work_types`
  - `users`
  - `agro_operations`
  - `machine_tasks`
  - `machine_task_agro_operation_mapping_items` (links between machine tasks and agrooperations)
  - `machine_task_field_mapping_items` (links between machine tasks and fields)
  - `gps_logger_data_items` (raw spatial GPS tracking points)
  - `gps_logger_event_data_items` (machinery sensor telemetry logs, such as fuel levels or engine speeds)
  - `history_items`
  - `inventory_history_items` (audit history and version logs for core assets: Machines, Implements, Fields)

### GIS Export Extension
- Includes an optional `processing` module utilizing `geopandas` and `shapely` to compile multi-day or single-shift telemetry points into continuous `LineString` vector geometries saved directly into standard `GeoPackage (.gpkg)` layers.


## 📦 Installation

To install the core lightweight client for handling structured metadata tables only:

```bash
pip install cropwise-api-client
```

To install the complete geospatial version containing the `processing` module:
*(Note: Windows users are highly recommended to run this package inside an **OSGeo4W Shell** or the integrated **QGIS Python Environment** to prevent spatial binary environment errors).*

```bash
pip install cropwise-api-client[gis]
```

## 🚀 Quick Start

### 1. Initializing the Client (Recommended via Permanent Token)

Generate a permanent token inside your Cropwise Operations profile settings and use it for secure script initialization without exposing raw password strings in the codebase:

```python
from cropwise import CropwiseClient

# Initialize the client using a secure permanent user API token
client = CropwiseClient(token="your_token")

# Fetch all operational fields into a structured pandas DataFrame indexed by ID
df_fields = client.get_fields()
print(df_fields[['id', 'name']])
```

### 2. Exporting Machinery Track to GeoPackage (.gpkg) for QGIS

Seamlessly download raw GPS tracking logs crossing multiple calendar days or overnight work shifts and compile them into a singular vector LineString layer saved straight to disk:

```python
from datetime import datetime
from pathlib import Path
from cropwise import CropwiseClient
from cropwise.processing import build_machine_track_gpkg

client = CropwiseClient(token="your_token")

# Extract telemetry points and write a vector LineString file for GIS mapping
build_machine_track_gpkg(
    client=client,
    machine_id=1299,
    dt_from=datetime(2026, 10, 20, 20, 0, 0),  # Night shift start
    dt_to=datetime(2026, 10, 21, 8, 0, 0),    # Night shift end
    output_gpkg=Path("C:/GIS_Data/tracks/night_shift_1299.gpkg"),
    machine_name="John Deere 8R"
)
```

### 3. Extracting Dynamic Telemetry and Sensor Logs

Extract specific telemetry sensor attributes across multiple machinery assets at once. The library will automatically flatten dynamic nested data attributes into native tabular columns:

```python
from cropwise import CropwiseClient

client = CropwiseClient(token="your_token")

# Fetch precise fuel level and engine speed logs
df_telemetry = client.get_logger_event_data(
    date_at="2026-10-23",
    machine_ids=[101],
    params=["fuel_level", "engine_speed", "pwr_ext"]
)
print(df_telemetry.head())
```

## 📄 License

This library is distributed under the MIT License. See [LICENSE](LICENSE) for more details.
