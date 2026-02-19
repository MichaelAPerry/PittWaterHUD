# Pittsburgh Water HUD v2 🌊
**Real-time river conditions for boaters, anglers, and paddlers on the Three Rivers.**

## Deploy to Streamlit Community Cloud

### Step 1 — Your repo structure
Make sure your GitHub repo looks exactly like this:
```
your-repo/
├── app.py
├── requirements.txt
└── .streamlit/
    └── config.toml
```

### Step 2 — Push to GitHub
```bash
git init
git add .
git commit -m "Pittsburgh Water HUD v2"
git remote add origin https://github.com/YOURUSERNAME/YOURREPO.git
git push -u origin main
```

### Step 3 — Deploy on Streamlit Community Cloud
1. Go to **[share.streamlit.io](https://share.streamlit.io)**
2. Sign in with your GitHub account
3. Click **"New app"**
4. Set:
   - **Repository:** `YOURUSERNAME/YOURREPO`
   - **Branch:** `main`
   - **Main file path:** `app.py`
5. Click **"Deploy!"**

Your live URL will be: `https://YOURUSERNAME-YOURREPO-app-XXXX.streamlit.app`

Deployment takes ~2 minutes. Share the URL — it works on any phone or browser.

---

## Data Sources (all free, no API keys needed)
| Source | Data | Cache |
|--------|------|-------|
| USGS NWIS | Flow, gauge height, water temp | 5 min |
| Open-Meteo | Wind, UV, AQI, precip, sunrise/sunset | 10 min |
| NWS api.weather.gov | Active flood/weather alerts | 10 min |
| NWPS water.noaa.gov | 48-hour predicted river stage | 15 min |
| Solunar.org | Moon phase, fish feeding windows | Daily |
| WPRDC CKAN | Allegheny County water quality | 30 min |
| ALCOSAN SOAK | Sewage overflow (Apr–Oct only) | 10 min |

## USGS Gauge Sites
| River | Site | Location | Upstream Early Warning |
|-------|------|----------|------------------------|
| Monongahela | 03085000 | Braddock | Youghiogheny @ Connellsville (03075070) · ~6hr lead |
| Allegheny | 03049640 | Acmetonia | Allegheny @ Natrona (03049500) · ~2hr lead |
| Ohio | 03086000 | Sewickley | — (downstream river) |

## Local Development
```bash
pip install -r requirements.txt
streamlit run app.py
```
Then open **http://localhost:8501**
