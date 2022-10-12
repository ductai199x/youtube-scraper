import asyncio
import os
import pickle
import shlex
import shutil
import subprocess
from multiprocessing import Manager, Pool
from typing import *

import rich
from pytube import YouTube
from pytube.exceptions import PytubeError
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tqdm.auto import tqdm

from chrome_driver_manager import ChromeDriverManager
from helper import get_all_files


async def check_if_page_loaded(driver, prev_url):
    while driver.current_url == prev_url:
        pass


open_proc = lambda cmd_list: subprocess.Popen(
    cmd_list, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1
)

url = "https://www.youtube.com"
max_num_videos = 12
max_num_proc = 10
search_bar_xpath = "//input[@id='search']"
filter_btn_xpath = "//tp-yt-paper-button[@aria-label='Search filters']"
thumbnail_xpath = """
//ytd-video-renderer[@class='style-scope ytd-item-section-renderer'] 
//div[@id='dismissible' and @class='style-scope ytd-video-renderer'] 
//a[@id='thumbnail' and ./yt-img-shadow/img[contains(@src, 'jpg')]]
""".strip()
dataset_root_dir = "/media/nas2/Tai/4-deepfake-data"
download_dir = f"{dataset_root_dir}/downloads"
h264_cvt_dir = f"{dataset_root_dir}/h264"
console = rich.get_console()


async def get_video_urls(search_string) -> Set:
    video_urls = set()
    console.print("[bold blue][INFO ]:[/bold blue][blue]\t\tSetting up the chrome headless driver..")
    cdm = ChromeDriverManager(headless=True)
    try:
        console.print(f"[bold blue][INFO ]:[/bold blue][blue]\t\tOpening {url}..")
        cdm.open_url(url)

        try:
            element_present = EC.presence_of_element_located((By.XPATH, search_bar_xpath))
            WebDriverWait(cdm.driver, 5.0).until(element_present)
        except TimeoutException:
            console.print(
                "[bold red][ERROR]:[/bold red][red]\t\tTimed out waiting for page to load search bar"
            )

        console.print(f"[bold blue][INFO ]:[/bold blue][blue]\t\tInput search string: {search_string}..")
        search_bar = cdm.driver.find_element(By.XPATH, search_bar_xpath)
        search_bar.send_keys(search_string)
        await asyncio.sleep(2)
        search_bar.send_keys(Keys.RETURN)

        console.print(f"[bold blue][INFO ]:[/bold blue][blue]\t\tWaiting for search results to appear..")
        await asyncio.wait_for(check_if_page_loaded(cdm.driver, url), timeout=20.0)

        try:
            element_present = EC.presence_of_element_located((By.XPATH, filter_btn_xpath))
            WebDriverWait(cdm.driver, 5.0).until(element_present)
        except TimeoutException:
            console.print(
                "[bold red][ERROR]:[/bold red][red]\t\tTimed out waiting for page to load filter button"
            )

        console.print(f"[bold blue][INFO ]:[/bold blue][blue]\t\tProcessing result page..")
        last_thumbnail_loc = 0
        pbar = tqdm(total=None)
        while len(video_urls) < max_num_videos:
            thumbnails = cdm.driver.find_elements(By.XPATH, thumbnail_xpath)
            if thumbnails[-1].location["y"] > last_thumbnail_loc:
                # print(len(video_urls), last_thumbnail_loc, thumbnails[-1].location["y"])
                for t in thumbnails:
                    video_url: str = t.get_attribute("href")
                    if video_url.find("list") < 0 and video_url.startswith("https://www.youtube.com"):
                        yt_obj = YouTube(video_url)
                        video_title = yt_obj.title.lower()
                        video_streams = mp4files = yt_obj.streams.filter(file_extension="mp4", res="1080p")
                        if len(video_streams) < 1:
                            continue
                        if any(
                            list(
                                map(
                                    lambda s: s in video_title,
                                    ["amber", "heard", "johnny", "depp", "live", "trial"],
                                )
                            )
                        ):
                            continue
                        video_urls.add(video_url)
                        pbar.set_description(f"Processing {len(video_urls)}/{max_num_videos}")
                        pbar.update()
                last_thumbnail_loc = thumbnails[-1].location["y"]

            cdm.driver.execute_script(f"window.scrollBy(0, 1000)", "")
            await asyncio.sleep(2.0)  # wait for page to load
        pbar.close()

        cdm.close_driver()
    except Exception as e:
        console.print(f"[bold red][ERROR]:[/bold red][red]\t\t{e}")
        if cdm.driver.session_id:
            cdm.close_driver()
    finally:
        return list(video_urls)


def on_complete_download(_, file_path: str):
    console.print(f"[bold green][FINISHED]:[/bold green][green]\t\tFinished downloading {file_path}")


