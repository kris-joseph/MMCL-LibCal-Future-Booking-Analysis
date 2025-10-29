#!/usr/bin/env python3
"""LibCal Space Booking Dashboard Generator.

This script generates a static HTML dashboard for GitHub Pages displaying:
1. Current next available booking dates for each space (color-coded)
2. Time-series graphs of booking rates over time (Monday data only)

The dashboard is updated daily for current availability, but time-series
data is only updated on Mondays.
"""

import os
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict
import glob


# Configuration
OUTPUT_DIR = Path("output")
DOCS_DIR = Path("docs")
TIME_SERIES_DATA_FILE = DOCS_DIR / "time_series_data.json"
INPUT_CSV = Path("input/spaces_to_analyze.csv")

# Color configuration for next available date gradient
GREEN_RGB = (34, 197, 94)   # Tailwind green-500
RED_RGB = (239, 68, 68)     # Tailwind red-500
MAX_DAYS_FOR_RED = 14


def ensure_docs_directory():
    """Ensure docs directory exists for GitHub Pages."""
    DOCS_DIR.mkdir(exist_ok=True)


def get_latest_output_file() -> Path:
    """Get the most recent output CSV file."""
    output_files = sorted(OUTPUT_DIR.glob("space_booking_analysis_*.csv"))
    if not output_files:
        raise FileNotFoundError("No output CSV files found in output directory")
    return output_files[-1]


def parse_date_from_filename(filename: str) -> datetime:
    """Extract date from filename like 'space_booking_analysis_20241028.csv'."""
    # Extract YYYYMMDD from filename
    date_str = filename.split('_')[-1].replace('.csv', '')
    return datetime.strptime(date_str, '%Y%m%d')


def is_monday_file(filepath: Path) -> bool:
    """Check if the file was created on a Monday."""
    try:
        date = parse_date_from_filename(filepath.name)
        return date.weekday() == 0  # Monday is 0
    except (ValueError, IndexError):
        return False


def get_monday_files() -> List[Path]:
    """Get all output files that were created on Mondays, sorted by date."""
    all_files = OUTPUT_DIR.glob("space_booking_analysis_*.csv")
    monday_files = [f for f in all_files if is_monday_file(f)]
    return sorted(monday_files)


def sort_locations(location_name: str) -> int:
    """
    Custom sort order for locations.
    Returns sort priority (lower numbers appear first).
    """
    if 'Scott Library' in location_name:
        return 0
    elif 'Media Creation Studios' in location_name:
        return 1
    elif 'Visualization Studio' in location_name:
        return 2
    else:
        return 99  # Unknown locations go last


def interpolate_color(days: int) -> str:
    """
    Interpolate color from green (0 days) to red (14+ days).
    
    Args:
        days: Number of days until next available booking
        
    Returns:
        RGB color string like 'rgb(r, g, b)'
    """
    if days <= 0:
        return f'rgb({GREEN_RGB[0]}, {GREEN_RGB[1]}, {GREEN_RGB[2]})'
    if days >= MAX_DAYS_FOR_RED:
        return f'rgb({RED_RGB[0]}, {RED_RGB[1]}, {RED_RGB[2]})'
    
    # Linear interpolation between green and red
    ratio = days / MAX_DAYS_FOR_RED
    r = int(GREEN_RGB[0] + (RED_RGB[0] - GREEN_RGB[0]) * ratio)
    g = int(GREEN_RGB[1] + (RED_RGB[1] - GREEN_RGB[1]) * ratio)
    b = int(GREEN_RGB[2] + (RED_RGB[2] - GREEN_RGB[2]) * ratio)
    
    return f'rgb({r}, {g}, {b})'


def calculate_days_until(next_available: str) -> int:
    """Calculate days from today until the next available date."""
    try:
        if not next_available or next_available.lower() in ['none', 'n/a', '']:
            return MAX_DAYS_FOR_RED + 1  # Return max+ for unavailable spaces
        
        # Try parsing with timestamp first, then without
        try:
            next_date = datetime.strptime(next_available, '%Y-%m-%d %H:%M')
        except ValueError:
            next_date = datetime.strptime(next_available, '%Y-%m-%d')
        
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        delta = (next_date.replace(hour=0, minute=0, second=0, microsecond=0) - today).days
        return max(0, delta)  # Don't return negative values
    except (ValueError, AttributeError):
        return MAX_DAYS_FOR_RED + 1


