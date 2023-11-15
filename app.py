import json
import requests
import tqdm
import urllib3
import os.path
import sqlite3
import subprocess
urllib3.disable_warnings()

json_file_path='/Library/Application Support/com.apple.idleassetsd/Customer/entries.json'
aerial_folder_path='/Library/Application Support/com.apple.idleassetsd/Customer/4KSDR240FPS/'

def getAerials(path):
    aerialsList = [{}]
    with open(path) as f:
        d = json.load(f)
        for aerial in d["assets"]:
            aerialsList.append(aerial)
    return aerialsList


def downloadAerial(url: str, file_path: str, name:str):
    with open(file_path, 'wb') as f:
        with requests.get(url, stream=True,verify=False) as r:
            r.raise_for_status()
            total = int(r.headers.get('content-length', 0))

            # tqdm has many interesting parameters. Feel free to experiment!
            tqdm_params = {
                'desc': name,
                'total': total,
                'miniters': 1,
                'unit': 'B',
                'unit_scale': True,
                'unit_divisor': 1024,
            }
            with tqdm.tqdm(**tqdm_params) as pb:
                for chunk in r.iter_content(chunk_size=8192):
                    pb.update(len(chunk))
                    f.write(chunk)


def updateSQL():
    con = sqlite3.connect("/Library/Application Support/com.apple.idleassetsd/Aerial.sqlite")
    cur = con.cursor()
    cur.execute("VACUUM;")
    cur.execute("UPDATE ZASSET SET ZLASTDOWNLOADED = 718364962.0204;")
    con.commit()
    con.close()

def killService():
    #idleassetsd
    subprocess.run(["killall", "idleassetsd"]) 

def downloadAerials(selected_aerials):
    for aerial in selected_aerials:
        if 'url-4K-SDR-240FPS' in aerial:
            # aerial has URL
            url = aerial["url-4K-SDR-240FPS"].replace('\\','')
            # check if file exists
            file_path = aerial_folder_path+aerial["id"]+'.mov'
            if not os.path.exists(file_path):
                print("Start download of "+aerial["accessibilityLabel"])
                # save to folder with id 
                downloadAerial(url, file_path, aerial["accessibilityLabel"])

def user_selected_category_interface():
    options = ["landscapes", "cities", "underwater", "space", "comp", "all"]
    input_message = "Select screen saver Category from the options: \n"
    user_input = ''
    for index, item in enumerate(options):
        input_message += f'{index+1}) {item}\n'

    input_message += 'Selecting "All" will take up 65GB of space\n comp is miscellaneous \n Your choice: '

    while user_input not in options:
        print("***********************************************************************")
        print("Please write the name of the category you want to download as given in the options")
        print("***********************************************************************")
        user_input = input(input_message)
    return user_input

def get_selected_aerial_list(json_file_path, selected_category):
    aerials = getAerials(json_file_path)
    selected_aerials = []

    if selected_category.lower() == 'all':
        return aerials
    else:
        for aerial in aerials:
            if 'previewImage' in aerial:
                last_part = aerial['previewImage'].split("/")[-1]
                word = last_part.split("_")[0]
                if word:
                    if word.lower() == selected_category.lower():
                        selected_aerials.append(aerial)
    return selected_aerials

print("Select Your Aerial List")
selected_category = user_selected_category_interface()
print("Filtering Aerials")
selected_ariels = get_selected_aerial_list(json_file_path, selected_category)
print("Downloading Aerials")
downloadAerials(selected_ariels)
print("Updating Aerials Database")
updateSQL()
print("Restarting service")
killService()