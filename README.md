# aerials-downloader

This little python snippet allows you to download all the new macOS Aerials screensavers and wallpapers, so they are available to shuffle.

You can also select Categories and Subcategories of video to download, and download them in parallel.

### warning, if you download all the video files in 4KSDR240FPS, it will take 65 GB of space.

This project uses [uv](https://docs.astral.sh/uv/) to manage Python and dependencies.

To use:

- Install uv (if you don't have it): `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Clone the repository
- Run the script:
  - **Tahoe (macOS 26) or newer:** `uv run app.py` (**no** sudo — uv sets up the environment on first run)
  - **Legacy macOS (Sonoma–Sequoia):** `uv sync` then `sudo .venv/bin/python app.py`

> On legacy macOS the aerials are written under `/Library`, so the script needs `sudo`. Because `sudo` resets your `PATH`, run the venv's Python directly (`sudo .venv/bin/python app.py`) rather than `sudo uv run`. Run `uv sync` once beforehand to create `.venv`.

Optional: to download more than one in parallel set the environment variable DOWNLOAD_THREADS.

For example to set to five:
- Tahoe:  `DOWNLOAD_THREADS=5 uv run app.py`
- Legacy: `sudo DOWNLOAD_THREADS=5 .venv/bin/python app.py`

Note: If you're choosing aerials manually, you can select multiple aerials with tab/shift+tab.

Note (Tahoe 26+): after the download finishes, close and reopen System Settings > Wallpaper (or Screen Saver) for the newly downloaded aerials to appear.

## screenshot
![Alt text](/aerials-downloader.png?raw=true "aerials-downloader")


## contributors
- [shinz4u](https://github.com/shinz4u)
- [shawncl](https://github.com/shawncl)
- [ismael-marcos](https://github.com/ismael-marcos)
- [skywinder](https://github.com/skywinder)
- [CoreJa](https://github.com/CoreJa)
- [NightMAchinery](https://github.com/NightMachinery)
- [foxhatleo](https://github.com/foxhatleo)
