import asyncio
from multiprocessing import Pool
from typing import *

from pytube import YouTube
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from chrome_driver_manager import ChromeDriverManager


async def check_if_page_loaded(driver, prev_url):
    while driver.current_url == prev_url:
        pass


url = "https://www.youtube.com"
max_num_videos = 100
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
    cdm = ChromeDriverManager(headless=True)
    try:
        cdm.open_url(url)

        try:
            element_present = EC.presence_of_element_located((By.XPATH, search_bar_xpath))
            WebDriverWait(cdm.driver, 5.0).until(element_present)
        except TimeoutException:
            print("Timed out waiting for page to load search bar")

        search_bar = cdm.driver.find_element(By.XPATH, search_bar_xpath)
        search_bar.send_keys(search_string)
        await asyncio.sleep(2)
        search_bar.send_keys(Keys.RETURN)

        await asyncio.wait_for(check_if_page_loaded(cdm.driver, url), timeout=20.0)

        try:
            element_present = EC.presence_of_element_located((By.XPATH, filter_btn_xpath))
            WebDriverWait(cdm.driver, 5.0).until(element_present)
        except TimeoutException:
            print("Timed out waiting for page to load filter button")

        last_thumbnail_loc = 0
        while len(video_urls) < max_num_videos:
            thumbnails = cdm.driver.find_elements(By.XPATH, thumbnail_xpath)
            if thumbnails[-1].location["y"] > last_thumbnail_loc:
                # print(len(video_urls), last_thumbnail_loc, thumbnails[-1].location["y"])
                for t in thumbnails:
                    video_url: str = t.get_attribute("href")
                    if video_url.find("list") < 0 and video_url.startswith("https://www.youtube.com"):
                        video_urls.add(video_url)
                last_thumbnail_loc = thumbnails[-1].location["y"]

            cdm.driver.execute_script(f"window.scrollBy(0, 1000)", "")
            await asyncio.sleep(2.5)  # wait for page to load

        cdm.close_driver()
    except Exception as e:
        print(e)
        if cdm.driver.session_id:
            cdm.close_driver()
    finally:
        return video_urls


def on_complete_download(file_path: str):
    print(f"Finished downloading {file_path}")


def download_video(url: str):
    yt = YouTube(url, on_complete_callback=on_complete_download)
    print(yt.title, url)
    mp4files = yt.streams.filter(file_extension="mp4", res="1080p")
    if len(mp4files) > 0:
        mp4files[-1].download(output_path=download_folder)
    else:
        print(f"No 1080p resolution or mp4 stream doesn't exist for {url}.")


async def main():
    video_urls = await get_video_urls()
    video_urls = list(video_urls)
    with Pool(max_num_proc) as p:
        print(p.map(download_video, video_urls))


if __name__ == "__main__":
    asyncio.run(main())
