#!/usr/bin/env python3
"""Diagnostic script to test LibCal API responses and processing logic."""

import json
import requests
from datetime import datetime, timedelta
import pytz

# Configuration from main script
API_BASE_URL = "https://yorku.libcal.com/api/1.1"
OAUTH_CLIENT_ID = "CLIENT_ID"
OAUTH_CLIENT_SECRET = "CLIENT_SECRET"
TIMEZONE = "America/Toronto"

# Get OAuth token
print("Obtaining OAuth token...")
token_url = f"{API_BASE_URL}/oauth/token"
token_params = {
    "client_id": OAUTH_CLIENT_ID,
    "client_secret": OAUTH_CLIENT_SECRET,
    "grant_type": "client_credentials",
}

token_response = requests.post(token_url, data=token_params, timeout=30)
token_response.raise_for_status()
token_data = token_response.json()
token = token_data["access_token"]
print(f"✓ Token obtained: {token[:20]}...\n")

# Test parameters
location_id = "7571"
space_id = "19904"
tz = pytz.timezone(TIMEZONE)
start_date = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
end_date = start_date + timedelta(weeks=1)

print(f"Analysis Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
print("=" * 79)

# Get location hours
print(f"\n1. Fetching hours for location {location_id}...")
hours_url = f"{API_BASE_URL}/hours/{location_id}"
headers = {"Authorization": f"Bearer {token}"}
from_date_str = start_date.strftime("%Y-%m-%d")
to_date_str = (end_date - timedelta(days=1)).strftime("%Y-%m-%d")
params = {"from": from_date_str, "to": to_date_str}

hours_response = requests.get(hours_url, headers=headers, params=params, timeout=30)
hours_response.raise_for_status()
hours_data = hours_response.json()

print(f"\n   Raw Hours API Response:")
print(json.dumps(hours_data, indent=2))

# Process hours like the main script does
hours_by_date = {}
for location in hours_data:
    if "dates" not in location:
        continue
    
    dates_dict = location["dates"]
    
    for date_str, day_data in dates_dict.items():
        if not day_data or day_data.get("status") != "open":
            print(f"\n   {date_str}: CLOSED")
            continue
        
        hours_list = day_data.get("hours", [])
        time_ranges = []
        
        for hours in hours_list:
            from_time = hours.get("from")
            to_time = hours.get("to")
            
            if from_time and to_time:
                from_dt = datetime.strptime(f"{date_str} {from_time}", "%Y-%m-%d %I:%M%p")
                to_dt = datetime.strptime(f"{date_str} {to_time}", "%Y-%m-%d %I:%M%p")
                
                from_dt = tz.localize(from_dt)
                to_dt = tz.localize(to_dt)
                
                duration = (to_dt - from_dt).total_seconds() / 3600
                time_ranges.append((from_dt, to_dt))
                print(f"\n   {date_str}: OPEN {from_time} - {to_time} ({duration:.1f} hours)")
        
        if time_ranges:
            hours_by_date[date_str] = time_ranges

# Calculate total available hours
print(f"\n2. Calculating total available hours...")
total_hours = 0.0
current_date = start_date.date()
end_date_only = end_date.date()

while current_date < end_date_only:
    date_str = current_date.strftime("%Y-%m-%d")
    
    if date_str in hours_by_date:
        for open_time, close_time in hours_by_date[date_str]:
            duration = (close_time - open_time).total_seconds() / 3600
            total_hours += duration
            print(f"   {date_str}: +{duration:.1f}h")
    else:
        print(f"   {date_str}: No hours data (closed or missing)")
    
    current_date += timedelta(days=1)

print(f"\n   TOTAL AVAILABLE HOURS: {total_hours:.1f}h")

# Get bookings
print(f"\n3. Fetching bookings for space {space_id}...")
bookings_url = f"{API_BASE_URL}/space/bookings"
days_to_fetch = (end_date - start_date).days
bookings_params = {
    "eid": space_id,
    "date": from_date_str,
    "days": days_to_fetch,
    "limit": 150,
    "include_tentative": 1,
    "include_cancel": 0,
}

bookings_response = requests.get(
    bookings_url, headers=headers, params=bookings_params, timeout=30
)
bookings_response.raise_for_status()
bookings_data = bookings_response.json()

print(f"\n   Total bookings returned by API: {len(bookings_data)}")

# Process bookings like the main script does
print(f"\n4. Processing bookings within date range...")
total_booked = 0.0
booking_count = 0

for idx, booking in enumerate(bookings_data, 1):
    try:
        from_date_raw = booking["fromDate"]
        to_date_raw = booking["toDate"]
        
        # Parse with timezone offset
        from_date = datetime.fromisoformat(from_date_raw.replace("+11:00", ""))
        to_date = datetime.fromisoformat(to_date_raw.replace("+11:00", ""))
        
        from_date = tz.localize(from_date.replace(tzinfo=None))
        to_date = tz.localize(to_date.replace(tzinfo=None))
        
        booking_start = max(from_date, start_date)
        booking_end = min(to_date, end_date)
        
        print(f"\n   Booking {idx}:")
        print(f"      Raw fromDate: {from_date_raw}")
        print(f"      Raw toDate: {to_date_raw}")
        print(f"      Parsed from: {from_date}")
        print(f"      Parsed to: {to_date}")
        print(f"      Analysis period: {start_date} to {end_date}")
        print(f"      Overlap window: {booking_start} to {booking_end}")
        
        if booking_start < booking_end:
            duration = (booking_end - booking_start).total_seconds() / 3600
            total_booked += duration
            booking_count += 1
            print(f"      ✓ COUNTED: {duration:.2f}h")
        else:
            print(f"      ✗ EXCLUDED: No overlap with analysis period")
    
    except (KeyError, ValueError) as e:
        print(f"\n   Booking {idx}: ERROR - {e}")
        continue

print(f"\n   TOTAL BOOKED HOURS: {total_booked:.2f}h")
print(f"   BOOKING COUNT: {booking_count}")

# Summary
print("\n" + "=" * 79)
print("SUMMARY")
print("=" * 79)
print(f"Available Hours: {total_hours:.1f}h")
print(f"Booked Hours: {total_booked:.2f}h")
print(f"Booking Count: {booking_count}")
print(f"Booking Rate: {(total_booked/total_hours*100):.2f}%" if total_hours > 0 else "N/A")
print("=" * 79)
#!/usr/bin/env python3
"""Diagnostic script to test LibCal API responses."""

import json
import requests

# Configuration from main script
API_BASE_URL = "https://yorku.libcal.com/api/1.1"
OAUTH_CLIENT_ID = "308"
OAUTH_CLIENT_SECRET = "936dcbaf514162bc2b36e54ec9f4ac9f"

# Get OAuth token
print("Obtaining OAuth token...")
token_url = f"{API_BASE_URL}/oauth/token"
token_params = {
    "client_id": OAUTH_CLIENT_ID,
    "client_secret": OAUTH_CLIENT_SECRET,
    "grant_type": "client_credentials",
}

token_response = requests.post(token_url, data=token_params, timeout=30)
token_response.raise_for_status()
token_data = token_response.json()
token = token_data["access_token"]
print(f"✓ Token obtained: {token[:20]}...\n")

# Test location hours API
# Replace with an actual location_id from your CSV
location_id = input("Enter a location_id to test (from your CSV): ").strip()

print(f"\nFetching hours for location {location_id}...")
hours_url = f"{API_BASE_URL}/hours/{location_id}"
headers = {"Authorization": f"Bearer {token}"}
params = {"from": "2025-10-09", "to": "2025-10-16"}

hours_response = requests.get(hours_url, headers=headers, params=params, timeout=30)
hours_response.raise_for_status()

print("\n" + "=" * 79)
print("HOURS API RESPONSE:")
print("=" * 79)
print(json.dumps(hours_response.json(), indent=2))

# Test bookings API
space_id = input("\n\nEnter a space_id to test (from your CSV): ").strip()

print(f"\nFetching bookings for space {space_id}...")
bookings_url = f"{API_BASE_URL}/space/bookings"
bookings_params = {
    "eid": space_id,
    "date": "2025-10-09",
    "days": 7,
    "limit": 150,
    "include_tentative": 1,
    "include_cancel": 0,
}

bookings_response = requests.get(
    bookings_url, headers=headers, params=bookings_params, timeout=30
)
bookings_response.raise_for_status()

print("\n" + "=" * 79)
print("BOOKINGS API RESPONSE:")
print("=" * 79)
print(json.dumps(bookings_response.json(), indent=2))
