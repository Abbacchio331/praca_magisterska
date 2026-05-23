from playwright.async_api import async_playwright, Page, Browser, BrowserContext, TimeoutError as PlaywrightTimeoutError
from anyio import open_file
from modules.speech import play_voice
from regex import findall, DOTALL
import asyncio
import time

DEBUGGING: bool = False
SOUNDS_PATH: str = "assets/sounds/"
BLANK_PAGE_VOICE_LOCATION: str = SOUNDS_PATH + "blank_page.wav"
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
            play_voice(BLANK_PAGE_VOICE_LOCATION)
            return

        print(f"Szukam '{title}'...")
        page_html = await self.page.content()

        if 'aria-controls="suggestion-list"' in page_html:
            search_input = self.page.locator('input[aria-controls="suggestion-list"]').first
            await search_input.fill(title)
            await search_input.press("Enter")
        else:
            print("Nie znaleziono pola wpisywania.")
            play_voice(OPEN_BROWSER_ERROR_VOICE_LOCATION)
            if DEBUGGING:
                async with await open_file('html_test_1.txt', 'w+', encoding="utf-8") as f:
                    await f.write(page_html)
            return

        await self.page.wait_for_timeout(wait_time * 50)
        await self.page.wait_for_load_state("networkidle", timeout=wait_time * 1000)
        found_page_html = await self.page.content()
        print(f"Szukanie '{title}' zakończone.")
        await asyncio.sleep(1)
        page_type_search: list = findall(r'(?i)(ytAttributedStringHost ytAttributedStringWhiteSpaceNoWrap"[^>]*?>\s*(?:Play|Shuffle)\s*<|ytmusic-(?:shelf-renderer|item-section-renderer)"[^>]*?>\s*songs\s*<|id="undercards")', found_page_html)
        if not page_type_search or not findall(r'(?i)\b(play|songs|undercards|shuffle)\b', page_type_search[0]):
            play_voice(OPEN_BROWSER_ERROR_VOICE_LOCATION)
            if DEBUGGING:
                async with await open_file('html_test_2.txt', 'w+', encoding="utf-8") as f:
                    await f.write(found_page_html)
            return

        play_button_locator = None
        title_search: list | None = None

        if findall(r'(?i)\b(play|shuffle)\b', page_type_search[0]):
            play_button_locator = self.page.locator(
                '#actions > yt-button-renderer:nth-child(1) > yt-button-shape > button').first
            title_search = findall(
                r'class="title style-scope ytmusic-card-(?:shelf-renderer|item-section-renderer)"(?:[^>]*?>){2}\s*([^<]*?)\s*<',
                found_page_html, DOTALL)

        elif findall(r'(?i)\b(songs|undercards)\b', page_type_search[0]):
            if "ytmusic-shelf-renderer" in found_page_html:
                play_button_locator = self.page.locator('#contents > ytmusic-shelf-renderer:nth-child(3) #play-button').first
            else:
                play_button_locator = self.page.locator('#contents.ytmusic-section-list-renderer > ytmusic-item-section-renderer:nth-child(3) #play-button').first

            title_search = findall(r'(?i)ytmusic-(?:shelf-renderer|item-section-renderer)"[^>]*?>\s*songs\s*<.*?title="\s*([^"]*?)\s*"',
                                   found_page_html, DOTALL)

        if not play_button_locator:
            print("Nie znaleziono przycisku odtwarzania.")
            play_voice(SONG_NOT_FOUND_ERROR)
            return

        if title_search:
            found_title = title_search[0]
        else:
            found_title = title

        try:
            await play_button_locator.click(timeout=5000)
            print(f"Uruchamiam '{found_title}'...")
        except Exception as e:
            print(f"Błąd: Przycisk odtwarzania (lokator: {play_button_locator}) jest niedostępny na stronie.")
            print(f"Szczegóły błędu: {e}")
            play_voice(SONG_NOT_FOUND_ERROR)
            return

        await self.monitor_ad_status()

        # Wyłączenie funkcji autoplay jeżeli była włączona
        if findall(r'id="automix"', found_page_html):
            if findall(r'id="automix"[^>]*?aria-pressed="true"', found_page_html):
                try:
                    await self.page.locator('#automix').first.click(force=True, timeout=5000)
                    print("Wyłączono automatyczne odtwarzanie.")
                except PlaywrightTimeoutError:
                    print("Błąd: Przycisk automix został znaleziony w HTML, ale nie można w niego kliknąć.")
            elif findall(r'id="automix"[^>]*?aria-pressed="false"', found_page_html):
                print("Automatyczne odtwarzanie zostało uprzednio wyłączone.")

    @staticmethod
    def _extract_title(html: str) -> str:
        """Pobiera aktualny tytuł z paska YouTube Music."""
        matches = findall(r'class="title style-scope ytmusic-player-bar"[^>]*?>\s*([^<]*?)\s*<', html)
        return matches[0] if matches else ""

    async def _mute_ad(self):
        """Wycisza odtwarzacz, ignorując błędy timeout."""
        try:
            await self.page.locator('button[aria-label="Mute"]').first.click(timeout=1000)
        except Exception as e:
            if "timeout" not in str(e).lower():
                print("Nie można wyciszyć tej reklamy.\nPowód:", e)

    async def _skip_ad_if_possible(self, html: str):
        """Sprawdza obecność przycisku i próbuje pominąć reklamę."""
        if "ytp-ad-skip-button-modern" in html:
            try:
                await self.page.locator('.ytp-ad-skip-button-modern').first.click()
                print("Pominięto reklamę.")
            except Exception as e:
                print("Nie udało się pominąć reklamy\nPowód:", e)

    async def _unmute_song(self):
        """Odcisza odtwarzacz po zakończeniu reklamy."""
        try:
            await self.page.locator('button[aria-label="Unmute"]').first.click(timeout=1000)
        except Exception as e:
            if "timeout" not in str(e).lower():
                print("Nie udało się odciszyć piosenki.\nPowód:", e)


    async def is_ad_playing(self) -> bool:
        await asyncio.sleep(2)
        html = await self.page.content()
        if 'title="Video will play after ad"' in html:
            return True
        return False


    async def monitor_ad_status(self):
        print("Rozpoczęto monitorowanie reklam...")

        start_time: float = time.time()
        await self._mute_ad()
        while True:
            try:
                if time.time() - start_time > 60.0:
                    print(f"Limit czasu (60s) minął. Przerywam monitorowanie reklam.")
                    await self._unmute_song()
                    break

                await asyncio.sleep(2)
                html = await self.page.content()

                is_ad = await self.is_ad_playing()

                if is_ad:
                    await self._mute_ad()
                    await self._skip_ad_if_possible(html)
                    await asyncio.sleep(2)
                else:
                    await self._unmute_song()
                    print("Rozpoczęto odtwarzanie!")
                    break

            except Exception as e:
                print("Błąd w monitorowaniu:", e)
                await self._unmute_song()
                break


    async def stop_song(self):
        try:
            await self.page.locator('button[aria-label="Pause"]').first.click(timeout=3000)
        except Exception as e:
            if "timeout" in str(e).lower():
                print("Ta piosenka już jest zatrzymana.")
            else:
                print("Nie udało się zatrzymać piosenki.\nPowód:", e)
        else:
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