def load_current_data() -> Dict[str, List[Dict]]:
    """Load the most recent output CSV and organize by location."""
    latest_file = get_latest_output_file()
    
    spaces_by_location = defaultdict(list)
    
    with open(latest_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            location_name = row['location_name']
            days_until = calculate_days_until(row['next_available_booking'])
            
            spaces_by_location[location_name].append({
                'space_id': row['space_id'],
                'space_name': row['space_name'],
                'category_name': row['category_name'],
                'next_available': row['next_available_booking'],
                'days_until': days_until,
                'color': interpolate_color(days_until),
                'booking_rate_1week': float(row['booking_rate_1week']) if row['booking_rate_1week'] else 0,
            })
    
    # Sort spaces alphabetically within each location
    for location in spaces_by_location:
        spaces_by_location[location].sort(key=lambda x: x['space_name'])
    
    return dict(spaces_by_location)


def update_time_series_data() -> Dict:
    """Update time series data file with Monday data if today is Monday."""
    today = datetime.now()
    
    # Load existing time series data
    if TIME_SERIES_DATA_FILE.exists():
        with open(TIME_SERIES_DATA_FILE, 'r') as f:
            time_series_data = json.load(f)
    else:
        time_series_data = {
            'dates': [],
            'spaces': {}
        }
    
    # Only update if today is Monday
    if today.weekday() == 0:  # Monday
        monday_files = get_monday_files()
        
        if monday_files:
            # Rebuild time series data from all Monday files
            time_series_data = {
                'dates': [],
                'spaces': {}
            }
            
            for monday_file in monday_files:
                file_date = parse_date_from_filename(monday_file.name)
                date_str = file_date.strftime('%Y-%m-%d')
                
                if date_str not in time_series_data['dates']:
                    time_series_data['dates'].append(date_str)
                    
                    with open(monday_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            space_id = row['space_id']
                            space_name = row['space_name']
                            location_name = row['location_name']
                            booking_rate = float(row['booking_rate_1week']) if row['booking_rate_1week'] else 0
                            
                            if space_id not in time_series_data['spaces']:
                                time_series_data['spaces'][space_id] = {
                                    'space_name': space_name,
                                    'location_name': location_name,
                                    'data': []
                                }
                            
                            time_series_data['spaces'][space_id]['data'].append(booking_rate)
            
            # Save updated time series data
            with open(TIME_SERIES_DATA_FILE, 'w') as f:
                json.dump(time_series_data, f, indent=2)
    
    return time_series_data


def generate_html(spaces_by_location: Dict, time_series_data: Dict) -> str:
    """Generate the complete HTML dashboard."""
    
    # Get last updated time
    latest_file = get_latest_output_file()
    last_updated = parse_date_from_filename(latest_file.name).strftime('%B %d, %Y')
    
    # Organize time series by location
    time_series_by_location = defaultdict(list)
    for space_id, space_data in time_series_data['spaces'].items():
        location = space_data['location_name']
        time_series_by_location[location].append({
            'space_id': space_id,
            'space_name': space_data['space_name'],
            'data': space_data['data']
        })
    
    # Sort spaces within each location alphabetically
    for location in time_series_by_location:
        time_series_by_location[location].sort(key=lambda x: x['space_name'])
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MMCL Space Booking Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="dashboard.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.js"></script>
</head>
<body>
    <div class="container-fluid">
        <header class="py-4 mb-4 border-bottom">
            <div class="row align-items-center">
                <div class="col">
                    <h1 class="display-5">MMCL Space Booking Dashboard</h1>
                    <p class="text-muted">Media Creation Spaces</p>
                </div>
                <div class="col-auto text-end">
                    <p class="mb-0 text-muted small">Last Updated Before MMCL Opened on</p>
                    <p class="mb-0 fw-bold">{last_updated}</p>
                </div>
            </div>
        </header>

        <section id="availability" class="mb-5">
            <div class="row mb-3">
                <div class="col">
                    <h2 class="h3">Next Available Booking for Each Space</h2>
                    <p class="text-muted">Data is updated each morning and shows the next available timeslot for each space. Color indicates booking demand: <span class="badge" style="background-color: {interpolate_color(0)}">Available Today</span> to <span class="badge" style="background-color: {interpolate_color(MAX_DAYS_FOR_RED)}">14+ Days Out</span></p>
                </div>
            </div>
'''
    
    # Generate availability cards by location
    for location_name in sorted(spaces_by_location.keys(), key=sort_locations):
        spaces = spaces_by_location[location_name]
        
        html += f'''
            <div class="location-section mb-4">
                <h3 class="h5 mb-3">{location_name}</h3>
                <div class="row g-3">
'''
        
        for space in spaces:
            days_text = "Today" if space['days_until'] == 0 else \
                       "Tomorrow" if space['days_until'] == 1 else \
                       f"{space['days_until']} days" if space['days_until'] < MAX_DAYS_FOR_RED else \
                       "14+ days"
            
            next_available_display = space['next_available'] if space['next_available'] else 'N/A'
            
            html += f'''
                    <div class="col-md-6 col-lg-4 col-xl-3">
                        <div class="card space-card h-100" style="border-left: 4px solid {space['color']}">
                            <div class="card-body">
                                <h4 class="card-title h6">{space['space_name']}</h4>
                                <p class="card-text text-muted small mb-2">{space['category_name']}</p>
                                <div class="availability-badge" style="background-color: {space['color']}">
                                    <div class="days-until">{days_text}</div>
                                    <div class="next-date">{next_available_display}</div>
                                </div>
                                <div class="mt-2">
                                    <small class="text-muted">1-Week Booking Rate: {space['booking_rate_1week']:.1f}%</small>
                                </div>
                            </div>
                        </div>
                    </div>
'''
        
        html += '''
                </div>
            </div>
'''
    
    html += '''
        </section>

        <section id="trends" class="mb-5">
            <div class="row mb-3">
                <div class="col">
                    <h2 class="h3">Booking Rate Trends</h2>
                    <p class="text-muted">Weekly booking rates over time (Monday data only)</p>
                </div>
            </div>
'''
    
    # Generate time series charts by location
    if time_series_data['dates']:
        for location_name in sorted(time_series_by_location.keys(), key=sort_locations):
            spaces = time_series_by_location[location_name]
            location_id = location_name.replace(' ', '_').replace('&', 'and')
            
            html += f'''
            <div class="location-section mb-4">
                <h3 class="h5 mb-3">{location_name}</h3>
                <div class="chart-container">
                    <canvas id="chart_{location_id}"></canvas>
                </div>
            </div>
'''
    else:
        html += '''
            <div class="alert alert-info">
                <p class="mb-0">No time series data available yet. Data will appear after the first Monday collection.</p>
            </div>
'''
    
    html += '''
        </section>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="dashboard.js"></script>
    <script>
        // Initialize charts with data
'''
    
    # Add chart initialization JavaScript
    if time_series_data['dates']:
        html += f'''
        const timeSeriesDates = {json.dumps(time_series_data['dates'])};
        const timeSeriesByLocation = {json.dumps(dict(time_series_by_location))};
        
        // Create a chart for each location
        Object.keys(timeSeriesByLocation).forEach(locationName => {{
            const locationId = locationName.replace(/ /g, '_').replace(/&/g, 'and');
            const spaces = timeSeriesByLocation[locationName];
            
            const datasets = spaces.map((space, index) => ({{
                label: space.space_name,
                data: space.data,
                borderColor: getColorForIndex(index),
                backgroundColor: getColorForIndex(index, 0.1),
                tension: 0.3,
                pointRadius: 4,
                pointHoverRadius: 6
            }}));
            
            createChart(`chart_${{locationId}}`, timeSeriesDates, datasets);
        }});
'''
    
    html += '''
    </script>
</body>
</html>
'''
    
    return html


def generate_css() -> str:
    """Generate the CSS stylesheet."""
    return '''/* MMCL Dashboard Styles */

:root {
    --primary-color: #1e40af;
    --secondary-color: #64748b;
    --success-color: #22c55e;
    --danger-color: #ef4444;
    --border-radius: 8px;
}

body {
    background-color: #f8fafc;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

.container-fluid {
    max-width: 1400px;
    margin: 0 auto;
    padding: 20px;
}

header {
    background-color: white;
    border-radius: var(--border-radius);
    padding: 20px;
    margin-bottom: 30px;
}

.location-section {
    background-color: white;
    border-radius: var(--border-radius);
    padding: 20px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.space-card {
    transition: transform 0.2s, box-shadow 0.2s;
    border-radius: var(--border-radius);
}

.space-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.availability-badge {
    padding: 12px;
    border-radius: 6px;
    text-align: center;
    color: white;
    font-weight: 600;
    margin-top: 10px;
}

.days-until {
    font-size: 1.1rem;
    margin-bottom: 4px;
}

.next-date {
    font-size: 0.85rem;
    opacity: 0.9;
}

.chart-container {
    position: relative;
    height: 400px;
    background-color: white;
    padding: 20px;
    border-radius: var(--border-radius);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.badge {
    padding: 6px 12px;
    border-radius: 4px;
    color: white;
    font-weight: 500;
}

@media (max-width: 768px) {
    .chart-container {
        height: 300px;
    }
    
    .space-card {
        margin-bottom: 15px;
    }
}

/* Print styles */
@media print {
    .space-card {
        break-inside: avoid;
    }
    
    .chart-container {
        height: 300px;
    }
}
'''


def generate_js() -> str:
    """Generate the JavaScript file."""
    return '''// MMCL Dashboard JavaScript

// Color palette for charts (colorblind-friendly)
const CHART_COLORS = [
    '#2563eb', // blue
    '#dc2626', // red
    '#16a34a', // green
    '#ca8a04', // yellow
    '#9333ea', // purple
    '#ea580c', // orange
    '#0891b2', // cyan
    '#db2777', // pink
    '#65a30d', // lime
    '#0d9488', // teal
];

function getColorForIndex(index, alpha = 1) {
    const color = CHART_COLORS[index % CHART_COLORS.length];
    if (alpha === 1) return color;
    
    // Convert hex to rgba
    const r = parseInt(color.substr(1, 2), 16);
    const g = parseInt(color.substr(3, 2), 16);
    const b = parseInt(color.substr(5, 2), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function createChart(canvasId, dates, datasets) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: dates,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        boxWidth: 12,
                        padding: 10,
                        font: {
                            size: 11
                        }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += context.parsed.y.toFixed(1) + '%';
                            }
                            return label;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    ticks: {
                        callback: function(value) {
                            return value.toFixed(0) + '%';
                        }
                    },
                    title: {
                        display: true,
                        text: 'Booking Rate'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Date (Mondays)'
                    }
                }
            }
        }
    });
}

