import asyncio
import os
import pickle
import shlex
import subprocess
from multiprocessing import Manager, Pool, Queue
from typing import *

from pytube import YouTube
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tqdm.auto import tqdm

from chrome_driver_manager import ChromeDriverManager


def get_all_files(path, prefix="", suffix="", contains=("",), excludes=("",)):
    if not os.path.isdir(path):
        raise ValueError(f"{path} is not a valid directory.")
    files = []
    for pre, dirs, basenames in os.walk(path):
        for name in basenames:
            if name.startswith(prefix) and name.endswith(suffix) and any([c in name for c in contains]):
                if excludes == ("",):
                    files.append(os.path.join(pre, name))
                else:
                    if all([e not in name for e in excludes]):
                        files.append(os.path.join(pre, name))
    return files


async def check_if_page_loaded(driver, prev_url):
    while driver.current_url == prev_url:
        pass


open_proc = lambda cmd_list: subprocess.Popen(
    cmd_list, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1
)

url = "https://www.youtube.com"
max_num_videos = 10
max_num_proc = 10
search_string = "celebrity documentaries"
search_bar_xpath = "//input[@id='search']"
filter_btn_xpath = "//tp-yt-paper-button[@aria-label='Search filters']"
thumbnail_xpath = """
//div[@id='contents' and @class='style-scope ytd-section-list-renderer']
//a[@id='thumbnail' and ./yt-img-shadow/img[contains(@src, 'jpg')]]
""".strip()
download_folder = "./downloads"


async def get_video_urls() -> Set:
    video_urls = set()
    print("[INFO ]:\t\tSetting up the chrome headless driver..")
    cdm = ChromeDriverManager(headless=True)
    try:
        print(f"[INFO ]:\t\tOpening {url}..")
        cdm.open_url(url)

        try:
            element_present = EC.presence_of_element_located((By.XPATH, search_bar_xpath))
            WebDriverWait(cdm.driver, 5.0).until(element_present)
        except TimeoutException:
            print("[ERROR]:\t\tTimed out waiting for page to load search bar")

        print(f"[INFO ]:\t\tInput search string: {search_string}..")
        search_bar = cdm.driver.find_element(By.XPATH, search_bar_xpath)
        search_bar.send_keys(search_string)
        await asyncio.sleep(2)
        search_bar.send_keys(Keys.RETURN)

        print(f"[INFO ]:\t\tWaiting for search results to appear..")
        await asyncio.wait_for(check_if_page_loaded(cdm.driver, url), timeout=20.0)

        try:
            element_present = EC.presence_of_element_located((By.XPATH, filter_btn_xpath))
            WebDriverWait(cdm.driver, 5.0).until(element_present)
        except TimeoutException:
            print("[ERROR]:\t\tTimed out waiting for page to load filter button")

        print(f"[INFO ]:\t\tProcessing result page..")
        last_thumbnail_loc = 0
        pbar = tqdm(total=None)
        while len(video_urls) < max_num_videos:
            thumbnails = cdm.driver.find_elements(By.XPATH, thumbnail_xpath)
            if thumbnails[-1].location["y"] > last_thumbnail_loc:
                # print(len(video_urls), last_thumbnail_loc, thumbnails[-1].location["y"])
                for t in thumbnails:
                    video_url: str = t.get_attribute("href")
                    if video_url.find("list") < 0 and video_url.startswith("https://www.youtube.com"):
                        video_urls.add(video_url)
                        pbar.set_description(f"Processing {len(video_urls)}/{max_num_videos}")
                        pbar.update()
                last_thumbnail_loc = thumbnails[-1].location["y"]

            cdm.driver.execute_script(f"window.scrollBy(0, 1000)", "")
            await asyncio.sleep(2.0)  # wait for page to load
        pbar.close()

        cdm.close_driver()
    except Exception as e:
        print(e)
        if cdm.driver.session_id:
            cdm.close_driver()
    finally:
        return video_urls


