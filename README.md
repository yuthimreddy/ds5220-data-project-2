## Weather Tracker — Charlottesville, VA

### Data Source
This pipeline uses the [Open-Meteo API](https://open-meteo.com/), a free, weather API which requires no access key while providing realtime meteorological data for 
any latitude/longitude. Data is collected for Charlottesville, VA 
(38.0293°N, 78.4767°W) including hourly temperature (°F) and precipitation (inches).

### Scheduled Process
A containerized Python application runs as a Kubernetes CronJob every hour on 
an EC2-hosted K3S cluster. On each run the application fetches the current 
weather conditions from Open-Meteo, writes a new record to a DynamoDB table 
(`weather-tracking`), reads the full history back, regenerates a plot, and 
overwrites `plot.png` and `data.csv` on a public S3 static website bucket.

### Output Data and Plot
- `data.csv` — full historical record of every hourly reading including 
  timestamp, temperature, and precipitation
- `plot.png` — two-panel time series chart showing (1) hourly temperature 
  over time with a 24-hour rolling average overlay, and (2) daily high/low 
  temperature range. The plot updates automatically every hour.
