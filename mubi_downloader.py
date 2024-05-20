import requests
import json
import os
import re
import base64
import shutil
from configparser import ConfigParser

# Create or load existing configuration
config = ConfigParser()
config_file = 'config.ini'

def load_or_create_config():
    if not os.path.exists(config_file):
        config['DEFAULT'] = {
            'Authorization': 'Bearer ADD_HERE',  # Prompt user to replace ADD_HERE
            'FolderPath': '/path/to/download',  # Prompt user to replace /path/to/download
        }
        with open(config_file, 'w') as f:
            config.write(f)
    config.read(config_file)

def get_user_input(prompt, key):
    """Prompt user to replace default or incorrect settings."""
    default_value = 'ADD_HERE' if 'Authorization' in key else '/path/to/download'
    if config['DEFAULT'][key].endswith(default_value):
        value = input(prompt)
        config.set('DEFAULT', key, value)
        with open(config_file, 'w') as f:
            config.write(f)
        return value
    return config['DEFAULT'][key]

def initialize_headers():
    """Initialize headers with values from the config file."""
    return {
        'authority': 'api.mubi.com',
        'accept': '*/*',
        'accept-language': 'en',
        'authorization': 'Bearer ' + config['DEFAULT']['Authorization'],
        'client': 'web',
        'client-accept-audio-codecs': 'aac',
        'client-accept-video-codecs': 'h265,vp9,h264',
        'client-country': 'US',
        'dnt': '1',
        'origin': 'https://mubi.com',
        'referer': 'https://mubi.com/',
        'sec-ch-ua': '"Google Chrome";v="111", "Not(A:Brand";v="8", "Chromium";v="111"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36',
    }