// Smooth scroll for internal links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});
'''


def main():
    """Main entry point for dashboard generation."""
    print("LibCal Space Booking Dashboard Generator")
    print("=" * 60)
    
    try:
        # Ensure docs directory exists
        ensure_docs_directory()
        print("✓ Docs directory ready")
        
        # Load current availability data
        print("\n[1/5] Loading current availability data...")
        spaces_by_location = load_current_data()
        print(f"      ✓ Loaded data for {sum(len(spaces) for spaces in spaces_by_location.values())} spaces")
        
        # Update time series data (only on Mondays)
        print("\n[2/5] Checking for time series updates...")
        today = datetime.now()
        if today.weekday() == 0:
            print("      → Today is Monday - updating time series data")
        else:
            print(f"      → Today is {today.strftime('%A')} - time series data unchanged")
        time_series_data = update_time_series_data()
        print(f"      ✓ Time series data ready ({len(time_series_data.get('dates', []))} data points)")
        
        # Generate HTML
        print("\n[3/5] Generating HTML dashboard...")
        html_content = generate_html(spaces_by_location, time_series_data)
        with open(DOCS_DIR / "index.html", 'w', encoding='utf-8') as f:
            f.write(html_content)
        print("      ✓ index.html created")
        
        # Generate CSS
        print("\n[4/5] Generating CSS stylesheet...")
        css_content = generate_css()
        with open(DOCS_DIR / "dashboard.css", 'w', encoding='utf-8') as f:
            f.write(css_content)
        print("      ✓ dashboard.css created")
        
        # Generate JavaScript
        print("\n[5/5] Generating JavaScript...")
        js_content = generate_js()
        with open(DOCS_DIR / "dashboard.js", 'w', encoding='utf-8') as f:
            f.write(js_content)
        print("      ✓ dashboard.js created")
        
        print("\n" + "=" * 60)
        print("Dashboard generation complete!")
        print(f"Files created in: {DOCS_DIR.absolute()}")
        print("=" * 60)
        
    except FileNotFoundError as e:
        print(f"\nERROR: {e}")
        print("Make sure the space_capacity_analysis.py script has been run first.")
        return 1
    except Exception as e:
        print(f"\nUNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
