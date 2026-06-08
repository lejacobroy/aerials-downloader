from typing import List, Dict

from iterfzf import iterfzf
import json
import requests
import tqdm
import os
import os.path
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.exceptions import ChunkedEncodingError
from urllib3.exceptions import ProtocolError

# CONSTANTS
LEGACY_JSON_FILE_PATH = (
    "/Library/Application Support/com.apple.idleassetsd/Customer/entries.json"
)
LEGACY_AERIAL_FOLDER_PATH = (
    "/Library/Application Support/com.apple.idleassetsd/Customer/4KSDR240FPS/"
)
TAHOE_JSON_FILE_PATH = os.path.expanduser(
    "~/Library/Application Support/com.apple.wallpaper/aerials/manifest/entries.json"
)
TAHOE_AERIAL_FOLDER_PATH = os.path.expanduser(
    "~/Library/Application Support/com.apple.wallpaper/aerials/videos/"
)

# Tahoe (macOS 26+) moved aerials out of /Library/.../idleassetsd into ~/Library/.../wallpaper.
# Detect by presence of the legacy entries.json — it does not exist on Tahoe or newer.
IS_LEGACY = os.path.exists(LEGACY_JSON_FILE_PATH)
JSON_FILE_PATH = LEGACY_JSON_FILE_PATH if IS_LEGACY else TAHOE_JSON_FILE_PATH
AERIAL_FOLDER_PATH = LEGACY_AERIAL_FOLDER_PATH if IS_LEGACY else TAHOE_AERIAL_FOLDER_PATH

QUERY = "UPDATE ZASSET SET ZLASTDOWNLOADED = 718364962.0204;"  # noqa ~ Ignores styling warnings

# Number of bytes to request per streamed chunk.
CHUNK_SIZE = 32 * 1024
# Maximum number of attempts per aerial before giving up.
MAX_RETRY = 5


def check_permissions():
    """
    Enforce the correct invocation for the detected macOS variant.
    Legacy writes to /Library and requires sudo. Tahoe writes to ~/Library
    and must NOT use sudo (would download as root into the user's home).
    """
    is_root = os.geteuid() == 0
    if IS_LEGACY and not is_root:
        print("Legacy macOS detected: must run with sudo.")
        sys.exit(1)
    if not IS_LEGACY and is_root:
        print("Tahoe or newer detected: do NOT run with sudo.")
        sys.exit(1)


def load_manifest(path):
    """
    Load and parse the aerials manifest JSON.
    Args:
        path: Path to the aerials manifest (entries.json)

    Returns:
        The parsed manifest as a dict.
    """
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit(
            f"Could not find the aerials manifest at:\n  {path}\n"
            "Open System Settings > Wallpaper once so macOS creates it, "
            "or this macOS version may not be supported yet."
        )


def get_aerials(data):
    """
    Get the list of aerials from a parsed manifest.
    Args:
        data: Parsed manifest dict

    Returns:
        The list of aerial asset objects.
    """
    return data["assets"]


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
    total = int(requests.head(url).headers.get("content-length", 0))

    headers = {"Range": f"bytes={resume_pos}-"}

    with requests.get(url, stream=True, headers=headers) as r:
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
                for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
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


def is_file_complete(file_path, url):
    """
    Check if the aerial finished downloading by comparing the local file size
    against the remote content length.
    Args:
        file_path: File path to the aerial
        url: URL for the aerial

    Returns:
        True if the file exists locally and matches the remote size.
    """
    if not os.path.exists(file_path):
        return False
    local_size = os.path.getsize(file_path)
    remote_size = int(requests.head(url).headers.get("content-length", 0))
    return local_size == remote_size


def download_aerials_parallel(aerial, max_retry=MAX_RETRY):
    """
    Download a single aerial, resuming and retrying on network errors.
    Args:
        aerial: Which aerial to download
        max_retry: Maximum number of attempts

    Returns:
        None on success or skip, or an error string describing the failure.
    """
    if "url-4K-SDR-240FPS" not in aerial:
        return None

    url = aerial["url-4K-SDR-240FPS"].replace("\\", "")
    file_path = AERIAL_FOLDER_PATH + aerial["id"] + ".mov"
    name = f"{aerial['accessibilityLabel']}: {aerial['id']}.mov"

    # Skip only when the existing file is present AND the correct, complete size.
    if is_file_complete(file_path, url):
        return None

    downloading_path = file_path + ".downloading"
    for attempt in range(1, max_retry + 1):
        try:
            resume_pos = (
                os.path.getsize(downloading_path)
                if os.path.exists(downloading_path)
                else 0
            )
            download_aerial(url, downloading_path, name, resume_pos=resume_pos)
            os.rename(downloading_path, file_path)
            return None
        except (ChunkedEncodingError, ProtocolError) as e:
            # Transient network error — loop to resume from where we stopped.
            if attempt >= max_retry:
                return f"{name}: maximum retries reached ({attempt}). {e!r}"
        except Exception as e:
            # Non-recoverable error (HTTP error, disk, etc.) — do not retry.
            return f"{name}: {e!r}"
    return None


