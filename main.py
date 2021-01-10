from datetime import datetime
from playsound import playsound
from multiprocessing import Process
from typing import Optional
from stockscan import Scanner, DummyScanner, StockMonitor, ScanResult, Item
from stockscan.vendors import HardwareFrScanner, LDLCScanner, NvidiaScanner, TopAchatScanner, RueDuCommerceScanner, \
    MaterielNetScanner, CaseKingScanner, AlternateScanner

import traceback
import time
import curses
import logging
from pprint import PrettyPrinter

pp = PrettyPrinter(indent=2)

# logging.basicConfig(filename='output.log', filemode='w', level=logging.WARNING)
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def loop(file):
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


class Main:
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
        self._notification_state: str = Main.Unavailable

        # init layout
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_RED, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_BLUE, -1)

        time_format = "%x-%X"
        self.layout = {
            "padding": (3, 1),
            "columns": (("Name", max(map(lambda s: len(s.name), self.monitor.scanners))),
                        ("State", max(map(lambda s: len(s), Main.States))),
                        ("Last Scan", max(len("Last Scan"), len("99s ago"))),
                        ("Last Stock", len(datetime.now().strftime(time_format))),
                        ("Details", -1)),
            "state_colors": {
                Main.InStock: curses.color_pair(2),
                Main.Unavailable: 0,
                Main.Error: curses.color_pair(1)
            },
            "time_format": time_format
        }
        height = self.layout["padding"][1] + 1 + 2 * len(monitor.scanners) + 1
        width = stdscr.getmaxyx()[1]
        self.pad = curses.newpad(height, width)
        self.stdscr = stdscr

    def _play_loop(self, file):
        logger.debug("create notification process")
        self._notification_process = Process(target=loop,
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
            if self._notification_state == Main.InStock:
                self._play_loop("data/whohoo.mp3")
            elif not self.silent_error and self._notification_state == Main.Error:
                self._play_loop("data/nooo.mp3")

    def _notify_state(self, state: str):
        if self._notification_state is state:
            return
        self._notification_state = state
        logger.info(f"notification state going to: {state}")
        self._play_sound_for_state()

    def _notifications(self):
        if any(result[0].is_in_stock for result in self.monitor.last_results):
            self._notify_state(Main.InStock)
        elif any(result[2] >= Main.MAX_FAIL for result in self.monitor.last_results):
            self._notify_state(Main.Error)
        else:
            self._notify_state(Main.Unavailable)

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
            return Main.InStock
        elif result.is_error:
            return Main.Error
        else:
            return Main.Unavailable

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
            x = padding[0]

            state = Main.get_state(result)
            color = int(self.layout["state_colors"][state])
            stdscr.addstr(y, x, scanner.name, color)
            x += columns[0][1] + padding[0]

            state_name = state
            if result.is_error:
                state_name += f" #{'>' if error_count > 9 else ''}{min(9, error_count)}"
            state_attr = 0 if state is Main.Unavailable else curses.A_STANDOUT
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
                    filter_pred = lambda it: it.in_stock
                    text = "in stock"
                else:
                    filter_pred = None
                    text = "watched"

                prices = sorted([item.price for item in filter(filter_pred, result.items)])
                stdscr.addstr(y, x,
                              f"{plural_str('item', len(prices))} {text}")
                if len(prices) > 0:
                    if len(prices) > 1:
                        price_text = f"[{prices[0]} ~ {prices[-1]}]"
                    else:
                        price_text = f"{prices[0]}"
                    stdscr.addstr(f" @ {price_text}")

            stdscr.addstr(y + 1, padding[0],
                          f"\tCheck ")
            stdscr.addstr(scanner.user_url, curses.color_pair(3) | curses.A_UNDERLINE)

            y += 2

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
            if key == 'q' or key == 'Q':
                raise ExitException
            elif key == 'm' or key == 'M':
                self.toggle_mute()
            elif key == 'u' or key == 'U':
                self.monitor.update_now()


def main(update_freq=30, silent=False, max_threads=8, foreign=True, nvidia=True,
         pattern="evga 3080", silent_error=True, gui=True, **kwargs):
    """
    Monitor vendor sites.
    """
    try:
        scanners = []
        custom_ldlc_url = "https://www.ldlc.com/nouveautes/+fcat-4684+fdi-1+fv1026-5801+fv121-19183,19185.html"
        if nvidia:
            scanners.append(NvidiaScanner("3080", **kwargs))
            scanners.append(NvidiaScanner("3090", **kwargs))
            scanners.append(LDLCScanner("", custom_url=custom_ldlc_url, **kwargs))

        if pattern:
            for ScannerClass in [HardwareFrScanner,
                                 LDLCScanner,
                                 TopAchatScanner,
                                 RueDuCommerceScanner,
                                 MaterielNetScanner,
                                 AlternateScanner]:
                scanners.append(ScannerClass(pattern, **kwargs))

            if foreign:
                scanners.append(CaseKingScanner(pattern, **kwargs))
                scanners.append(AlternateScanner(pattern, locale="de", **kwargs))

        dummy_scanners = [
            DummyScanner(delay=1, error=1, stocks=1),
            DummyScanner(delay=1, error=1, stocks=1),
        ]

        # scanners = dummy_scanners

        def main_loop_nogui():
            monitor = StockMonitor(scanners, update_freq=update_freq, max_thread=max_threads)
            try:
                monitor.start()

                def print_scan(scanner: Scanner, result: ScanResult, *args):
                    print(f"{result.timestamp.strftime('%Y/%m/%d %H:%M:%S')} - {scanner.name} - ", end='')
                    if result.is_in_stock:
                        print(f"IN STOCK - {scanner.user_url}")
                    elif result.is_error:
                        print(f"ERROR - {type(result.error).__name__}")
                    elif result.items is not None:
                        print(f"UNAVAILABLE - watching {plural_str('item', len(result.items))}")
                    else:
                        print(f"PENDING")
                monitor.register_to_scan(print_scan)
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
            finally:
                monitor.terminate()

        def main_loop(stdscr):
            monitor = StockMonitor(scanners, update_freq=update_freq, max_thread=max_threads)
            app = Main(monitor, silent=silent, silent_error=silent_error, stdscr=stdscr)
            try:
                monitor.start()
                logger.info("monitor started")
                while True:
                    app.draw()
                    app.input_poll()
                    time.sleep(1.0 / 10)
            except ExitException:
                pass
            finally:
                logger.info("terminate monitor")
                monitor.terminate()

        if gui:
            curses.wrapper(main_loop)
        else:
            main_loop_nogui()

        print("exiting...")

    except Exception as ex:
        print(f"Unexpected ! {ex}")
        traceback.print_exc()


if __name__ == '__main__':
    import fire

    fire.Fire(main)