def on_complete_download(_, file_path: str):
    print(f"[FINISHED]:\t\tFinished downloading {file_path}")


def download_video(url: str, queue: Queue):
    try:
        yt = YouTube(url, on_complete_callback=on_complete_download)
        mp4files = yt.streams.filter(file_extension="mp4", res="1080p")
        if len(mp4files) > 0:
            yt_stream = mp4files[-1]
            default_path = f"{download_folder}/{yt_stream.default_filename}"
            filesize_in_stream = yt_stream.filesize
            filesize_on_disk = os.path.getsize(default_path) if os.path.exists(default_path) else -1
            queue.put(
                {
                    url: {
                        "title": yt.title,
                        "author": yt.author,
                        "desc": yt.description,
                        "size": filesize_in_stream,
                        "path": default_path,
                    }
                }
            )
            print(
                f"[INFO ]:\t\t{yt.title}, {filesize_in_stream}, {filesize_on_disk}, {filesize_in_stream == filesize_on_disk}"
            )
            if filesize_in_stream != filesize_on_disk:
                print(f"[INFO ]:\t\tDownloading...{yt.title} ({url})")
                yt_stream.download(output_path=download_folder, max_retries=100, timeout=300)
            else:
                print(f"[INFO ]:\t\t{yt.title} has already been downloaded.")
        else:
            print(f"[ERROR]:\t\tNo 1080p resolution or mp4 stream doesn't exist for {url}.")
    except Exception as e:
        print(f"[ERROR]:\t\tFile {yt.title} ({url}) has failed with {repr(e)}")


metadata = []


def metadata_write_listener(queue: Queue):
    global metadata
    while True:
        data = queue.get()
        if data == "kill":
            break
        metadata.append(data)


def re_encode_as_h264(path: str):
    dir, fname = os.path.split(path)
    basename, ext = os.path.splitext(fname)

    get_codec = subprocess.run(
        shlex.split(
            f"ffprobe -v error -select_streams v:0 "
            + f"-show_entries stream=codec_name -of default=noprint_wrappers=1:nokey=1 "
            + f'"{path}"'
        ),
        stdout=subprocess.PIPE,
    )
    codec_name = str(get_codec.stdout.decode("utf-8"))
    if codec_name != "h264":
        new_file_path = f"{dir}/{basename}_h264.mp4"
        print(f"Converting {path}({codec_name}) -> {new_file_path}(h264)...")
        subprocess.run(
            shlex.split(
                f"ffmpeg "
                + "-hwaccel cuda "
                + "-hwaccel_device 1 "
                + f'-i "{path}" '
                + "-c:v h264_nvenc "
                + "-b:v 3000k "
                + "-preset medium "
                + "-crf 23 "
                + "-c:a aac "
                + "-b:a 160k "
                + "-vf format=yuv420p "
                + "-movflags +faststart "
                + f'"{new_file_path}"'
            ),
            stdout=subprocess.PIPE,
        )
        new_size = os.path.getsize(new_file_path)
        if new_size == 0:
            print(f"\n\nERROR!!! Delete h264 version {new_file_path}")
            os.remove(new_file_path)
        else:
            os.remove(path)
            os.rename(new_file_path, path)


async def main():
    video_urls = await get_video_urls()
    video_urls = list(video_urls)

    metadata_queue_manager = Manager()
    metadata_queue = metadata_queue_manager.Queue()

    with Pool(max_num_proc) as p:
        watcher = p.apply_async(metadata_write_listener, (metadata_queue,))

        jobs = []
        for url in video_urls:
            job = p.apply_async(download_video, (url, metadata_queue))
            jobs.append(job)

        # collect results from the workers through the pool result queue
        for job in jobs:
            job.get()

        metadata_queue.put("kill")

    with open("metadata.pkl", "wb") as f:
        pickle.dump(metadata, f)

    downloaded_files = get_all_files(download_folder, suffix=".mp4")
    with Pool(2) as p:
        p.map(re_encode_as_h264, downloaded_files)


if __name__ == "__main__":
    asyncio.run(main())
