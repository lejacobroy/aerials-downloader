from typing import List, Dict

from iterfzf import iterfzf
import json
from itertools import zip_longest
import requests
import tqdm
import urllib3
import os
import os.path
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from requests.exceptions import ChunkedEncodingError
from urllib3.exceptions import ProtocolError

# Disable warnings
urllib3.disable_warnings()

# CONSTANTS
JSON_FILE_PATH = (
    "/Library/Application Support/com.apple.idleassetsd/Customer/entries.json"
)
AERIAL_FOLDER_PATH = (
    "/Library/Application Support/com.apple.idleassetsd/Customer/4KSDR240FPS/"
)
QUERY = "UPDATE ZASSET SET ZLASTDOWNLOADED = 718364962.0204;"  # noqa ~ Ignores styling warnings


def get_aerials(path):
    """
    Get the list of aerial URLs from the aerials JSON file
    Args:
        path: Path to aerials JSON file

    Returns:

    """
    aerials_list = []
    with open(path) as f:
        d = json.load(f)
        for aerial in d["assets"]:
            aerials_list.append(aerial)
    return aerials_list


def download_aerial(url: str, file_path: str, name: str, resume_pos: int = 0):
    """
    Download an aerial from a URL
    Args:
        url: URL for the aerial
        file_path: File path to save the aerial
        name: Name of the aerial
        resume_pos: Resume the download from this position

    Returns:
        None

    """
    r = requests.head(url, verify=False)  # Send a HEAD request

    total = int(r.headers.get("content-length", 0))  # Get the total content length

    headers = dict(
        Range=f"bytes={resume_pos}-"
    )

    with requests.get(url, stream=True, headers=headers, verify=False) as r:
        r.raise_for_status()

        with open(file_path, "wb" if resume_pos == 0 else "ab") as f:
            kwargs = dict(
                desc=name,
                total=total,
                miniters=1,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                initial=resume_pos,
            )
            with tqdm.tqdm(**kwargs) as pb:
                for chunk in r.iter_content(chunk_size=32 * 1024):
                    f.write(chunk)
                    pb.update(len(chunk))


def update_sql():
    """
    Update SQL database for downloaded aerials
    Returns:
        None

    """
    con = sqlite3.connect(
        "/Library/Application Support/com.apple.idleassetsd/Aerial.sqlite"
    )
    cur = con.cursor()
    cur.execute("VACUUM;")
    cur.execute(QUERY)
    con.commit()
    con.close()


def kill_service():
    """
    Kill idleassetsd service
    Returns:
        None

    """
    # idleassetsd
    subprocess.run(["killall", "idleassetsd"])


def download_aerials_parallel(aerial, max_retry=5):
    """
    Download aerials in parallel
    Args:
        aerial: Which aerial to download
        max_retry: Maximum number of retries

    Returns:
        None

    """
    if 'url-4K-SDR-240FPS' in aerial:
        url = aerial["url-4K-SDR-240FPS"].replace('\\', '')
        file_path = AERIAL_FOLDER_PATH + aerial["id"] + '.mov'
        is_download_complete = os.path.exists(file_path)
        retry = 0
        while not is_download_complete and retry < max_retry:
            try:
                resume_pos = os.path.getsize(file_path + ".downloading") if os.path.exists(
                    file_path + ".downloading") else 0
                download_aerial(url, file_path + ".downloading", f"{aerial['accessibilityLabel']}: {aerial['id']}.mov",
                                resume_pos=resume_pos)
                os.rename(file_path + ".downloading", file_path)
                is_download_complete = True
            except ChunkedEncodingError | ProtocolError as e:
                retry += 1
                if retry >= 5:
                    print(
                        f"Error downloading {aerial['accessibilityLabel']}: {aerial['id']}.mov. "
                        f"Maximum retries reached. {repr(e)}."
                    )
            except Exception as e:
                print(f"Error downloading {aerial['accessibilityLabel']}: {aerial['id']}.mov. {repr(e)}")


def is_file_complete(file_path, url):
    """
    Check if the aerial completed downloading
    Args:
        file_path: File path to the aerial
        url: URL for the aerial

    Returns:
        None
    """
    if os.path.exists(file_path):
        local_size = os.path.getsize(file_path)
        remote_size = int(
            requests.head(url, verify=False).headers.get("content-length", 0)
        )
        return local_size == remote_size
    return False


def choose_category():
    """
    Choose a category for aerials
    Returns:
        chosen_category_obj: Chosen category object
    """
    chosen_category_obj = {}
    with open(JSON_FILE_PATH) as f:
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


