#!/usr/bin/env python3
"""LibCal Space Booking Capacity Analysis Script.

This script analyzes booking data from Springshare's LibCal API to assess
usage rates of bookable studio and maker spaces. It calculates usage
percentages over various time periods and identifies next available booking
slots for each space.

Note: The LibCal Hours API has a maximum limit of 100 days per request.
The default analysis window is set to 13 weeks (~90 days) to stay within
this limit.

Usage:
    python space_capacity_analysis.py [OPTIONS]

Options:
    --input CSV_FILE    Input CSV file with space data
                        (default: spaces_to_analyze.csv)
    --output CSV_FILE   Output CSV file for results
                        (default: space_booking_analysis.csv)
    --window WEEKS      Analysis window in weeks (default: 16)
    --duration HOURS    Booking slot duration in hours (default: 3.0)
"""

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

import requests
import pytz


# Configuration constants
API_BASE_URL = "https://yorku.libcal.com/api/1.1"
# Read OAuth credentials from environment variables (set by GitHub Actions)
OAUTH_CLIENT_ID = os.environ.get('LIBCAL_CLIENT_ID', '')
OAUTH_CLIENT_SECRET = os.environ.get('LIBCAL_CLIENT_SECRET', '')
TIMEZONE = "America/Toronto"
DEFAULT_INPUT_FILE = "input/spaces_to_analyze.csv"
DEFAULT_OUTPUT_FILE_TEMPLATE = "output/space_booking_analysis_{date}.csv"
DEFAULT_ANALYSIS_WINDOW_WEEKS = 13  # ~90 days (13 weeks * 7 days = 91 days)
DEFAULT_BOOKING_DURATION_HOURS = 3.0
BOOKING_TIME_INCREMENTS = [0, 15, 30, 45]  # Minutes
BOOKING_BUFFER_MINUTES = 15
MAX_HOURS_API_DAYS = 100  # Maximum days supported by Hours API


class LibCalAPIError(Exception):
    """Exception raised for LibCal API errors."""

    pass


class DataValidationError(Exception):
    """Exception raised for data validation errors."""

    pass


