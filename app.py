from iterfzf import iterfzf
import json
import requests
import tqdm
import urllib3
import os
import os.path
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor

urllib3.disable_warnings()

try:
    #: used for printing diagnostic messages
    from icecream import ic, colorize as ic_colorize

    ic.configureOutput(outputFunction=lambda s: print(ic_colorize(s)))
except ImportError:
    #: Graceful fallback if Icecream isn't installed.
    ic = lambda *a: None if not a else (a[0] if len(a) == 1 else a)

json_file_path = (
    "/Library/Application Support/com.apple.idleassetsd/Customer/entries.json"
)
aerial_folder_path = (
    "/Library/Application Support/com.apple.idleassetsd/Customer/4KSDR240FPS/"
)


def getAerials(path):
    aerialsList = []
    with open(path) as f:
        d = json.load(f)
        for aerial in d["assets"]:
            aerialsList.append(aerial)
    return aerialsList


def updateSQL():
    con = sqlite3.connect(
        "/Library/Application Support/com.apple.idleassetsd/Aerial.sqlite"
    )
    cur = con.cursor()
    cur.execute("VACUUM;")
    cur.execute("UPDATE ZASSET SET ZLASTDOWNLOADED = 718364962.0204;")
    con.commit()
    con.close()


def killService():
    # idleassetsd
    subprocess.run(["killall", "idleassetsd"])


def downloadAerialsParallel(aerial):
    if "url-4K-SDR-240FPS" in aerial:
        url = aerial["url-4K-SDR-240FPS"].replace("\\", "")
        file_path = aerial_folder_path + aerial["id"] + ".mov"
        if not os.path.exists(file_path) or not isFileComplete(file_path, url):
            print("Downloading " + aerial["accessibilityLabel"])
            downloadAerial(url, file_path, aerial["accessibilityLabel"])


def isFileComplete(file_path, url):
    if os.path.exists(file_path):
        local_size = os.path.getsize(file_path)
        remote_size = int(
            requests.head(url, verify=False).headers.get("content-length", 0)
        )
        return local_size == remote_size
    return False


def downloadAerial(url: str, file_path: str, name: str):
    resume_byte_position = 0
    if os.path.exists(file_path):
        resume_byte_position = os.path.getsize(file_path)

    with open(file_path, "ab") as f:
        with requests.get(
            url,
            stream=True,
            verify=False,
            headers={"Range": f"bytes={resume_byte_position}-"},
        ) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0)) + resume_byte_position

            # tqdm has many interesting parameters. Feel free to experiment!
            tqdm_params = {
                "desc": name,
                "total": total,
                "miniters": 1,
                "unit": "B",
                "unit_scale": True,
                "unit_divisor": 1024,
                "initial": resume_byte_position,
            }
            with tqdm.tqdm(**tqdm_params) as pb:
                for chunk in r.iter_content(chunk_size=8192):
                    pb.update(len(chunk))
                    f.write(chunk)


def chooseCategory():
    chosen_category_obj = {}
    with open(json_file_path) as f:
        data = json.load(f)

        # Display a choice of aerials categories
        print("Select aerial category:")

        categories = []
        i = 0
        for category in data["categories"]:
            i = i + 1
            print(
                str(i)
                + ". "
                + category["localizedNameKey"].replace("AerialCategory", "")
            )
            categories.append(category["localizedNameKey"])

        categories.append("All")
        print(str(i + 1) + ". All")

        choice = input("Enter category number: ")
        chosen_category = categories[int(choice) - 1]
        if chosen_category != "All":
            chosen_category_obj = {}
            for category in data["categories"]:
                if category["localizedNameKey"] == chosen_category:
                    chosen_category_obj = category
                    break
    return chosen_category_obj


def chooseSubcategory(categoryObj):
    chosen_subcategory_obj = {}
    with open(json_file_path) as f:
        data = json.load(f)
        # Get subcategories
        subcategories = []
        j = 0
        # Print subcategories
        print(
            "Select a subcategory in "
            + categoryObj["localizedNameKey"].replace("AerialCategory", "")
            + ":"
        )
        for subcat in categoryObj["subcategories"]:
            j = j + 1
            print(
                str(j)
                + ". "
                + subcat["localizedNameKey"].replace("AerialSubcategory", "")
            )
            subcategories.append(subcat["localizedNameKey"])

        subcategories.append("All")
        print(str(j + 1) + ". All")

        choice = input("Enter subcategory number: ")
        chosen_subcategory = subcategories[int(choice) - 1]
        if chosen_subcategory != "All":
            chosen_subcategory_obj = {}
            for subcat in categoryObj["subcategories"]:
                if subcat["localizedNameKey"] == chosen_subcategory:
                    chosen_subcategory_obj = subcat
                    break
    return chosen_subcategory_obj

def chooseAerials():
    categoryObj = {}
    subcategoryObj = {}

    print("Select an option:")
    print("1. Choose aerials manually")
    print("2. Download all aerials")
    choice = input("Enter option number: ")

    if choice == "1":
        categoryObj = chooseCategory()
        if categoryObj != {}:
            subcategoryObj = chooseSubcategory(categoryObj)

    aerials = getAerials(json_file_path)

    filteredAerials = []
    aerials_set = set()
    for a in aerials:
        if categoryObj == {}:
            if a["id"] not in aerials_set:
                aerials_set.add(a["id"])
                filteredAerials.append(a)
        else:
            for cat in a["categories"]:
                if cat == categoryObj["id"]:
                    if a["id"] not in aerials_set:
                        aerials_set.add(a["id"])
                        filteredAerials.append(a)
            if subcategoryObj != {}:
                for sub in a["subcategories"]:
                    if sub == subcategoryObj["id"]:
                        if a["id"] not in aerials_set:
                            aerials_set.add(a["id"])
                            filteredAerials.append(a)

    if choice == "1":
        ic(filteredAerials[0])

        def aerial_name(aerial):
            return f"""{aerial['accessibilityLabel']} ({aerial['localizedNameKey']})"""

        # Create a generator function to yield the aerial names
        def aerial_generator():
            for aerial in filteredAerials:
                yield aerial_name(aerial)

        # Use iterfzf to allow the user to filter the aerials
        selected_aerials = iterfzf(
            aerial_generator(),
            multi=True,
        )

        # Filter filteredAerials based on the user's selection
        filteredAerials = [
            aerial for aerial in filteredAerials if aerial_name(aerial) in selected_aerials
        ]

    print("Downloading " + str(len(filteredAerials)) + " aerials")

    # Get the number of download threads from the environment variable
    download_threads = int(os.environ.get("DOWNLOAD_THREADS", 1))

    with ThreadPoolExecutor(max_workers=download_threads) as executor:
        executor.map(downloadAerialsParallel, filteredAerials)


print("Loading Aerials list")
chooseAerials()
print("Updating Aerials Database")
updateSQL()
print("Restarting service")
killService()