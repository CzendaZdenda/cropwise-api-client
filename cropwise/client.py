# cropwise/client.py

import json
import logging
from typing import Dict, Any, List, Optional, Union
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import pandas as pd
from .exceptions import CropwiseAuthException, CropwiseApiException

# Set up library-specific logger
logger = logging.getLogger("cropwise")

# Standard Cropwise API response status mapping
RESPONSE_STATUS = {
    400: ('Bad Request', 'The request could not be understood or was missing required parameters.'),
    401: ('Unauthorized', 'Authentication failed or user doesn\'t have permissions for requested operation.'),
    403: ('Forbidden', 'Access denied.'),
    404: ('Not Found', 'Resource was not found.'),
    422: ('Unprocessable Entity', 'The request was well-formed but failed due to semantic errors.'),
    503: ('Service Unavailable', 'Service is temporarily unavailable (e.g. scheduled Platform Maintenance).')
}


class CropwiseClient:
    def __init__(
        self, 
        token: Optional[str] = None, 
        email: Optional[str] = None, 
        password: Optional[str] = None, 
        server_url: str = 'https://operations.cropwise.com/api/v3'
    ):
        """
        Python client wrapper for the Cropwise Operations API v3.
        
        :param token: Permanent User API Token generated in the Cropwise profile (Recommended).
        :param email: User login email (used if token is not provided).
        :param password: User login password (used if token is not provided).
        :param server_url: Base API server URL.
        """
        self.server_url = server_url.rstrip('/')
        self._token = token
        self._email = email
        self._password = password
        
        # Initialize an HTTP session with built-in retry logic
        self.session = requests.Session()
        self._setup_retry_policy()

    def _setup_retry_policy(self):
        """Configures automatic request retries for connection errors and unstable server states."""
        retry_strategy = Retry(
            total=5,                          # Maximum 5 retries before failing
            backoff_factor=1,                 # Wait 1s, 2s, 4s, 8s, 16s between retries
            status_forcelist=[500, 502, 503, 504],  # Specific server error codes to retry
            raise_on_status=False             # Allow manual status check in _check_response
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    @property
    def token(self) -> str:
        """Lazy loader that returns the permanent token or dynamically requests one using credentials."""
        if not self._token:
            if not self._email or not self._password:
                raise CropwiseAuthException(
                    "Authentication error: You must provide either a permanent 'token' "
                    "or a valid 'email' and 'password' combination."
                )
            logger.info("Token not provided. Performing dynamic authentication via credentials...")
            self._token = self._authenticate()
        return self._token

    def _authenticate(self) -> str:
        """Sends a POST request to obtain a temporary session token using email and password."""
        url = f"{self.server_url}/users/sign_in" 
        
        payload = {
            "user_login": {
                "email": self._email,
                "password": self._password
            }
        }
        headers = {'Content-Type': 'application/json'}
        
        try:
            response = self.session.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code != 200:
                raise CropwiseAuthException(f"Authentication failed with status code {response.status_code}.")
            return response.json()['user_api_token']
        except requests.RequestException as e:
            raise CropwiseApiException(f"Network error during authentication process: {e}")

    def _get_headers(self) -> Dict[str, str]:
        """Generates required HTTP headers for authorized API requests."""
        return {
            'Content-Type': 'application/json',
            'X-User-Api-Token': self.token,
            'Accept-Language': 'en'
        }

    def _check_response(self, response: requests.Response):
        """Validates HTTP response codes and throws clear exception messages if an error occurs."""
        if response.status_code in (200, 201, 204):
            return
            
        status_info = RESPONSE_STATUS.get(response.status_code, ('Unknown Error', 'No further details available.'))
        err_msg = f"HTTP {response.status_code} ({status_info[0]}): {status_info[1]}"
        
        try:
            server_errors = response.json().get('errors')
            if server_errors:
                err_msg += f" | Server context: {server_errors}"
        except Exception:
            pass
            
        raise CropwiseApiException(err_msg)

    def _get_page(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Performs a low-level HTTP GET request for a single data page."""
        url = f'{self.server_url}/{endpoint}'
        response = self.session.get(url, headers=self._get_headers(), params=params, timeout=30)
        self._check_response(response)
        return response.json()

    def _get_all_pages(self, endpoint: str, filter_params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Universal pagination engine that automatically iterates through all pages using from_id."""
        all_data = []
        last_id = 0
        
        params = filter_params.copy() if filter_params else {}

        while True:
            params['from_id'] = last_id + 1
            response_json = self._get_page(endpoint, params=params)
            
            page_data = response_json.get('data')
            meta_resp = response_json.get('meta', {}).get('response', {})
            
            if not page_data or meta_resp.get('obtained_records', 0) == 0:
                break
                
            all_data.extend(page_data)
            
            limit = meta_resp.get('limit', 0)
            obtained_records = meta_resp.get('obtained_records', 0)
            last_id = meta_resp.get('last_record_id', last_id)
            
            # If the current page contains fewer items than the limit, we reached the end
            if obtained_records < limit:
                break
                
        return all_data

    def _prepare_filters(self, kwargs: Dict[str, Any]) -> Dict[str, str]:
        """Converts Python data types in kwargs to Cropwise API compatible string filters."""
        filters = {}
        for k, v in kwargs.items():
            if v is not None:
                if hasattr(v, 'strftime'):
                    filters[k] = v.strftime("%Y-%m-%dT%H:%M:%S")
                elif isinstance(v, (list, tuple, set)):
                    filters[k] = ','.join([str(x) for x in v])
                elif isinstance(v, bool):
                    filters[k] = str(v).lower()
                else:
                    filters[k] = str(v)
        return filters

    def _to_dataframe(self, data: List[Dict[str, Any]], filter_params: Dict[str, Any]) -> pd.DataFrame:
        """Converts raw API list data into a standardized and sorted pandas DataFrame."""
        if not data:
            return pd.DataFrame()
            
        df = pd.DataFrame(data)
        
        # If the user didn't specify custom sorting, sort by 'id' (if the column exists)
        if 'sort_by' not in filter_params and 'id' in df.columns:
            return df.sort_values(by='id')
            
        return df

    def _request_and_parse(self, endpoint: str, kwargs: dict) -> pd.DataFrame:
        """Internal helper to process filters, fetch all pages, and return a DataFrame."""
        filters = self._prepare_filters(kwargs)
        data = self._get_all_pages(endpoint, filter_params=filters)
        return self._to_dataframe(data, filters)

    def _send_mutation(self, method: str, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Internal helper to handle POST, PUT, or PATCH mutation requests to the API.
        """
        url = f'{self.server_url}/{endpoint}'
        
        # Cropwise API expects the payload wrapped in a single singular-named root object key, 
        # but to keep the client simple and universal, we expect the user to pass the pre-formatted payload.
        response = self.session.request(
            method=method.upper(),
            url=url,
            headers=self._get_headers(),
            json=data,
            timeout=30
        )
        self._check_response(response)
        return response.json() if response.status_code != 204 else {}

    def get_fields(self, **kwargs) -> pd.DataFrame:
        """
        Fetches all operational fields from the server.
        
        Exact match:
            id, field_group_id, name, additional_info, description, moisture_zone, idempotency_key, 
            external_id, cwp_id, field_type, parent_id, public_registry_key

        Comparison (append _eq, _gt, _gt_eq, _lt or _lt_eq to attribute, e.g. created_at_gt):
            created_at, updated_at

        Sorting (sort_by=<attribute>_<asc|desc>, e.g. sort_by=created_at_desc):
            id, created_at, updated_at
        """
        return self._request_and_parse('fields', kwargs)

    def get_machines(self, **kwargs) -> pd.DataFrame:
        """
        Fetches all registered agricultural machinery.

        Exact match:
            id, name, chassis_serial_number, engine_serial_number, inventory_number, machine_subtype, 
            machine_type, registration_number, year, machine_group_id, default_implement_id, default_driver_id, 
            machinery_model_id, external_id, phone_number, fuel_type_id, machinery_manufacturer_id

        Comparison (append _eq, _gt, _gt_eq, _lt or _lt_eq to attribute, e.g. created_at_gt):
            created_at, updated_at

        Sorting (sort_by=<attribute>_<asc|desc>, e.g. sort_by=created_at_desc):
            id, name, created_at, updated_at
        """
        return self._request_and_parse('machines', kwargs)

    def get_crops(self, hidden: bool = False, **kwargs) -> pd.DataFrame:
        """
        Fetches the agricultural crops.
        
        Exact match:
            id, standard_name, short_name, custom_name, additional_info, description, multi_year, 
            season_type, external_id, base_crop_id, productivity_estimate_crop_name, hidden

        Comparison (append _eq, _gt, _gt_eq, _lt or _lt_eq to attribute, e.g. created_at_gt):
            created_at, updated_at

        Sorting (sort_by=<attribute>_<asc|desc>, e.g. sort_by=created_at_desc):
            id, created_at, updated_at
        """
        # Mix explicit arguments with dynamic kwargs
        kwargs['hidden'] = hidden

        return self._request_and_parse('crops', kwargs)

    def get_work_types(self, **kwargs) -> pd.DataFrame:
        """
        Fetches work types with optional filters.
        
        Exact match:
            id, work_type_group_id, name, agri, application, sowing, harvesting, soil, 
            standard_name, hidden, external_id, disable_first_track_rule_coverage

        Comparison (append _eq, _gt, _gt_eq, _lt or _lt_eq to attribute, e.g. created_at_gt):
            created_at, updated_at

        Sorting (sort_by=<attribute>_<asc|desc>, e.g. sort_by=created_at_desc):
            id, created_at, updated_at
        """
        return self._request_and_parse('work_types', kwargs)

    def get_machine_groups(self, **kwargs) -> pd.DataFrame:
        """
        Fetches machinery groups with optional filters.
        
        Exact match:
            id, name, external_id

        Comparison (append _eq, _gt, _gt_eq, _lt or _lt_eq to attribute, e.g. created_at_gt):
            created_at, updated_at

        Sorting (sort_by=<attribute>_<asc|desc>, e.g. sort_by=created_at_desc):
            id, created_at, updated_at
        """
        return self._request_and_parse('machine_groups', kwargs)

    def get_implements(self, **kwargs) -> pd.DataFrame:
        """
        Fetches attached agricultural implements with optional filters.
        
        Exact match:
            id, implement_type, inventory_number, manufacturer, model, external_id, year, 
            registration_number, chassis_serial_number, virtual

        Comparison (append _eq, _gt, _gt_eq, _lt or _lt_eq to attribute, e.g. created_at_gt):
            created_at, updated_at

        Sorting (sort_by=<attribute>_<asc|desc>, e.g. sort_by=created_at_desc):
            id, created_at, updated_at
        """
        return self._request_and_parse('implements', kwargs)

    def get_users(self, **kwargs) -> pd.DataFrame:
        """
        Fetches company system users with optional filters.
        
        Exact match:
            id, username, email, notification_email, status, external_id, tax_identification_number, 
            individual_insurance_number, create_scout_report_outside_of_field

        Comparison (append _eq, _gt, _gt_eq, _lt or _lt_eq to attribute, e.g. created_at_gt):
            created_at, updated_at

        Sorting (sort_by=<attribute>_<asc|desc>, e.g. sort_by=created_at_desc):
            id, created_at, updated_at
        """
        return self._request_and_parse('users', kwargs)

    def get_history_items(self, **kwargs) -> pd.DataFrame:
        """
        Fetches crop rotation and historical land use records with optional filters.
        
        Exact match:
            id, field_id, active, crop_id, variety, till_type, productivity, sowing_date, harvesting_date, 
            description, additional_info, external_id, harvested_weight, yield_density, age_of_sugar_cane, 
            productivity_zone, grain_class, grain_humidity, grain_garbage_admixture, production_cycle_id, 
            field_shape_id, marketable_weight
        
        Comparison (append _eq, _gt, _gt_eq, _lt or _lt_eq to attribute, e.g. sowing_date_gt):
            sowing_date, harvesting_date, created_at, updated_at
        
        Sorting (sort_by=<attribute>_<asc|desc>, e.g. sort_by=created_at_desc):
            id, created_at, updated_at
        """
        return self._request_and_parse('history_items', kwargs)

    def get_machine_tasks(self, **kwargs) -> pd.DataFrame:
        """
        Fetches specific machinery field work tasks with optional filters.
        
        Exact match (query params):
            id, machine_id, driver_id, implement_id, season, work_type_id, status, external_id, 
            locked_to_edit, total_distance, work_distance, covered_area, work_area
        
        Comparison (append _eq, _gt, _gt_eq, _lt or _lt_eq to attribute, e.g. season_gt):
            season, total_distance, work_distance, covered_area, work_area, start_time, end_time, 
            created_at, updated_at, locked_at
        
        Sorting (sort_by=<attribute>_<asc|desc>, e.g. sort_by=created_at_desc):
            id, created_at, updated_at
        """
        return self._request_and_parse('machine_tasks', kwargs)

    def get_agro_operations(self, **kwargs) -> pd.DataFrame:
        """
        Fetches agricultural operations (agrooperations) with optional filters.
        
        :param kwargs: Filters supported by Cropwise API (e.g., field_ids, crop_ids, date_start, date_end).

        Exact match (query params):
            id, field_id, status, season, work_type_id, field_shape_id, locked_to_edit, 
            external_id, agri_work_plan_id, calc_by, applications_type, history_item_id, 
            from_warehouse_id, covered_area_by_track, machine_work_area, planned_area, 
            completed_area, application_by_days, closure_reason_id

        Comparison (append _eq, _gt, _gt_eq, _lt or _lt_eq to attribute, e.g. season_gt):
            season, covered_area_by_track, machine_work_area, planned_area, completed_area, 
            planned_start_date, planned_end_date, created_at, updated_at, actual_start_datetime, 
            completed_datetime, locked_at

        Sorting (sort_by=<attribute>_<asc|desc>, e.g. sort_by=created_at_desc):
            id, created_at, updated_at
        """
        return self._request_and_parse('agro_operations', kwargs)

    def get_machine_task_field_mapping_items(self, **kwargs) -> pd.DataFrame:
        """
        Fetches mapping links between machinery tasks and specific fields.
        
        Exact match (query params):
            id, field_id, machine_task_id, history_item_id, covered_area, work_area
        
        Comparison (append _eq, _gt, _gt_eq, _lt or _lt_eq to attribute, e.g. created_at_gt):
            covered_area, work_area, created_at, updated_at
        
        Sorting (sort_by=<attribute>_<asc|desc>, e.g. sort_by=created_at_desc):
            id, created_at, updated_at
        """
        return self._request_and_parse('machine_task_field_mapping_items', kwargs)

    def get_machine_task_agro_operation_mapping_items(self, **kwargs) -> pd.DataFrame:
        """
        Fetches mapping links between machinery tasks and agrooperations.
        
        Exact match (query params):
            id, machine_task_id, agro_operation_id
        
        Comparison (append _eq, _gt, _gt_eq, _lt or _lt_eq to attribute, e.g. created_at_gt):
            created_at, updated_at
        
        Sorting (sort_by=<attribute>_<asc|desc>, e.g. sort_by=created_at_desc):
            id, created_at, updated_at
        """
        return self._request_and_parse('machine_task_agro_operation_mapping_items', kwargs)

    def get_inventory_history_items(self, **kwargs) -> pd.DataFrame:
        """
        Fetches the audit history and version logs for core assets (Machines, Implements, Fields).
        
        This endpoint tracks lifecycle changes, updates, and versions of corporate inventory objects 
        to help understand which record state is currently active or what changed in the past.

        Exact match (query params): 
            id, historyable_id, historyable_type, reason, description, available, hidden, external_id

        Comparison (append _eq, _gt, _gt_eq, _lt or _lt_eq to attribute, e.g. created_at_gt):
            created_at, updated_at

        Sorting (sort_by=<attribute>_<asc|desc>, e.g. sort_by=created_at_desc):
            id, created_at, updated_at
        """
        return self._request_and_parse('inventory_history_items', kwargs)

    def get_logger_event_data(
        self, 
        date_at: Optional[Any] = None, 
        from_time: Optional[Any] = None, 
        to_time: Optional[Any] = None, 
        machine_ids: Optional[Union[int, str, List[Union[int, str]]]] = None, 
        params: Optional[List[str]] = None, 
        **kwargs
    ) -> pd.DataFrame:
        """
        Fetches telemetry logger event data items (sensors, fuel levels, ignition status).
        
        You must provide EITHER 'date_at' OR BOTH 'from_time' and 'to_time'.
        
        :param date_at: Target date (string "YYYY-MM-DD" or datetime/date object).
        :param from_time: Start time of the interval (string ISO 8601 or datetime object).
        :param to_time: End time of the interval (string ISO 8601 or datetime object).
        :param machine_ids: Optional. Single ID (int/str) or a list/tuple/set of machine IDs.
        :param params: Optional. List of specific sensor telemetry keys to extract.
        """
        # Validate that either date_at or the time interval is provided
        if not date_at and (not from_time or not to_time):
            raise ValueError(
                "Missing required parameters: You must provide either 'date_at' "
                "or both 'from_time' and 'to_time' to specify the time range."
            )
            
        # Process and format time arguments into kwargs
        if date_at is not None:
            kwargs['date_at'] = date_at.strftime("%Y-%m-%d") if hasattr(date_at, 'strftime') else date_at
        if from_time is not None:
            kwargs['from_time'] = from_time.strftime("%Y-%m-%dT%H:%M:%S") if hasattr(from_time, 'strftime') else from_time
        if to_time is not None:
            kwargs['to_time'] = to_time.strftime("%Y-%m-%dT%H:%M:%S") if hasattr(to_time, 'strftime') else to_time
            
        if machine_ids is not None:
            kwargs['machine_ids'] = machine_ids
            
        filters = self._prepare_filters(kwargs)
        raw_data = self._get_all_pages('gps_logger_event_data_items', filter_params=filters)
        
        if not raw_data:
            return pd.DataFrame()
            
        # Flattening dynamic telemetry sensor attributes into columns
        flat_data = []
        for row in raw_data:
            item_id = row.get('id')
            inner_data = row.get('data', {})
            
            record = {
                'id_e': item_id, 
                'time': pd.to_datetime(inner_data.get('time'), unit='s') if inner_data.get('time') else None
            }
            
            if params:
                for p in params:
                    record[p] = inner_data.get(p)
            else:
                for k, v in inner_data.items():
                    if k != 'time':
                        record[k] = v
                        
            flat_data.append(record)
            
        df = pd.DataFrame(flat_data)
        if not df.empty and 'id_e' in df.columns:
            df = df.set_index('id_e')
            if 'time' in df.columns:
                df = df.sort_values(by='time')
        return df

    def get_logger_track_data(
        self, 
        date_at: Optional[Any] = None, 
        date_from: Optional[Any] = None, 
        date_to: Optional[Any] = None, 
        machine_ids: Optional[Union[int, str, List[Union[int, str]]]] = None, 
        **kwargs
    ) -> pd.DataFrame:
        """
        Fetches raw spatial GPS tracking points for machinery.
        
        You must provide EITHER 'date_at' OR BOTH 'date_from' and 'date_to'.
        Supports precise datetime ranges (e.g., for night shifts crossing midnight).
        
        :param date_at: Target date for a single day query (string "YYYY-MM-DD" or datetime/date object).
        :param date_from: Start datetime for a precise range query (string ISO 8601 or datetime object).
        :param date_to: End datetime for a precise range query (string ISO 8601 or datetime object).
        :param machine_ids: Optional. Single ID (int/str) or a list/tuple/set of machine IDs.
        """
        if not date_at and (not date_from or not date_to):
            raise ValueError(
                "Missing required parameters: You must provide either 'date_at' "
                "or both 'date_from' and 'date_to' to specify the time range."
            )

        if machine_ids is not None:
            kwargs['machine_ids'] = machine_ids

        # Scenario 1: Precise datetime range query (Handles shifts like 20:00 to 08:00)
        if date_from and date_to:
            # Keep full datetime precision for later filtering
            ts_from = pd.to_datetime(date_from)
            ts_to = pd.to_datetime(date_to)
            
            if ts_from > ts_to:
                raise ValueError("'date_from' cannot be later than 'date_to'.")
                
            logger.info(f"Fetching precise GPS tracks interval from {ts_from} to {ts_to}...")
            
            all_dfs = []
            # Generate calendar days that need to be requested from Cropwise API
            for current_date in pd.date_range(ts_from.date(), ts_to.date()):
                day_str = current_date.strftime("%Y-%m-%d")
                day_kwargs = kwargs.copy()
                day_kwargs['date_at'] = day_str
                
                filters = self._prepare_filters(day_kwargs)
                data = self._get_all_pages('gps_logger_data_items', filter_params=filters)
                day_df = self._to_dataframe(data, filters)
                
                if not day_df.empty:
                    all_dfs.append(day_df)
                    
            if not all_dfs:
                return pd.DataFrame()
                
            df = pd.concat(all_dfs)
            
            # Temporary standardizations needed before filtering by time
            if 'time' in df.columns:
                df['local_time'] = pd.to_datetime(df['time']).dt.tz_localize(None)
                # CRITICAL STEP: Crop precise shift boundaries inside Python
                df = df[(df['local_time'] >= ts_from) & (df['local_time'] <= ts_to)]

        # Scenario 2: Single calendar day query (Standard mode)
        else:
            kwargs['date_at'] = date_at.strftime("%Y-%m-%d") if hasattr(date_at, 'strftime') else date_at
            filters = self._prepare_filters(kwargs)
            data = self._get_all_pages('gps_logger_data_items', filter_params=filters)
            df = self._to_dataframe(data, filters)
            if not df.empty and 'time' in df.columns:
                df['local_time'] = pd.to_datetime(df['time']).dt.tz_localize(None)

        # Final Post-processing and GIS optimization
        if not df.empty:
            if 'long' in df.columns:
                df = df.rename(columns={'long': 'lon'})
            if 'id' in df.columns:
                df = df.rename(columns={'id': 'id_t'}).set_index('id_t')
            if 'time' in df.columns:
                df = df.sort_values(by='time')
                
        return df

    def create_object(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Creates a new object (e.g., machine_tasks, machine_task_field_mapping_items) on the server.
        
        :param endpoint: The API collection name (e.g., 'machine_tasks').
        :param data: Dictionary containing object attributes.
        :return: Server response as a dictionary.
        """
        # As per Cropwise API v3 docs, the payload must be wrapped in a "data" root key
        payload = {"data": data}
        
        return self._send_mutation('POST', endpoint, payload)

    def update_object(self, endpoint: str, object_id: Union[int, str], data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates an existing object using PUT semantics.
        
        :param endpoint: The API collection name (e.g., 'machine_tasks').
        :param object_id: Unique identifier of the resource.
        :param data: Dictionary containing updated object attributes.
        :return: Server response as a dictionary.
        """
        # Standardizing payload structure with "data" root key for mutations
        payload = {"data": data}
        
        full_endpoint = f"{endpoint}/{object_id}"
        return self._send_mutation('PUT', full_endpoint, payload)