from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from modules.speech import play_voice
from regex import findall, DOTALL
import asyncio

SOUNDS_PATH: str = "assets/sounds/"
OPEN_BROWSER_ERROR_VOICE_LOCATION: str = SOUNDS_PATH + "open_browser_error.wav"
SONG_NOT_FOUND_ERROR: str = SOUNDS_PATH + "song_not_found_error.wav"
SONG_ALREADY_STOPPED_VOICE_LOCATION: str = SOUNDS_PATH + "song_already_stopped.wav"
STOPPED_SONG_VOICE_LOCATION: str = SOUNDS_PATH + "stopped_song.wav"

class YouTubeSession:
    def __init__(self):
        self.playwright = None
        self.browser: Browser = None  # type: ignore
        self.context: BrowserContext = None  # type: ignore
        self.page: Page = None  # type: ignore
        self.html_snapshot: str = ""
        self.START_URL = "https://music.youtube.com"

    async def open_the_search_page(self, wait_time: int = 30):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=False)

        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            permissions=["geolocation", "notifications"],
            locale='en-US',
            java_script_enabled=True,
        )

        self.page = await self.context.new_page()
        await self.page.goto(self.START_URL, timeout=wait_time * 1000)
        await self.page.wait_for_timeout(wait_time * 50)
        await self.page.wait_for_load_state("domcontentloaded", timeout=wait_time * 1000)

        self.html_snapshot = await self.page.content()

        if 'aria-label="Reject all"' in self.html_snapshot:
            await self.page.locator('button[aria-label="Reject all"]').first.click()

        print("YouTube Music jest gotowy.")

    async def find_and_a_play_song(self, title: str, wait_time: int = 30):
        if self.page is None:
            print("Strona nie istnieje.")
            await play_voice(OPEN_BROWSER_ERROR_VOICE_LOCATION)
            return

        print(f"Szukam '{title}'...")
        page_html = await self.page.content()

        if 'aria-controls="suggestion-list"' in page_html:
            search_input = self.page.locator('input[aria-controls="suggestion-list"]').first
            await search_input.fill(title)
            await search_input.press("Enter")
        else:
            print("Nie znaleziono pola wpisywania.")
            await play_voice(OPEN_BROWSER_ERROR_VOICE_LOCATION)
            return

        await self.page.wait_for_timeout(wait_time * 50)
        await self.page.wait_for_load_state("networkidle", timeout=wait_time * 1000)
        found_page_html = await self.page.content()
        print(f"Szukanie '{title}' zakończone.")
        # with open('debug_search_result1.html', 'w', encoding='utf-8') as f:
        #     f.write(found_page_html)

        page_type_search: list = findall(r'(?i)(yt-core-attributed-string--white-space-no-wrap"[^>]*?>\s*Play\s*<|ytmusic-shelf-renderer"[^>]*?>\s*songs\s*<|id="undercards")', found_page_html)
        if not page_type_search or not findall(r'(?i)\b(play|songs|undercards)\b', page_type_search[0]):
            await play_voice(OPEN_BROWSER_ERROR_VOICE_LOCATION)
            return

        title_search: list | None = None
        if findall(r'(?i)\b(play)\b', page_type_search[0]):
            await self.page.locator('#actions > yt-button-renderer:nth-child(1) > yt-button-shape > button').first.click()
            title_search = findall(r'class="title style-scope ytmusic-card-shelf-renderer"(?:[^>]*?>){2}\s*([^<]*?)\s*<', found_page_html, DOTALL)
        elif findall(r'(?i)\b(songs|undercards)\b', page_type_search[0]):
            await self.page.locator('#contents > ytmusic-shelf-renderer:nth-child(3) #play-button').first.click()
            title_search = findall(r'(?i)ytmusic-shelf-renderer"[^>]*?>\s*songs\s*<.*?title="\s*([^"]*?)\s*"', found_page_html, DOTALL)

        if title_search is not None:
            title = title_search[0]
        else:
            print("Nie znaleziono piosenki")
            await play_voice(SONG_NOT_FOUND_ERROR)
            return

        print(f"Uruchamiam '{title}'...")
        await self.monitor_ad_status(title)

        # Disable autoplay if enabled
        if findall(r'id="automix"', found_page_html):
            if findall(r'id="automix"[^>]*?aria-pressed="true"', found_page_html):
                await self.page.locator('#automix').first.click()
                print("Wyłączono automatyczne oddtwarzanie.")
            elif findall(r'id="automix"[^>]*?aria-pressed="false"', found_page_html):
                print("Automatyczne oddtwarzanie zostało uprzednio wyłączone.")

        # Start monitoring ads
        return True, found_page_html

    async def monitor_ad_status(self, title: str):
        print("Rozpoczęto monitorowanie reklam...")
        while True:
            try:
                html = await self.page.content()

                # Get current title from bottom bar
                title_2_matches = findall(r'class="title style-scope ytmusic-player-bar"[^>]*?>\s*([^<]*?)\s*<', html)
                title_2 = title_2_matches[0] if title_2_matches else ""

                is_ad = title_2 != title
                # print(f"? title_2 = '{title_2}', ad = {is_ad}")

                if is_ad:
                    # Mute if ad is playing
                    # print("? Muting...")
                    try:
                        await self.page.locator('button[aria-label="Mute"]').first.click(timeout=1000)
                    except Exception as e:
                        if "timeout" in str(e).lower():
                            pass
                        else:
                            print("Nie można wyciszyć tej reklamy.\nPowód:", e)

                    # Skip ad if possible
                    if "ytp-ad-skip-button-modern" in html:
                        try:
                            await self.page.locator('.ytp-ad-skip-button-modern').first.click()
                            print("Pominięto reklamę.")
                        except Exception as e:
                            print("Nie udało się pominąć reklamy\nPowód:", e)
                    await asyncio.sleep(2)
                else:
                    try:
                        await self.page.locator('button[aria-label="Unmute"]').first.click(timeout=1000)
                    except Exception as e:
                        if "timeout" in str(e).lower():
                            pass
                        else:
                            print("Nie udało się odciszyć piosenki.\nPowód:", e)
                    print("Rozpoczęto oddtwarzanie!")
                    break
            except Exception as e:
                print("Błąd w monitorowaniu:", e)
                break


    async def stop_song(self):
        try:
            await self.page.locator('button[aria-label="Pause"]').first.click(timeout=3000)
        except Exception as e:
            if "timeout" in str(e).lower():
                print("Ta piosenka już jest zatrzymana.")
                # await play_voice(SONG_ALREADY_STOPPED_VOICE_LOCATION)
            else:
                print("Nie udało się zatrzymać piosenki.\nPowód:", e)
        else:
            await play_voice(STOPPED_SONG_VOICE_LOCATION)
            print("Zatrzymano oddtwarzanie piosenki.")

    async def resume_song(self):
        try:
            await self.page.locator('button.yt-icon-button[aria-label="Play"]').first.click(timeout=3000)
        except Exception as e:
            if "timeout" in str(e).lower():
                print("Ta piosenka już jest oddtwarzana.")
            else:
                print("Nie udało się wznowić oddtwarzanie piosenki.\nPowód:", e)
        else:
            print("Wznowiono odtwarzanie.")

    async def shutdown(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        print("Sesja YouTube została zamknięta.")