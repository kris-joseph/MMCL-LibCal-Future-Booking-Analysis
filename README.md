# LibCal Space Booking Capacity Analysis

A Python script for analyzing booking patterns and availability of studio and maker spaces using Springshare's LibCal API. This tool calculates booking rates, tracks availability, and generates comprehensive reports to help assess space utilization.

## Features

- **Automated booking rate analysis** across multiple time periods (1 week, 2 weeks, 1 month, 2 months, 3 months)
- **Next available booking detection** for each space
- **Hierarchical reporting** by location and category
- **CSV export** with timestamped filenames for historical tracking
- **Configurable analysis windows** and booking durations
- **Robust error handling** and data validation

## Requirements

- Python 3.7 or higher
- Active LibCal API credentials
- CSV file containing space configuration data

## Installation

1. Clone or download this repository to your local machine.

2. Install required Python packages:

```bash
pip install -r requirements.txt
```

3. Create the required directory structure:

```bash
mkdir -p input output
```

## Configuration

### Input File Format

Place your space configuration CSV file in the `input/` directory. The default filename is `spaces_to_analyze.csv`.

**Required CSV columns:**
- `category_id` - Numeric ID for the space category
- `category_name` - Name of the space category (e.g., "Audio Recording Studios")
- `space_id` - Numeric ID for the specific space (used for booking queries)
- `space_name` - Name of the space (e.g., "Scott 203K - Audio Recording Studio")
- `location_id` - Numeric ID for the location (used for hours queries)
- `location_name` - Name of the location (e.g., "Scott Library Making & Media Creation Lab")

**Important:** The `location_id` must correspond to the location ID used in LibCal's Hours API, which may differ from the location ID used for bookings.

**Example CSV:**
```csv
category_id,category_name,space_id,space_name,location_id,location_name
6842,Flex Studio Spaces,19904,Scott 204 - Flex Studio,7571,Scott Library Making & Media Creation Lab
6843,Audio Recording Studios,19900,Scott 203K - Audio Recording Studio,7571,Scott Library Making & Media Creation Lab
```

### API Credentials

API credentials are configured in the script itself. Update the following constants in `libcal_analysis.py`:

```python
OAUTH_CLIENT_ID = "your_client_id"
OAUTH_CLIENT_SECRET = "your_client_secret"
```

### Configurable Parameters

Global constants at the top of the script can be modified:

- `TIMEZONE` - Time zone for analysis (default: "America/Toronto")
- `DEFAULT_ANALYSIS_WINDOW_WEEKS` - Analysis period in weeks (default: 13 weeks / ~90 days)
- `DEFAULT_BOOKING_DURATION_HOURS` - Assumed booking duration for availability checks (default: 3.0 hours)
- `BOOKING_TIME_INCREMENTS` - Valid booking start times in minutes (default: [0, 15, 30, 45])

## Usage

### Basic Usage

Run the script with default settings:

```bash
python space_capacity_analysis.py
```

This will:
- Read from `input/spaces_to_analyze.csv`
- Write to `output/space_booking_analysis_YYYYMMDD.csv`
- Analyze the next 13 weeks (90 days)
- Look for 3-hour booking slots

### Command-Line Options

```bash
python space_capacity_analysis.py [OPTIONS]
```

**Available options:**

- `--input CSV_FILE` - Specify input CSV file path (default: `input/spaces_to_analyze.csv`)
- `--output CSV_FILE` - Specify output CSV file path (default: `output/space_booking_analysis_YYYYMMDD.csv`)
- `--window WEEKS` - Set analysis window in weeks (default: 13)
- `--duration HOURS` - Set booking slot duration in hours (default: 3.0)

**Examples:**

Analyze 8 weeks with 2-hour booking slots:
```bash
python space_capacity_analysis.py --window 8 --duration 2
```

Use custom input and output files:
```bash
python space_capacity_analysis.py --input data/my_spaces.csv --output reports/analysis.csv
```

Analyze 4 weeks with custom output location:
```bash
python space_capacity_analysis.py --window 4 --output output/monthly_report_$(date +%Y%m%d).csv
```

## Output

### Console Output

The script provides three types of console output:

1. **Progress indicators** showing processing status
2. **Location-level summary** with totals and category breakdowns
3. **Top 10 spaces with longest lead times** (most distant next available booking)

