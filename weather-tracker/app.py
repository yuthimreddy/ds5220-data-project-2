import os
import boto3
import requests
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from datetime import datetime, timezone
from decimal import Decimal

# --- Config ---
LOCATION = "Charlottesville, VA"
LATITUDE = 38.0293
LONGITUDE = -78.4767
S3_BUCKET = os.environ["S3_BUCKET"]
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
TABLE_NAME = "weather-tracking"

# Open-Meteo API — no key required
API_URL = (
    f"https://api.open-meteo.com/v1/forecast"
    f"?latitude={LATITUDE}&longitude={LONGITUDE}"
    f"&current=temperature_2m,precipitation,rain,showers,snowfall"
    f"&temperature_unit=fahrenheit"
    f"&precipitation_unit=inch"
    f"&timezone=America%2FNew_York"
)

# --- AWS clients ---
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(TABLE_NAME)
s3 = boto3.client("s3", region_name=AWS_REGION)


def fetch_weather():
    resp = requests.get(API_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    current = data["current"]
    return {
        "temperature_f": current["temperature_2m"],
        "precipitation_in": current["precipitation"],
        "rain_in": current["rain"],
        "snowfall_in": current["snowfall"],
    }


def write_to_dynamo(weather: dict):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    item = {
        "location_id": LOCATION,
        "timestamp": timestamp,
        "temperature_f": Decimal(str(weather["temperature_f"])),
        "precipitation_in": Decimal(str(weather["precipitation_in"])),
        "rain_in": Decimal(str(weather["rain_in"])),
        "snowfall_in": Decimal(str(weather["snowfall_in"])),
    }
    table.put_item(Item=item)
    return timestamp


def fetch_history():
    resp = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("location_id").eq(LOCATION),
        ScanIndexForward=True,
    )
    items = resp["Items"]
    # Handle DynamoDB pagination
    while "LastEvaluatedKey" in resp:
        resp = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("location_id").eq(LOCATION),
            ScanIndexForward=True,
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        items.extend(resp["Items"])
    return items


def save_csv(items):
    df = pd.DataFrame(items)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")
    for col in ["temperature_f", "precipitation_in", "rain_in", "snowfall_in"]:
        df[col] = df[col].astype(float)
    csv_path = "/tmp/data.csv"
    df.to_csv(csv_path, index=False)
    s3.upload_file(
        csv_path, S3_BUCKET, "data.csv",
        ExtraArgs={"ContentType": "text/csv"},
    )

    print(f"Uploaded data.csv ({len(df)} rows)")
    return df


def make_plot(df):
    sns.set_theme(style="darkgrid")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    fig.suptitle(f"Weather Tracker — {LOCATION}", fontsize=15, fontweight="bold", y=0.98)

    # Temperature
    ax1.plot(df["timestamp"], df["temperature_f"], color="#e07b39", linewidth=2, marker="o", markersize=3)
    ax1.fill_between(df["timestamp"], df["temperature_f"], alpha=0.15, color="#e07b39")
    ax1.set_ylabel("Temperature (°F)", fontsize=11)
    ax1.set_title("Temperature Over Time", fontsize=12)

    # Precipitation
    ax2.bar(df["timestamp"], df["precipitation_in"], width=0.01, color="#4a90d9", alpha=0.8, label="Precipitation (in)")
    ax2.set_ylabel("Precipitation (in)", fontsize=11)
    ax2.set_title("Hourly Precipitation", fontsize=12)
    ax2.set_xlabel("Time (ET)", fontsize=11)

    # Format x-axis
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d\n%H:%M"))
    ax2.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=30)

    # Annotation: latest reading
    latest = df.iloc[-1]
    ax1.annotate(
        f"Latest: {latest['temperature_f']:.1f}°F",
        xy=(latest["timestamp"], latest["temperature_f"]),
        xytext=(10, 10), textcoords="offset points",
        fontsize=9, color="#e07b39",
        arrowprops=dict(arrowstyle="->", color="#e07b39"),
    )

    n = len(df)
    fig.text(
        0.99, 0.01,
        f"Data points: {n} | Last updated: {latest['timestamp'].strftime('%Y-%m-%d %H:%M ET')}",
        ha="right", va="bottom", fontsize=8, color="gray",
    )

    plt.tight_layout()
    plot_path = "/tmp/plot.png"
    plt.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close()

    s3.upload_file(
        plot_path, S3_BUCKET, "plot.png",
        ExtraArgs={"ContentType": "image/png"},
    )
    
    print(f"Uploaded plot.png")


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Fetching weather for {LOCATION}...")
    weather = fetch_weather()
    timestamp = write_to_dynamo(weather)

    print(
        f"WEATHER | temp={weather['temperature_f']}°F | "
        f"precip={weather['precipitation_in']}in | "
        f"rain={weather['rain_in']}in | "
        f"snow={weather['snowfall_in']}in | "
        f"ts={timestamp}"
    )

    items = fetch_history()
    df = save_csv(items)
    make_plot(df)
    print("Done.")


if __name__ == "__main__":
    main()

