#! /usr/bin/env python3
import platform
from typing import *

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities


class ChromeDriverManager:
    def __init__(
        self,
        driver_version="101_0",
        headless=False,
        gpu=False,
        extensions=False,
        js=True,
        ignore_cert_err=False,
        eager=False,
        wait=5,
    ):
        self.driver_version = driver_version
        self.headless = "--headless" if headless else None
        self.gpu = None if gpu else "--disable-gpu"
        self.extensions = None if extensions else "--disable-extensions"
        self.js = None if js else "--disable-javascript"
        self.ignore_cert_err = "--ignore-certificate-errors" if ignore_cert_err else None
        self.wait = wait

        id, driver = self.init_driver(
            driver_version=self.driver_version,
            headless=self.headless,
            gpu=self.gpu,
            extensions=self.extensions,
            js=self.js,
            ignore_cert_err=self.ignore_cert_err,
            wait=self.wait,
            eager=eager,
        )
        self.id = id
        self.driver = driver
        self.current_tab = driver.current_window_handle

    @staticmethod
    def init_driver(
        driver_version, headless, gpu, extensions, js, ignore_cert_err, wait, eager
    ) -> Tuple[str, webdriver.Chrome]:
        options = Options()
        if headless:
            options.add_argument(headless)
        if gpu:
            options.add_argument(gpu)
        if extensions:
            options.add_argument(extensions)
        if js:
            options.add_argument(js)
        if ignore_cert_err:
            options.add_argument(ignore_cert_err)

        options.add_argument("--no-sandbox")
        options.add_argument("start-maximized")
        options.add_argument("disable-infobars")

        # https://www.selenium.dev/documentation/webdriver/capabilities/shared/#pageloadstrategy
        options.page_load_strategy = "none"
        # # Disable image loading:
        # disable_img_loading = {"profile.managed_default_content_settings.images": 2}
        # options.add_experimental_option("prefs", disable_img_loading)

        os = platform.system()
        if os == "Linux":
            exec_path = f"./chromedriver_linux64_v{driver_version}"
        elif os == "Windows":
            exec_path = f"./chromedriver_win32_v{driver_version}.exe"
        else:
            raise NotImplementedError(f"No driver for platform `{os}`")

        caps = DesiredCapabilities().CHROME.copy()

        if eager:
            driver = webdriver.Chrome(
                executable_path=exec_path,
                chrome_options=options,
                desired_capabilities=caps,
            )
        else:
            driver = webdriver.Chrome(executable_path=exec_path, chrome_options=options)

        driver.implicitly_wait(wait)
        return (driver.current_window_handle, driver)

    def open_url(self, pageUrl: str) -> None:
        self.driver.get(pageUrl)

    def get_driver(self) -> WebDriver:
        return self.driver

    def get_driver_handles(self) -> List:
        return self.driver.window_handles

    def get_current_tab_id(self) -> str:
        return self.current_tab

    def close_driver(self) -> None:
        self.driver.quit()

    def open_new_tab(self, link: str):
        self.driver.execute_script("window.open(" + link + ")")
        self.driver.switch_to.window(self.get_driver_handles()[-1])

    def switch_to_tab(self, tab_idx: int):
        try:
            tab_handle = self.get_driver_handles()[tab_idx]
            self.driver.switch_to.window(tab_handle)
            self.current_tab = tab_handle
        except Exception as e:
            print("Tab not found\n" + repr(e))

    def switch_to_handle(self, tab_handle: str):
        try:
            self.driver.switch_to.window(tab_handle)
            self.current_tab = tab_handle
        except Exception as e:
            print("Tab not found\n" + repr(e))


# class PageAction(object):
#     def __init__(self, browser):
#         self._browser = browser.implicitly_wait(2)

#     def getTextByXpath(self, xpath):
#         self._xpath = xpath
#         self.__text = ''
#         self.__t0 = time.clock()
#         self.__time = time.clock() - self.__t0
#         self.__found = False
#         while self.__time < 10 and self.__found == False:
#             try:
#                 element = self._browser.find_element_by_xpath(self._xpath)
#                 self.__text = element.text
#                 self.__found = True
#             except:
#                 self.__text = ''
#             self.__time = time.clock() - self.__t0
#         return self.__text


# class ElementHasClass(object):
#     """An expectation for checking that an element has a particular css class.

#     locator - used to find the element
#     returns the WebElement once it has the particular css class
#     """

#     def __init__(self, locator, css_class):
#         self.locator = locator
#         self.css_class = css_class

#     def __call__(self, driver):
#         element = driver.find_element(*self.locator)  # Finding the referenced element
#         if self.css_class in element.get_attribute("class"):
#             return element
#         else:
#             return False