def get_oauth_token() -> str:
    """Retrieve OAuth access token from LibCal API.

    Returns:
        str: Access token for API authentication.

    Raises:
        LibCalAPIError: If token retrieval fails.
    """
    if not OAUTH_CLIENT_ID or not OAUTH_CLIENT_SECRET:
        raise LibCalAPIError(
            "OAuth credentials not found. Please set LIBCAL_CLIENT_ID and "
            "LIBCAL_CLIENT_SECRET environment variables."
        )
    
    url = f"{API_BASE_URL}/oauth/token"
    params = {
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
        "grant_type": "client_credentials",
    }

    try:
        response = requests.post(url, data=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data["access_token"]
    except requests.exceptions.RequestException as e:
        raise LibCalAPIError(f"Failed to obtain OAuth token: {e}")
    except (KeyError, ValueError) as e:
        raise LibCalAPIError(f"Invalid token response format: {e}")


def validate_csv_data(row: Dict[str, str], row_num: int) -> None:
    """Validate that a CSV row contains all required fields.

    Args:
        row: Dictionary representing a CSV row.
        row_num: Row number for error reporting.

    Raises:
        DataValidationError: If any required field is missing or empty.
    """
    required_fields = [
        "category_id",
        "category_name",
        "space_id",
        "space_name",
        "location_id",
        "location_name",
    ]

    for field in required_fields:
        if field not in row or not row[field].strip():
            raise DataValidationError(
                f"Row {row_num}: Missing or empty value for '{field}'"
            )


def load_spaces_from_csv(filepath: str) -> List[Dict[str, str]]:
    """Load space configuration from CSV file.

    Args:
        filepath: Path to the CSV file containing space data.

    Returns:
        List of dictionaries, each representing a space with its metadata.

    Raises:
        DataValidationError: If CSV format is invalid or data is missing.
        FileNotFoundError: If the CSV file does not exist.
    """
    spaces = []

    try:
        with open(filepath, "r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)

            if reader.fieldnames is None:
                raise DataValidationError("CSV file is empty or has no header")

            for idx, row in enumerate(reader, start=2):
                validate_csv_data(row, idx)
                spaces.append(row)

        if not spaces:
            raise DataValidationError("No valid space data found in CSV")

        return spaces

    except FileNotFoundError:
        raise FileNotFoundError(f"Input file not found: {filepath}")
    except csv.Error as e:
        raise DataValidationError(f"CSV parsing error: {e}")


def get_location_hours(
    token: str, location_id: str, from_date: str, to_date: str
) -> Dict[str, List[Tuple[datetime, datetime]]]:
    """Retrieve operating hours for a location from LibCal API.

    Args:
        token: OAuth access token.
        location_id: Location ID to query.
        from_date: Start date in YYYY-MM-DD format.
        to_date: End date in YYYY-MM-DD format.

    Returns:
        Dictionary mapping dates (YYYY-MM-DD) to list of (open, close)
        datetime tuples for that date.

    Raises:
        LibCalAPIError: If API request fails.
    """
    url = f"{API_BASE_URL}/hours/{location_id}"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"from": from_date, "to": to_date}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        hours_by_date = {}
        tz = pytz.timezone(TIMEZONE)

        for location in data:
            if "dates" not in location:
                continue

            dates_dict = location["dates"]
            
            for date_str, day_data in dates_dict.items():
                if not day_data or day_data.get("status") != "open":
                    continue

                hours_list = day_data.get("hours", [])
                time_ranges = []

                for hours in hours_list:
                    from_time = hours.get("from")
                    to_time = hours.get("to")

                    if from_time and to_time:
                        from_dt = datetime.strptime(
                            f"{date_str} {from_time}", "%Y-%m-%d %I:%M%p"
                        )
                        to_dt = datetime.strptime(
                            f"{date_str} {to_time}", "%Y-%m-%d %I:%M%p"
                        )

                        from_dt = tz.localize(from_dt)
                        to_dt = tz.localize(to_dt)

                        time_ranges.append((from_dt, to_dt))

                if time_ranges:
                    hours_by_date[date_str] = time_ranges

        return hours_by_date

    except requests.exceptions.RequestException as e:
        raise LibCalAPIError(
            f"Failed to fetch hours for location {location_id}: {e}"
        )
    except (KeyError, ValueError) as e:
        raise LibCalAPIError(
            f"Invalid hours response format for location {location_id}: {e}"
        )


def get_space_bookings(
    token: str, space_id: str, from_date: str, days: int
) -> List[Dict]:
    """Retrieve bookings for a specific space from LibCal API.

    Args:
        token: OAuth access token.
        space_id: Space ID to query.
        from_date: Start date in YYYY-MM-DD format.
        days: Number of days to retrieve bookings for.

    Returns:
        List of booking dictionaries.

    Raises:
        LibCalAPIError: If API request fails.
    """
    url = f"{API_BASE_URL}/space/bookings"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "eid": space_id,
        "date": from_date,
        "days": days,
        "limit": 150,
        "include_tentative": 1,
        "include_cancel": 0,
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        raise LibCalAPIError(
            f"Failed to fetch bookings for space {space_id}: {e}"
        )
    except ValueError as e:
        raise LibCalAPIError(
            f"Invalid bookings response format for space {space_id}: {e}"
        )


def generate_potential_slots(
    hours_data: Dict[str, List[Tuple[datetime, datetime]]],
    duration_hours: float,
) -> List[datetime]:
    """Generate all potential booking slots within operating hours.

    Args:
        hours_data: Dictionary mapping dates to operating hours.
        duration_hours: Duration of booking slots in hours.

    Returns:
        List of potential booking start times.
    """
    slots = []
    duration = timedelta(hours=duration_hours)

    for date_str, time_ranges in sorted(hours_data.items()):
        for open_time, close_time in time_ranges:
            current_time = open_time

            while current_time + duration <= close_time:
                if current_time.minute in BOOKING_TIME_INCREMENTS:
                    slots.append(current_time)

                current_time += timedelta(minutes=15)

    return slots


def calculate_booked_hours(
    bookings: List[Dict], tz: pytz.timezone
) -> List[Tuple[datetime, datetime]]:
    """Extract booked time ranges from booking data.

    Args:
        bookings: List of booking dictionaries from API.
        tz: Timezone for datetime localization.

    Returns:
        List of (start, end) datetime tuples for booked periods.
    """
    booked_ranges = []

    for booking in bookings:
        try:
            from_date = booking.get("fromDate")
            to_date = booking.get("toDate")

            if not from_date or not to_date:
                continue

            from_dt = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
            to_dt = datetime.fromisoformat(to_date.replace("Z", "+00:00"))

            from_dt = from_dt.astimezone(tz)
            to_dt = to_dt.astimezone(tz)

            booked_ranges.append((from_dt, to_dt))

        except (ValueError, AttributeError):
            continue

    return booked_ranges


def is_slot_available(
    slot_start: datetime,
    duration_hours: float,
    booked_ranges: List[Tuple[datetime, datetime]],
) -> bool:
    """Check if a time slot is available for booking.

    Args:
        slot_start: Start time of the potential booking slot.
        duration_hours: Duration of the slot in hours.
        booked_ranges: List of (start, end) tuples for existing bookings.

    Returns:
        True if slot is available, False otherwise.
    """
    buffer = timedelta(minutes=BOOKING_BUFFER_MINUTES)
    slot_end = slot_start + timedelta(hours=duration_hours)

    buffered_start = slot_start - buffer
    buffered_end = slot_end + buffer

    for booked_start, booked_end in booked_ranges:
        if not (buffered_end <= booked_start or buffered_start >= booked_end):
            return False

    return True


def calculate_metrics_for_period(
    potential_slots: List[datetime],
    booked_ranges: List[Tuple[datetime, datetime]],
    duration_hours: float,
    cutoff_date: datetime,
) -> Tuple[float, float, float, int]:
    """Calculate booking metrics for a specific time period.

    Args:
        potential_slots: All potential booking slots in the period.
        booked_ranges: List of booked time ranges.
        duration_hours: Duration of each booking slot.
        cutoff_date: End date for the analysis period.

    Returns:
        Tuple of (booking_rate, available_hours, booked_hours, booking_count).
    """
    slots_in_period = [s for s in potential_slots if s < cutoff_date]

    if not slots_in_period:
        return 0.0, 0.0, 0.0, 0

    available_count = sum(
        1
        for slot in slots_in_period
        if is_slot_available(slot, duration_hours, booked_ranges)
    )

    booked_count = len(slots_in_period) - available_count
    total_slots = len(slots_in_period)

    booking_rate = (booked_count / total_slots * 100) if total_slots > 0 else 0.0
    available_hours = available_count * duration_hours
    booked_hours = booked_count * duration_hours

    bookings_in_period = sum(
        1
        for start, end in booked_ranges
        if start < cutoff_date
    )

    return booking_rate, available_hours, booked_hours, bookings_in_period


def find_next_available_slot(
    potential_slots: List[datetime],
    booked_ranges: List[Tuple[datetime, datetime]],
    duration_hours: float,
    current_time: datetime,
) -> Optional[str]:
    """Find the next available booking slot after the current time.

    Args:
        potential_slots: All potential booking slots.
        booked_ranges: List of booked time ranges.
        duration_hours: Duration of booking slots.
        current_time: Current date/time to search from.

    Returns:
        Formatted string of next available time, or None if no slots available.
    """
    future_slots = [s for s in potential_slots if s >= current_time]

    for slot in future_slots:
        if is_slot_available(slot, duration_hours, booked_ranges):
            return slot.strftime("%Y-%m-%d %H:%M")

    return None


def analyze_space(
    token: str,
    space: Dict[str, str],
    analysis_start: datetime,
    window_weeks: int,
    duration_hours: float,
    location_hours_cache: Dict[str, Dict],
) -> Dict:
    """Analyze booking patterns for a single space.

    Args:
        token: OAuth access token.
        space: Space metadata dictionary.
        analysis_start: Start date for analysis.
        window_weeks: Number of weeks to analyze.
        duration_hours: Booking slot duration in hours.
        location_hours_cache: Cache of location hours data.

    Returns:
        Dictionary containing analysis metrics.
    """
    location_id = space["location_id"]
    space_id = space["space_id"]
    tz = pytz.timezone(TIMEZONE)

    # Fetch location hours (with caching)
    if location_id not in location_hours_cache:
        analysis_end = analysis_start + timedelta(weeks=window_weeks)
        from_date = analysis_start.strftime("%Y-%m-%d")
        to_date = analysis_end.strftime("%Y-%m-%d")

        location_hours_cache[location_id] = get_location_hours(
            token, location_id, from_date, to_date
        )

    hours_data = location_hours_cache[location_id]

    # Fetch bookings
    from_date = analysis_start.strftime("%Y-%m-%d")
    days = window_weeks * 7
    bookings = get_space_bookings(token, space_id, from_date, days)

    # Generate potential slots and booking ranges
    potential_slots = generate_potential_slots(hours_data, duration_hours)
    booked_ranges = calculate_booked_hours(bookings, tz)

    # Calculate metrics for different periods
    periods = {
        "1week": 1,
        "2weeks": 2,
        "1month": 4,
        "2months": 8,
        "3months": 13,
    }

    metrics = {
        "space_id": space_id,
        "space_name": space["space_name"],
        "category_id": space["category_id"],
        "category_name": space["category_name"],
        "location_id": location_id,
        "location_name": space["location_name"],
    }

    for period_name, weeks in periods.items():
        cutoff = analysis_start + timedelta(weeks=weeks)
        rate, avail_hrs, booked_hrs, count = calculate_metrics_for_period(
            potential_slots, booked_ranges, duration_hours, cutoff
        )

        metrics[f"booking_rate_{period_name}"] = round(rate, 2)
        metrics[f"total_hours_available_{period_name}"] = round(avail_hrs, 2)
        metrics[f"total_hours_booked_{period_name}"] = round(booked_hrs, 2)
        metrics[f"booking_count_{period_name}"] = count

    # Find next available slot
    next_available = find_next_available_slot(
        potential_slots, booked_ranges, duration_hours, analysis_start
    )
    metrics["next_available_booking"] = (
        next_available if next_available else "No availability"
    )

    return metrics


def print_summary_by_location(results: List[Dict]) -> None:
    """Print summary statistics grouped by location and category.

    Args:
        results: List of space analysis results.
    """
    location_data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for result in results:
        location = result["location_name"]
        category = result["category_name"]

        for period in ["1week", "2weeks", "1month", "2months", "3months"]:
            booking_key = f"booking_rate_{period}"
            available_key = f"total_hours_available_{period}"
            booked_key = f"total_hours_booked_{period}"
            count_key = f"booking_count_{period}"

            location_data[location][category][booking_key].append(
                result[booking_key]
            )
            location_data[location][category][available_key].append(
                result[available_key]
            )
            location_data[location][category][booked_key].append(
                result[booked_key]
            )
            location_data[location][category][count_key].append(
                result[count_key]
            )

    print("\n" + "=" * 79)
    print("SUMMARY BY LOCATION AND CATEGORY")
    print("=" * 79)

    for location_name in sorted(location_data.keys()):
        print(f"\nLocation: {location_name}")
        print("=" * 79)
        
        # Calculate location-wide totals
        location_totals = defaultdict(list)
        for category_name in location_data[location_name].keys():
            for key, values in location_data[location_name][category_name].items():
                location_totals[key].extend(values)
        
        # Print location totals
        print("\n  LOCATION TOTALS:")
        print("  " + "-" * 77)
        for period in ["1week", "2weeks", "1month", "2months", "3months"]:
            booking_key = f"booking_rate_{period}"
            available_key = f"total_hours_available_{period}"
            booked_key = f"total_hours_booked_{period}"
            count_key = f"booking_count_{period}"

            if booking_key in location_totals:
                avg_booking = sum(location_totals[booking_key]) / len(location_totals[booking_key])
                total_available = sum(location_totals[available_key])
                total_booked = sum(location_totals[booked_key])
                total_count = sum(location_totals[count_key])

                print(
                    f"  {period.upper():12} - Avg Booking: {avg_booking:6.2f}% | "
                    f"Available: {total_available:8.2f}h | "
                    f"Booked: {total_booked:8.2f}h | "
                    f"Count: {int(total_count):4}"
                )
        
        # Print breakdown by category
        for category_name in sorted(location_data[location_name].keys()):
            print(f"\n  Category: {category_name}")
            print("  " + "-" * 77)
            
            data = location_data[location_name][category_name]

            for period in ["1week", "2weeks", "1month", "2months", "3months"]:
                booking_key = f"booking_rate_{period}"
                available_key = f"total_hours_available_{period}"
                booked_key = f"total_hours_booked_{period}"
                count_key = f"booking_count_{period}"

                if booking_key in data:
                    avg_booking = sum(data[booking_key]) / len(data[booking_key])
                    total_available = sum(data[available_key])
                    total_booked = sum(data[booked_key])
                    total_count = sum(data[count_key])

                    print(
                        f"    {period.upper():12} - Avg Booking: {avg_booking:6.2f}% | "
                        f"Available: {total_available:8.2f}h | "
                        f"Booked: {total_booked:8.2f}h | "
                        f"Count: {int(total_count):4}"
                    )

    print("\n" + "=" * 79)


def print_longest_lead_times(results: List[Dict], top_n: int = 10) -> None:
    """Print spaces with the longest lead times for next available booking.

    Args:
        results: List of space analysis results.
        top_n: Number of spaces to display (default: 10).
    """
    spaces_with_times = []

    for result in results:
        next_available = result.get("next_available_booking", "")
        if next_available and next_available != "No availability":
            try:
                available_dt = datetime.strptime(
                    next_available, "%Y-%m-%d %H:%M"
                )
                spaces_with_times.append(
                    {
                        "space_name": result["space_name"],
                        "location_name": result["location_name"],
                        "next_available": next_available,
                        "next_available_dt": available_dt,
                    }
                )
            except ValueError:
                continue

    spaces_with_times.sort(key=lambda x: x["next_available_dt"], reverse=True)

    print("\n" + "=" * 79)
    print(f"TOP {top_n} SPACES WITH LONGEST LEAD TIMES")
    print("=" * 79)

    for idx, space in enumerate(spaces_with_times[:top_n], start=1):
        print(
            f"{idx:2}. {space['space_name']:<45} "
            f"({space['location_name'][:25]})"
        )
        print(f"    Next Available: {space['next_available']}")

    print("=" * 79)


def write_results_to_csv(results: List[Dict], output_file: str) -> None:
    """Write analysis results to CSV file.

    Args:
        results: List of space analysis results.
        output_file: Path to output CSV file.
    """
    if not results:
        print("No results to write.")
        return

    fieldnames = [
        "space_id",
        "space_name",
        "category_id",
        "category_name",
        "location_id",
        "location_name",
        "booking_rate_1week",
        "total_hours_available_1week",
        "total_hours_booked_1week",
        "booking_count_1week",
        "booking_rate_2weeks",
        "total_hours_available_2weeks",
        "total_hours_booked_2weeks",
        "booking_count_2weeks",
        "booking_rate_1month",
        "total_hours_available_1month",
        "total_hours_booked_1month",
        "booking_count_1month",
        "booking_rate_2months",
        "total_hours_available_2months",
        "total_hours_booked_2months",
        "booking_count_2months",
        "booking_rate_3months",
        "total_hours_available_3months",
        "total_hours_booked_3months",
        "booking_count_3months",
        "next_available_booking",
    ]

    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nResults written to: {output_file}")


def ensure_directories_exist() -> None:
    """Ensure input and output directories exist."""
    import os

    os.makedirs("input", exist_ok=True)
    os.makedirs("output", exist_ok=True)


def main() -> None:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Analyze LibCal space booking rates."
    )
    
    # Generate default output filename with current date
    current_date = datetime.now().strftime("%Y%m%d")
    default_output = DEFAULT_OUTPUT_FILE_TEMPLATE.format(date=current_date)
    
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT_FILE,
        help=f"Input CSV file (default: {DEFAULT_INPUT_FILE})",
    )
    parser.add_argument(
        "--output",
        default=default_output,
        help=f"Output CSV file (default: {default_output})",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=DEFAULT_ANALYSIS_WINDOW_WEEKS,
        help=f"Analysis window in weeks (default: {DEFAULT_ANALYSIS_WINDOW_WEEKS}, ~90 days)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_BOOKING_DURATION_HOURS,
        help=f"Booking duration in hours (default: {DEFAULT_BOOKING_DURATION_HOURS})",
    )

    args = parser.parse_args()

    try:
        ensure_directories_exist()

        print("LibCal Space Booking Analysis")
        print("=" * 79)
        print(f"Input file: {args.input}")
        print(f"Output file: {args.output}")
        print(f"Analysis window: {args.window} weeks")
        print(f"Booking duration: {args.duration} hours")
        print("=" * 79)

        print("\n[1/4] Obtaining OAuth token...")
        token = get_oauth_token()
        print("      ✓ Token obtained successfully")

        print("\n[2/4] Loading space data from CSV...")
        spaces = load_spaces_from_csv(args.input)
        print(f"      ✓ Loaded {len(spaces)} spaces")

        print("\n[3/4] Analyzing space bookings...")
        tz = pytz.timezone(TIMEZONE)
        analysis_start = datetime.now(tz).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        results = []
        location_hours_cache = {}

        for idx, space in enumerate(spaces, start=1):
            print(
                f"      Processing space {idx}/{len(spaces)}: "
                f"{space['space_name']}..."
            )

            metrics = analyze_space(
                token,
                space,
                analysis_start,
                args.window,
                args.duration,
                location_hours_cache,
            )
            results.append(metrics)

        print("      ✓ Analysis complete")

        print_summary_by_location(results)
        print_longest_lead_times(results)

        print("\n[4/4] Writing results to CSV...")
        write_results_to_csv(results, args.output)
        print("      ✓ Complete")

        print("\n" + "=" * 79)
        print("Analysis finished successfully!")
        print("=" * 79)

    except (LibCalAPIError, DataValidationError, FileNotFoundError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nUNEXPECTED ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()