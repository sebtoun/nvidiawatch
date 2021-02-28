from datetime import datetime
from playsound import playsound
from multiprocessing import Process
from typing import Optional, Union, List, Tuple
from stockscan import DummyScanner, StockMonitor, ScanResult, ALL_SCANNERS
from functools import partial

import asyncio
import time
import curses
import logging
import json
import dataclasses
from pprint import PrettyPrinter

pp = PrettyPrinter(indent=2)

# logging.basicConfig(filename='output.log', filemode='w', level=logging.WARNING)
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def loop_sound(file):
    while True:
        playsound(file)


class ExitException(Exception):
    pass


def plural_str(noun: str, count: int, plural_mark='s'):
    if not count:
        return f"no {noun}"
    if count == 1:
        return f"1 {noun}"
    return f"{count} {noun}{plural_mark}"


class CursesGUI:
    MAX_FAIL = 5

    InStock = "In Stock"
    Unavailable = "Unavailable"
    Error = "Error"

    States = [InStock, Unavailable, Error]

    def __init__(self, monitor: StockMonitor, silent=False, silent_error=True, stdscr=None):
        self.monitor = monitor
        self.silent = silent
        self.silent_error = silent_error

        # notifications
        self._notification_process: Optional[Process] = None
        self._notification_state: str = CursesGUI.Unavailable

        # init layout
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_RED, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_BLUE, -1)

        time_format = "%x-%X"
        self.layout = {
            "padding": (3, 1),
            "columns": (("Name", max(map(lambda s: len(s.name), self.monitor.scanners))),
                        ("State", max(map(lambda s: len(s), CursesGUI.States))),
                        ("Last Scan", max(len("Last Scan"), len("99s ago"))),
                        ("Last Stock", len(datetime.now().strftime(time_format))),
                        ("Details", -1)),
            "state_colors": {
                CursesGUI.InStock: curses.color_pair(2),
                CursesGUI.Unavailable: 0,
                CursesGUI.Error: curses.color_pair(1)
            },
            "time_format": time_format
        }
        height = self.layout["padding"][1] + 1 + 2 * len(monitor.scanners) + 1
        width = stdscr.getmaxyx()[1]
        self.pad_size = (height, width)
        self.pad = curses.newpad(*self.pad_size)
        self.stdscr = stdscr

    def _grow_pad(self, sizeyx: tuple[int, int]):
        self.pad_size = (self.pad_size[0] + sizeyx[0], self.pad_size[1] + sizeyx[1])
        self.pad = curses.newpad(*self.pad_size)

    def _play_loop(self, file):
        logger.debug("create notification process")
        self._notification_process = Process(target=loop_sound,
                                             args=(file,))
        self._notification_process.daemon = True
        self._notification_process.start()

    def _stop_sound(self):
        if self._notification_process is not None:
            logger.debug("killing notification process")
            self._notification_process.terminate()
            while self._notification_process.is_alive():
                time.sleep(0.1)
            self._notification_process.close()
            self._notification_process = None
            logger.debug("notification process killed")

    @property
    def _is_playing_sound(self):
        return self._notification_process is not None

    def _play_sound_for_state(self):
        if self._is_playing_sound:
            self._stop_sound()
        if not self.silent:
            if self._notification_state == CursesGUI.InStock:
                self._play_loop("data/whohoo.mp3")
            elif not self.silent_error and self._notification_state == CursesGUI.Error:
                self._play_loop("data/nooo.mp3")

    def _notify_state(self, state: str):
        if self._notification_state is state:
            return
        self._notification_state = state
        logger.info(f"notification state going to: {state}")
        self._play_sound_for_state()

    def _notifications(self):
        if any(result[0].is_in_stock for result in self.monitor.last_results):
            self._notify_state(CursesGUI.InStock)
        elif any(result[2] >= CursesGUI.MAX_FAIL for result in self.monitor.last_results):
            self._notify_state(CursesGUI.Error)
        else:
            self._notify_state(CursesGUI.Unavailable)

    def toggle_mute(self):
        self.silent = not self.silent
        if self.silent and self._is_playing_sound:
            self._stop_sound()
        elif not self.silent:
            self._play_sound_for_state()

    @staticmethod
    def add_centered(stdscr, text, *args, **kwargs):
        _, cols = stdscr.getmaxyx()
        y, _ = stdscr.getyx()
        x = (cols - len(text)) // 2
        stdscr.addstr(y, x, text, *args, **kwargs)

    @staticmethod
    def get_state(result: ScanResult) -> str:
        if result.is_in_stock:
            return CursesGUI.InStock
        elif result.is_error:
            return CursesGUI.Error
        else:
            return CursesGUI.Unavailable

    def draw(self):
        stdscr = self.pad
        self._notifications()
        stdscr.clear()
        curses.curs_set(False)

        padding = self.layout["padding"]
        x, y = padding

        columns = self.layout["columns"]
        for column in columns:
            stdscr.addstr(y, x, column[0])
            x += column[1] + padding[0]

        y += 1
        for scanner, (result, last_stock_time, error_count) in zip(self.monitor.scanners, self.monitor.last_results):
            if result.is_in_stock:
                items_in_stock = [item for item in result.items if item.in_stock]
                height = 1 + len(items_in_stock)
            else:
                items_in_stock = []
                height = 2
            # if y + height >= self.pad_size[0]:
            #     self._grow_pad((height, 0))

            x = padding[0]

            state = CursesGUI.get_state(result)
            color = int(self.layout["state_colors"][state])
            stdscr.addstr(y, x, scanner.name, color)
            x += columns[0][1] + padding[0]

            state_name = state
            if result.is_error:
                state_name += f" #{'>' if error_count > 9 else ''}{min(9, error_count)}"
            state_attr = 0 if state is CursesGUI.Unavailable else curses.A_STANDOUT
            stdscr.addstr(y, x,
                          state_name,
                          color | state_attr)
            x += columns[1][1] + padding[0]

            elapsed = datetime.now() - result.timestamp
            stdscr.addstr(y, x, f"{int(elapsed.total_seconds()):>2}s ago", color)
            x += columns[2][1] + padding[0]

            time_format = self.layout["time_format"]
            if last_stock_time is not None:
                stdscr.addstr(y, x, last_stock_time.strftime(time_format), color)
            x += columns[3][1] + padding[0]

            if result.is_error:
                stdscr.addstr(y, x, f"{type(result.error).__name__}: {result.error}", color)
            elif result.items is not None:
                if result.is_in_stock:
                    priced_items = items_in_stock
                    text = "in stock"
                else:
                    priced_items = result.items
                    text = "watched"

                prices = sorted([item.price for item in priced_items])
                stdscr.addstr(y, x, f"{plural_str('item', len(prices))} {text}")
                if len(prices) > 0:
                    if len(prices) > 1:
                        price_text = f"[{prices[0]} ~ {prices[-1]}]"
                    else:
                        price_text = f"{prices[0]}"
                    stdscr.addstr(f" @ {price_text}")
            y += 1
            if result.is_in_stock:
                stdscr.addstr(y, padding[0], f"\tCheck ")
                stdscr.addstr(items_in_stock[0].url, curses.color_pair(3) | curses.A_UNDERLINE)
                y += 1
                # for item in items_in_stock:
                #     stdscr.addstr(y, padding[0], f"\tItem ")
                #     stdscr.addstr(item.url, curses.color_pair(3) | curses.A_UNDERLINE)
                #     y += 1
            else:
                stdscr.addstr(y, padding[0], f"\tCheck ")
                stdscr.addstr(scanner.user_url, curses.color_pair(3) | curses.A_UNDERLINE)
                y += 1

        stdscr.addstr(y, padding[0], f"[ 'Q'uit | 'U'pdate now | ")
        mute_cmd = "Un'm'ute" if self.silent else "'M'ute"
        stdscr.addstr(mute_cmd, curses.A_STANDOUT if self.silent else 0)
        stdscr.addstr(" ]")

        pad_dims = stdscr.getmaxyx()
        screen_dims = self.stdscr.getmaxyx()
        stdscr.refresh(0, 0, 0, 0, min(pad_dims[0], screen_dims[0]) - 1, min(pad_dims[1], screen_dims[1]) - 1)
        self.stdscr.refresh()

    def input_poll(self):
        # handle user inputs (quit)
        self.stdscr.nodelay(True)
        try:
            key = self.stdscr.getkey()
        except:
            pass
        else:
            keyup = key.upper()
            if keyup == 'Q':
                raise ExitException
            elif keyup == 'M':
                self.toggle_mute()
            elif keyup == 'U':
                self.monitor.update_now()

    async def update_loop(self):
        try:
            while True:
                self.draw()
                self.input_poll()
                await asyncio.sleep(0.1)
        except ExitException:
            pass