def choose_subcategory(category_obj):
    """
    Choose a subcategory for a category
    Args:
        category_obj: Category object

    Returns:
        chosen_subcategory_obj: Chosen subcategory object
    """
    chosen_subcategory_obj = {}
    with open(JSON_FILE_PATH) as f:
        data = json.load(f)
        # Get subcategories
        subcategories = []
        j = 0
        # Print subcategories
        print("Select a subcategory in " + category_obj['localizedNameKey'].replace('AerialCategory', '') + ":")
        for subcat in category_obj['subcategories']:
            j = j + 1
            print(str(j) + '. ' + subcat['localizedNameKey'].replace('AerialSubcategory', ''))
            subcategories.append(subcat['localizedNameKey'])

        subcategories.append('All')
        print(str(j + 1) + '. All')

        choice = input("Enter subcategory number: ")
        chosen_subcategory = subcategories[int(choice) - 1]
        if chosen_subcategory != "All":
            chosen_subcategory_obj = {}
            for subcat in category_obj["subcategories"]:
                if subcat["localizedNameKey"] == chosen_subcategory:
                    chosen_subcategory_obj = subcat
                    break
    return chosen_subcategory_obj


def download_all_aerials(aerials):
    """
    Download all aerials
    Args:
        aerials: Aerials list

    Returns:
        None
    """
    filtered_aerials = []
    aerials_set = set()
    # format the list of all aerials urls
    for a in aerials:
        if a["id"] not in aerials_set:
            aerials_set.add(a["id"])
            filtered_aerials.append(a)
        else:
            for _ in a["categories"]:
                if a["id"] not in aerials_set:
                    aerials_set.add(a["id"])
                    filtered_aerials.append(a)
            for _ in a["subcategories"]:
                if a["id"] not in aerials_set:
                    aerials_set.add(a["id"])
                    filtered_aerials.append(a)
    start_download_of_aerials_list(filtered_aerials)


def download_filtered_aerials(aerials):
    """
    Download filtered aerials
    Args:
        aerials: Aerials list

    Returns:
        None

    """
    subcategory_obj = {}
    filtered_aerials = []
    aerials_set = set()

    category_obj = choose_category()
    if category_obj != {}:
        subcategory_obj = choose_subcategory(category_obj)

    for a in aerials:
        if category_obj == {}:
            if a["id"] not in aerials_set:
                aerials_set.add(a["id"])
                filtered_aerials.append(a)
        else:
            if subcategory_obj != {}:
                for sub in a["subcategories"]:
                    if sub == subcategory_obj["id"]:
                        if a["id"] not in aerials_set:
                            aerials_set.add(a["id"])
                            filtered_aerials.append(a)
            else:
                for cat in a["categories"]:
                    if cat == category_obj["id"]:
                        if a["id"] not in aerials_set:
                            aerials_set.add(a["id"])
                            filtered_aerials.append(a)

    def aerial_name(aerial: dict):
        """
        Create a formatted name for an aerial
        Args:
            aerial: Aerial object

        Returns:

        """
        return f"""{aerial['accessibilityLabel']} ({aerial['localizedNameKey']})"""

    # Create a generator function to yield the aerial names
    def aerial_generator():
        """
        Generator function to yield the aerial names
        Returns:

        """
        for aerial in filtered_aerials:
            yield aerial_name(aerial)

    # Use iterfzf to allow the user to filter the aerials
    selected_aerials = iterfzf(
        aerial_generator(),
        multi=True,
    )

    # Filter filteredAerials based on the user's selection
    filtered_aerials = [
        aerial for aerial in filtered_aerials if aerial_name(aerial) in selected_aerials
    ]

    start_download_of_aerials_list(filtered_aerials)


def start_download_of_aerials_list(_list: List[Dict]):
    """
    Start download of aerials list
    Args:
        _list: List[Dict]: Aerials list

    Returns:
        None

    """
    print("Downloading " + str(len(_list)) + " aerials")

    # Get the number of download threads from the environment variable
    download_threads = int(os.environ.get("DOWNLOAD_THREADS", 1))

    max_retry = 5

    with ThreadPoolExecutor(max_workers=download_threads) as executor:
        executor.map(download_aerials_parallel, _list, [max_retry] * len(_list))


def choose_aerials():
    """
    Choose specific aerials or download all aerials
    Returns:
        None
    """
    print("Select an option:")
    print("1. Choose aerials manually")
    print("2. Download all aerials")
    choice = input("Enter option number: ")

    aerials = get_aerials(JSON_FILE_PATH)

    if choice == "2":
        # Format the list of all aerials urls
        download_all_aerials(aerials)

    if choice == "1":
        download_filtered_aerials(aerials)


print("Loading Aerials list")
choose_aerials()
print("Updating Aerials Database")
update_sql()
print("Restarting service")
kill_service()