**Example console output:**
```
===============================================================================
LOCATION-LEVEL SUMMARY (BY CATEGORY)
===============================================================================

Scott Library Making & Media Creation Lab
===============================================================================

LOCATION TOTALS:
  1WEEK        - Avg Booking:  45.23% | Available:   150.00h | Booked:    67.50h | Count:   25
  2WEEKS       - Avg Booking:  43.10% | Available:   300.00h | Booked:   129.30h | Count:   48

  Category: Audio Recording Studios
    1WEEK      - Avg Booking:  60.00% | Available:    30.00h | Booked:    18.00h | Count:    8
    2WEEKS     - Avg Booking:  58.50% | Available:    60.00h | Booked:    35.10h | Count:   15

===============================================================================
TOP 10 SPACES WITH LONGEST LEAD TIMES
===============================================================================
 1. Prusa XL #1 "Tiamat"                          (Scott Library Making & M)
    Next Available: 2025-11-15 14:30
 2. Green Screen Video Studio (Rm 3060C)          (Markham Library Media Cr)
    Next Available: 2025-11-12 11:00
```

### CSV Output

The CSV file contains one row per space with the following columns:

**Space identification:**
- `space_id`, `space_name`, `category_id`, `category_name`, `location_id`, `location_name`

**For each time period (1week, 2weeks, 1month, 2months, 3months):**
- `booking_rate_{period}` - Percentage of available hours that are booked
- `total_hours_available_{period}` - Total hours the space is available
- `total_hours_booked_{period}` - Total hours with confirmed bookings
- `booking_count_{period}` - Number of individual bookings

**Availability:**
- `next_available_booking` - Date and time of next available booking slot (format: YYYY-MM-DD HH:MM)

The output filename includes the date of analysis (e.g., `space_booking_analysis_20251009.csv`), allowing you to maintain historical records.

## Troubleshooting

### Common Issues

**"Input file not found"**
- Ensure the CSV file exists in the `input/` directory
- Check that the filename matches what you specified (default: `spaces_to_analyze.csv`)

**"Missing or empty value for [field]"**
- Verify that all required columns are present in your CSV
- Check that no cells are empty in any row

**"Failed to obtain OAuth token"**
- Verify your `OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET` are correct
- Check your network connection
- Confirm your API credentials are still valid

**All available hours show as 0**
- Verify that the `location_id` values correspond to locations with configured hours in LibCal
- Check that the location IDs are for the Hours API (not the booking location IDs)
- Use the diagnostic script (see below) to verify the Hours API response

**Booking counts don't match expectations**
- Verify the analysis date range matches your expectations
- Check that bookings fall within operating hours
- Use the diagnostic script to see detailed booking processing

### Diagnostic Script

A diagnostic script (`diagnostic_script.py`) is included to help troubleshoot data issues:

```bash
python diagnostic_script.py
```

When prompted, enter a location ID and space ID from your CSV. The script will:
- Show the raw API responses
- Display how dates and times are parsed
- Reveal which bookings are counted or excluded
- Summarize the calculations

This is invaluable for understanding why certain data might not appear as expected.

## API Limitations

- **Hours API limit:** Maximum 100 days per request (script defaults to 90 days for safety)
- **Bookings API limit:** Maximum 500 bookings per request (script uses 150)
- **OAuth token validity:** 60 minutes (script requests a new token each run)
- **Rate limiting:** Be mindful of API rate limits when running frequently

## Understanding the Metrics

### Booking Rate
The percentage of available hours that have confirmed bookings in MMCL studio and editing spaces. Calculated as:
```
booking_rate = (total_hours_booked / total_hours_available) × 100
```

### Next Available Booking
The earliest date/time when a continuous booking slot of the configured duration is available. This considers:
- Location operating hours
- Existing bookings
- Valid booking time increments (0, 15, 30, 45 minutes past the hour)

### Booking Count
The total number of individual bookings within the time period. A booking is counted if any part of it falls within the analysis period.

## Best Practices

1. **Run weekly** on a consistent schedule (e.g., Monday mornings) for trend tracking
2. **Archive outputs** - The dated filenames make it easy to maintain historical data
3. **Verify location IDs** - Ensure you're using the correct IDs for the Hours API
4. **Monitor lead times** - Spaces with very long lead times may need capacity increases
5. **Compare categories** - Use the category breakdowns to identify high-demand space types


## Support

For issues related to:
- **The script:** Review this README and use the diagnostic script
- **LibCal API:** Consult Springshare's API documentation at https://springshare.com/libcal/
- **Your LibCal configuration:** Contact your LibCal administrator

## Version History

- **v1.0** - Initial release with booking analysis, category breakdowns, and CSV export