def download_video(url: str, search_string: str, metadata):
    try:
        yt = YouTube(url, on_complete_callback=on_complete_download)
        mp4files = yt.streams.filter(file_extension="mp4", res="1080p")
        if len(mp4files) > 0:
            yt_stream = mp4files[-1]
            default_path = f"{download_dir}/{yt.video_id}"
            filesize_in_stream = yt_stream.filesize
            filesize_on_disk = os.path.getsize(default_path) if os.path.exists(default_path) else -1
            metadata[url] = {
                "search_string": search_string,
                "title": yt.title,
                "author": yt.author,
                "desc": yt.description,
                "size": filesize_in_stream,
                "path": default_path,
            }
            console.print(
                f"[bold blue][INFO ]:[/bold blue][blue]\t\t{yt.title}, {filesize_in_stream}, "
                + f"{filesize_on_disk}, {filesize_in_stream == filesize_on_disk}"
            )
            if filesize_in_stream != filesize_on_disk:
                console.print(
                    f"[bold blue][INFO ]:[/bold blue][blue]\t\tDownloading...{yt.title} ({yt.video_id}.mp4)"
                )
                yt_stream.download(
                    output_path=download_dir,
                    filename=f"{yt.video_id}.mp4",
                    max_retries=100,
                    timeout=300,
                )
            else:
                console.print(
                    f"[bold blue][INFO ]:[/bold blue][blue]\t\t{yt.title} has already been downloaded."
                )
        else:
            console.print(
                f"[bold red][ERROR]:[/bold red][red]\t\tNo 1080p resolution or mp4 stream doesn't exist "
                + f"for {yt.title} {yt.video_id}"
            )
    except (Exception, PytubeError) as e:
        console.print(
            f"[bold red][ERROR]:[/bold red][red]\t\tFile {yt.title} ({yt.video_id}.mp4) "
            + f"has failed with {repr(e)}"
        )


def re_encode_as_h264(path: str):
    dir, fname = os.path.split(path)
    basename, ext = os.path.splitext(fname)
    new_file_path = f"{h264_cvt_dir}/{basename}.mp4"

    get_codec = subprocess.run(
        shlex.split(
            f"ffprobe -v error -select_streams v:0 "
            + f"-show_entries stream=codec_name -of default=noprint_wrappers=1:nokey=1 "
            + f'"{path}"'
        ),
        stdout=subprocess.PIPE,
    )
    codec_name = str(get_codec.stdout.decode("utf-8")).strip()
    if codec_name != "h264":
        console.print(
            f"[bold blue][INFO ]:[/bold blue][blue]\t\tConverting {path}({codec_name}) "
            + f"-> {new_file_path}(h264)..."
        )
        subprocess.run(
            shlex.split(
                f"ffmpeg -loglevel error -stats "
                + "-hwaccel cuda "
                + "-hwaccel_device 0 "
                + f'-i "{path}" '
                + "-c:v h264_nvenc "
                + "-b:v 6500k "
                + "-preset fast "
                + "-c:a aac "
                + "-b:a 960k "
                + "-vf format=yuv420p "
                + "-movflags +faststart "
                + f'"{new_file_path}"'
            ),
            stdout=subprocess.PIPE,
        )
        new_size = os.path.getsize(new_file_path)
        if new_size == 0:
            console.print(
                f"\n\n[bold red][ERROR]:[/bold red][red]\t\tNew file's size is 0! "
                + f"Delete h264 version {new_file_path}"
            )
            os.remove(new_file_path)
    else:
        shutil.copy(path, new_file_path)


async def main():
    search_strings = [
        "ariana grande",
        "justin bieber",
        "taylor swift",
        "selena gomez",
        "ed sheeran",
        "miley cyrus",
        "lady gaga",
        "billie eilish",
        "camila cabello",
        "bruno mars",
        "charlie puth",
        "tom holland",
        "dwayne johnson",
        "scarlett johansson",
        "daniel craig",
        "tom cruise",
        "liam neeson",
        "rami malek",
        "keanu reeves",
        "benedict cumberbatch",
        "chris pratt",
        "jennifer lawrence",
    ]
    print("\n".join(search_strings))

    video_urls = []
    for ss in search_strings:
        extracted_urls = await get_video_urls(f"{ss} interview")
        video_urls += list(zip(extracted_urls, [ss] * len(extracted_urls)))

    with open(f"{dataset_root_dir}/download_list.txt", "w") as f:
        for i, (url, search_string) in enumerate(video_urls):
            f.write(f"{i+1}, {url}, {search_string}, {YouTube(url).title}\n")

    with open(f"{dataset_root_dir}/download_list.txt", "r") as f:
        for line in f:
            fields = line.split(", ")
            video_urls.append((fields[1], fields[2]))

    multiproc_manager = Manager()
    metadata = multiproc_manager.dict()

    with Pool(max_num_proc) as p:
        jobs = []
        for url, search_string in video_urls:
            job = p.apply_async(download_video, (url, search_string, metadata))
            jobs.append(job)

        # collect results from the workers through the pool result queue
        for job in jobs:
            job.get()

    with open(f"{dataset_root_dir}/metadata.pkl", "wb") as f:
        pickle.dump(dict(metadata), f)

    if not os.path.exists(h264_cvt_dir):
        os.makedirs(h264_cvt_dir)
    downloaded_files = get_all_files(download_dir, suffix=".mp4")
    with Pool(2) as p:
        p.map(re_encode_as_h264, downloaded_files)


if __name__ == "__main__":
    asyncio.run(main())