class Main:
    """
    Monitor vendor sites.
    """

    def __init__(self):
        self._scanners = []

    @staticmethod
    def _check_parameter(name_list: Union[None, str, List[str]]) -> List[str]:
        if name_list is None:
            return []
        if isinstance(name_list, tuple):
            name_list = list(name_list)
        if isinstance(name_list, str):
            name_list = name_list.split(",")
        for i, name in enumerate(name_list):
            name = name.replace('.', '').replace('-', '').lower().strip()
            if not name.endswith("scanner"):
                name += "scanner"
            name_list[i] = name
        return name_list

    def _setup_scanners(self, pattern: str, only_scanners: List[str], except_scanners: List[str]) -> None:
        all_scanner_name = ALL_SCANNERS.keys()
        if only_scanners:
            scanner_names = [name for name in only_scanners if name in all_scanner_name]
        else:
            scanner_names = [name for name in all_scanner_name if name not in except_scanners]

        for name in scanner_names:
            self._scanners.append(ALL_SCANNERS[name](pattern))

    @staticmethod
    async def _print_scan_result(json_output: bool, scanner: Scanner, result: ScanResult, *args) -> None:
        output = {"scanner": scanner.name,
                  "user_url": scanner.user_url,
                  "result": dataclasses.asdict(result)}
        if json_output:
            print(json.dumps(output, indent=4, default=str))
        else:
            pp.pprint(output)

    def pattern(self, pattern: Union[str, List[str], Tuple[str]],
                only_scanners: Union[str, List[str]] = None,
                except_scanners: Union[str, List[str]] = None):
        """
        Add a new pattern to check on scanners
        :param pattern: the pattern to match, supports '-keyword' to blacklist 'keyword'
        :param only_scanners: only monitor with the given scanners
        :param except_scanners: monitor with all scanners except given scanners
        :return: self to allow chaining
        """
        only_scanners = self._check_parameter(only_scanners)
        except_scanners = self._check_parameter(except_scanners)
        if isinstance(pattern, str):
            pattern = pattern.split(',')
        for p in pattern:
            if p:
                self._setup_scanners(p, only_scanners, except_scanners)
        return self

    def scan(self, json=False):
        """
        Perform a single scan on all vendors.
        """
        try:
            monitor = StockMonitor(self._scanners)
            monitor.register_to_scan(partial(Main._print_scan_result, json))
            asyncio.get_event_loop().run_until_complete(monitor.single_update())
        except KeyboardInterrupt:
            logger.debug("interrupted")

    def loop(self, json=False, update_freq=30):
        """
        Loop scan on all vendors at fixed interval.

        Args:
            update_freq (float): The interval at which scans are performed.
        """
        try:
            monitor = StockMonitor(self._scanners, update_freq=update_freq)
            monitor.register_to_scan(partial(Main._print_scan_result, json))
            asyncio.get_event_loop().run_until_complete(monitor.update_loop())
        except KeyboardInterrupt:
            logger.debug("interrupted")

    def gui(self, update_freq=30, silent=False, silent_error=True):
        """
        Loop scan on all vendors at fixed interval and display results in a curses GUI.

        Args:
            update_freq (float): The interval at which scans are performed.
            silent (bool): play sound when stock state changes
            silent_error (bool): play sound when scan results in an error
        """
        curses.wrapper(partial(self._gui_loop, update_freq, silent, silent_error))

    def list(self):
        """
        List all available scanners
        """
        return [name.replace('scanner', '') for name in ALL_SCANNERS.keys()]

    def _gui_loop(self, update_freq, silent, silent_error, stdscr):
        monitor = StockMonitor(self._scanners, update_freq=update_freq)
        app = CursesGUI(monitor, silent=silent, silent_error=silent_error, stdscr=stdscr)

        async def main_loop():
            await asyncio.wait(map(asyncio.create_task, [app.update_loop(), monitor.update_loop()]),
                               return_when=asyncio.FIRST_COMPLETED)
        asyncio.get_event_loop().run_until_complete(main_loop())


if __name__ == '__main__':
    import fire
    fire.Fire(Main)
