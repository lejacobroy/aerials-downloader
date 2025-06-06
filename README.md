# aerials-downloader

This little python snippet allows you to download all the new MacOS Sonoma Aerials screensavers and wallpapers, so they are available to shuffle.

You can also select Categories and Subcategories of video to download, and download them in parallel.

### warning, if you download all the video files in 4KSDR240FPS, it will take 65 GB of space.

To use:

- Clone the repository
- `pip3 install -r requirements.txt`
- `sudo python3 app.py`

Optional: to download more than one in parallel update the environment variable DOWNLOAD_THREADS.

For example to set to five: `sudo -E DOWNLOAD_THREADS=5 python3 app.py`

Note: If you're choosing aerials manually, you can select multiple aerials with tab/shift+tab.

## screenshot
![Alt text](/aerials-downloader.png?raw=true "aerials-downloader")


## contributors
- [shinz4u](https://github.com/shinz4u)
- [shawncl](https://github.com/shawncl)
- [ismael-marcos](https://github.com/ismael-marcos)
- [skywinder](https://github.com/skywinder)
- [CoreJa](https://github.com/CoreJa)
- [NightMAchinery](https://github.com/NightMachinery)
