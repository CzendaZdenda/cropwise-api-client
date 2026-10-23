from datetime import datetime
import logging
from typing import Optional
from pathlib import Path
import geopandas as gpd
from shapely.geometry import LineString
from .client import CropwiseClient

# Set up library-specific logger
logger = logging.getLogger("cropwise")


def build_machine_track_gpkg(
    client: CropwiseClient, 
    machine_id: int, 
    dt_from: datetime, 
    dt_to: datetime, 
    output_gpkg: Path | str, 
    machine_name: Optional[str] = None
) -> bool:
    """
    Fetches raw telemetry points from the Cropwise API across a date range and constructs 
    a continuous vector LineString layer saved directly into a GeoPackage (.gpkg) file for QGIS.
    
    :param client: An instance of CropwiseClient.
    :param machine_id: ID of the machinery.
    :param dt_from: Start datetime of the track period (supports custom shifts).
    :param dt_to: End datetime of the track period (supports custom shifts).
    :param output_gpkg: Path destination (Path object or string) for the final GeoPackage file.
    :param machine_name: Optional machine label metadata to store inside the layer attributes.
    :return: True if the file was generated successfully, False otherwise.
    """
    # Ensure output_gpkg is a Path object for safe manipulation
    output_gpkg = Path(output_gpkg)

    # REFACTORING ADVANTAGE: 
    # Our new client already handles multi-day range queries, token refresh, 
    # chronological sorting, and precise datetime cropping internally!
    df_filtered = client.get_logger_track_data(
        date_from=dt_from,
        date_to=dt_to,
        machine_ids=machine_id
    )

    # In our new client, the DataFrame index becomes 'id_t', so we check length or emptiness
    if df_filtered.empty or len(df_filtered) < 2:
        logger.warning(
            f"Insufficient spatial data ({len(df_filtered)} points) found "
            f"for machine ID {machine_id} within the specified timeframe."
        )
        return False

    # Convert pandas DataFrame to vector GeoDataFrame (WGS 84 / EPSG:4326 standard GPS CRS)
    gdf_points = gpd.GeoDataFrame(
        df_filtered, 
        geometry=gpd.points_from_xy(df_filtered["lon"], df_filtered["lat"]), 
        crs="EPSG:4326"
    )
    
    # Aggregate coordinates into a single LineString vector geometry
    track_line = LineString(gdf_points["geometry"].tolist())

    gdf_line = gpd.GeoDataFrame({
        "machine_id": [machine_id],
        "date_from": [dt_from.isoformat()],
        "date_to": [dt_to.isoformat()],
        "machine_name": [machine_name],
    }, geometry=[track_line], crs="EPSG:4326")

    # The name of the file acts as the default vector layer name inside QGIS
    gdf_line.to_file(output_gpkg, driver="GPKG", layer=output_gpkg.stem)
    logger.info(f"Spatial machinery track successfully generated and saved to: {output_gpkg}")
    return True