def main():
    load_or_create_config()

    auth_token = get_user_input('Enter Authorization Bearer token: ', 'Authorization')
    headers = initialize_headers()
    
    folder_path = get_user_input('Enter the folder path for downloads: ', 'FolderPath')
    
    mubi_id = input('Enter MUBI movie ID: ')
    custom_data = input('dt-custom-data: ')
    response = requests.get(f'https://api.mubi.com/v3/films/{mubi_id}/viewing/secure_url', headers=headers)
    mubi = json.loads(response.text)
    url = mubi['url']
    def get_valid_filename(title):
        invalid_chars = '<>:"/\|?*'
        title = ''.join('_' if c in invalid_chars else c for c in title)

        while True:
            response = input(f"Is this an appropriate filename? '{title}' [Y/N]: ").strip().upper()
            if response == 'Y':
                return title
            elif response == 'N':
                return input('Enter final file name: ').strip()
            else:
                print("Please enter 'Y' for yes or 'N' for no.")

    title = mubi['mux']['video_title']
    name = get_valid_filename(title)
    kid = requests.get(url)
    result = re.search(r'cenc:default_KID="(\w{8}-(?:\w{4}-){3}\w{12})">', str(kid.text))
    def get_pssh(keyId):
        array_of_bytes = bytearray(b'\x00\x00\x002pssh\x00\x00\x00\x00')
        array_of_bytes.extend(bytes.fromhex("edef8ba979d64acea3c827dcd51d21ed"))
        array_of_bytes.extend(b'\x00\x00\x00\x12\x12\x10')
        array_of_bytes.extend(bytes.fromhex(keyId.replace("-", "")))
        return base64.b64encode(bytes.fromhex(array_of_bytes.hex()))

    kid = result.group(1).replace('-', '')
    assert len(kid) == 32 and not isinstance(kid, bytes), "wrong KID length"
    pssh = format(get_pssh(kid).decode('utf-8'))

    json_data = {
        'license': 'https://lic.drmtoday.com/license-proxy-widevine/cenc/?specConform=true',
        'headers': f'Dt-Custom-Data: {custom_data}',
        'pssh': pssh,                                                
        'buildInfo': '',                                                 
        'proxy': '',                                                      
        'cache': False,                                                    
    }

    decrypt_response = requests.post('https://cdrm-project.com/wv', headers=headers, json=json_data)
    decryption_key = re.search(r"[a-z0-9]{16,}:[a-z0-9]{16,}", decrypt_response.text).group()
    decryption_key_formatted = f'key_id={decryption_key.replace(":", ":key=")}'
    
    # Proceed with downloading and decryption process
    os.system(f'N_m3u8DL-RE "{url}" --auto-select --save-name "{name}" --auto-select --save-dir "{folder_path}" -mt --tmp-dir "{folder_path}/temp"')
    decrypted_video_path = f"{folder_path}/{name}/decrypted-video.mp4"
    os.system(f'shaka-packager in="{folder_path}/{name}.mp4",stream=video,output="{decrypted_video_path}" --enable_raw_key_decryption --keys {decryption_key_formatted}')
    regex_pattern = re.escape(name) + r"\.[a-z]{2,}\.m4a"
    for filename in os.listdir(folder_path):
        if re.match(regex_pattern, filename):
            letters = re.search(re.escape(name) + r"\.([a-zA-Z]{2,})\.m4a", filename).group(1)
            audio_file_path = os.path.join(folder_path, filename)
            decrypted_audio_path = f"{folder_path}/{name}/decrypted-audio.{letters}.m4a"
            os.system(f'shaka-packager in="{audio_file_path}",stream=audio,output="{decrypted_audio_path}" --enable_raw_key_decryption --keys {decryption_key_formatted}')
            os.remove(audio_file_path)
    
    # Move subtitle files
    for filename in os.listdir(folder_path):
        if filename.endswith(".srt") and name in filename:
            source_path = os.path.join(folder_path, filename)
            dest_path = os.path.join(folder_path, name, filename)
            shutil.move(source_path, dest_path)
    
    # Clean up and decryption status
    os.remove(f"{folder_path}/{name}.mp4")
    print(f"Decryption complete. Files saved to {folder_path}/{name}")

    # Add audio to the video
    dic_audio = {}
    for filename in os.listdir(f"{folder_path}/{name}"):
        if filename.endswith(".m4a"):
            aux = filename.split(".")
            language = aux[len(aux) - 2]
            dic_audio[language] = filename
    command = f'ffmpeg -i "{decrypted_video_path}"'
    for index, (language, filename) in enumerate(dic_audio.items()):
        command += f' -i "{folder_path}/{name}/{filename}"'
    command += ' -map 0:v'
    for index in range(len(dic_audio)):
        command += f' -map {index + 1}:a'
    command += ' -c copy'
    for index, language in enumerate(dic_audio.keys()):
        command += f' -metadata:s:a:{index} language={language}'
        command += f' -metadata:s:a:{index} title="{language.upper()}"'
    command += f' "{folder_path}/{name}/{name}.mp4"'
    os.system(command)

    # Remove decrypted audio and video files
    for filename in os.listdir(f"{folder_path}/{name}"):
        if filename.startswith("decrypted-"):
            os.remove(os.path.join(folder_path, name, filename))

    # Add subtitles to the video
    dic_subtitles = {}
    for filename in os.listdir(f"{folder_path}/{name}"):
        if filename.endswith(".srt"):
            aux = filename.split(".")
            language = aux[len(aux) - 2]
            dic_subtitles[language] = filename
    command = f'ffmpeg -i "{folder_path}/{name}/{name}.mp4"'
    for index, (language, filename) in enumerate(dic_subtitles.items()):
        command += f' -i "{folder_path}/{name}/{filename}"'
    command += ' -map 0'
    for index in range(len(dic_subtitles)):
        command += f' -map {index + 1}'
    command += ' -c copy -c:s mov_text'
    for index, language in enumerate(dic_subtitles.keys()):
        command += f' -metadata:s:s:{index} language={language}'
        command += f' -metadata:s:s:{index} title="{language.upper()}"'
    command += f' "{folder_path}/{name}/{name}_subtitles.mp4"'
    os.system(command)

    # Rename final video file
    os.remove(f"{folder_path}/{name}/{name}.mp4")
    os.rename(f"{folder_path}/{name}/{name}_subtitles.mp4", f"{folder_path}/{name}/{name}.mp4")
    
    # Clean up subtitle files
    for filename in os.listdir(f"{folder_path}/{name}"):
        if filename.endswith(".srt"):
            os.remove(os.path.join(folder_path, name, filename))

    print(f"Final video file saved to {folder_path}/{name}")

if __name__ == "__main__":
    main()