def choose_category(data):
    """
    Choose a category for aerials
    Args:
        data: Parsed manifest dict

    Returns:
        chosen_category_obj: Chosen category object, or {} for "All"
    """
    print("Select aerial category:")

    categories = []
    for i, category in enumerate(data["categories"], start=1):
        print(f"{i}. " + category["localizedNameKey"].replace("AerialCategory", ""))
        categories.append(category["localizedNameKey"])

    categories.append("All")
    print(f"{len(categories)}. All")

    chosen_category = categories[prompt_index("Enter category number: ", len(categories))]
    if chosen_category == "All":
        return {}
    for category in data["categories"]:
        if category["localizedNameKey"] == chosen_category:
            return category
    return {}


def choose_subcategory(category_obj):
    """
    Choose a subcategory for a category
    Args:
        category_obj: Category object

    Returns:
        chosen_subcategory_obj: Chosen subcategory object, or {} for "All"
    """
    print(
        "Select a subcategory in "
        + category_obj["localizedNameKey"].replace("AerialCategory", "")
        + ":"
    )

    subcategories = []
    for j, subcat in enumerate(category_obj["subcategories"], start=1):
        print(f"{j}. " + subcat["localizedNameKey"].replace("AerialSubcategory", ""))
        subcategories.append(subcat["localizedNameKey"])

    subcategories.append("All")
    print(f"{len(subcategories)}. All")

    chosen = subcategories[prompt_index("Enter subcategory number: ", len(subcategories))]
    if chosen == "All":
        return {}
    for subcat in category_obj["subcategories"]:
        if subcat["localizedNameKey"] == chosen:
            return subcat
    return {}


def prompt_index(prompt, count):
    """
    Prompt repeatedly until the user enters a valid 1..count integer.
    Args:
        prompt: Text shown at the input prompt
        count: Number of valid options

    Returns:
        The chosen index, zero-based.
    """
    while True:
        choice = input(prompt)
        try:
            idx = int(choice) - 1
        except ValueError:
            print("Please enter a number.")
            continue
        if 0 <= idx < count:
            return idx
        print(f"Please enter a number between 1 and {count}.")


def dedupe_by_id(aerials):
    """
    Remove duplicate aerials, keeping the first occurrence of each id.
    Args:
        aerials: Aerials list

    Returns:
        A new list with duplicate ids removed.
    """
    seen = set()
    unique = []
    for a in aerials:
        if a["id"] not in seen:
            seen.add(a["id"])
            unique.append(a)
    return unique


def download_all_aerials(aerials):
    """
    Download all aerials
    Args:
        aerials: Aerials list

    Returns:
        None
    """
    start_download_of_aerials_list(dedupe_by_id(aerials))


def download_filtered_aerials(aerials, data):
    """
    Download a user-selected subset of aerials
    Args:
        aerials: Aerials list
        data: Parsed manifest dict

    Returns:
        None

    """
    category_obj = choose_category(data)
    subcategory_obj = choose_subcategory(category_obj) if category_obj else {}

    filtered_aerials = []
    for a in dedupe_by_id(aerials):
        if not category_obj:
            filtered_aerials.append(a)
        elif subcategory_obj:
            if subcategory_obj["id"] in a["subcategories"]:
                filtered_aerials.append(a)
        elif category_obj["id"] in a["categories"]:
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

    if not selected_aerials:
        print("No aerials selected.")
        return

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

    # Ensure the destination folder exists (it may be absent on a fresh install
    # where the user has not yet opened Wallpaper settings).
    os.makedirs(AERIAL_FOLDER_PATH, exist_ok=True)

    # Get the number of download threads from the environment variable
    download_threads = int(os.environ.get("DOWNLOAD_THREADS", 1))

    errors = []
    with ThreadPoolExecutor(max_workers=download_threads) as executor:
        futures = [
            executor.submit(download_aerials_parallel, aerial, MAX_RETRY)
            for aerial in _list
        ]
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as e:  # pragma: no cover - unexpected escape
                result = repr(e)
            if result:
                errors.append(result)

    if errors:
        print(f"\n{len(errors)} download(s) failed:")
        for err in errors:
            print(f"  - {err}")


def choose_aerials(data):
    """
    Choose specific aerials or download all aerials
    Args:
        data: Parsed manifest dict

    Returns:
        None
    """
    print("Select an option:")
    print("1. Choose aerials manually")
    print("2. Download all aerials")
    choice = input("Enter option number: ")

    aerials = get_aerials(data)

    if choice == "2":
        download_all_aerials(aerials)
    elif choice == "1":
        download_filtered_aerials(aerials, data)
    else:
        print("Unknown option.")


def main():
    """Entry point: load the manifest, prompt, download, then refresh macOS."""
    check_permissions()
    print(f"Loading Aerials list{' (pre-Tahoe)' if IS_LEGACY else ''}")
    data = load_manifest(JSON_FILE_PATH)
    choose_aerials(data)
    if IS_LEGACY:
        print("Updating Aerials Database")
        update_sql()
        print("Restarting service")
        kill_service()
    else:
        print(
            "Done. On Tahoe, close and reopen System Settings > Wallpaper "
            "(or Screen Saver) for the new aerials to appear."
        )


if __name__ == "__main__":
    main()
