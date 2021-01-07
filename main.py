from datetime import datetime
from playsound import playsound
from multiprocessing import Process
from typing import Optional
from stockscan import Scanner, DummyScanner, StockMonitor
from stockscan.vendors import HardwareFrScanner, LDLCScanner, NvidiaScanner, TopAchatScanner, RueDuCommerceScanner, \
    MaterielNetScanner, CaseKingScanner, AlternateScanner

import traceback
import time
import curses
import logging

logging.basicConfig(filename='output.log', filemode='w')


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

    def __init__(self, monitor: StockMonitor, silent=False, silent_error=True):
        self.monitor = monitor
        self.silent = silent
        self.silent_error = silent_error

        # notifications
        self._notification_process: Optional[Process] = None
        self._notification_state: str = Scanner.Unavailable

        # init layout
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_RED, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_BLUE, -1)

        state_names = {
            Scanner.InStock: "In Stock",
            Scanner.Unavailable: "Unavailable",
            Scanner.Error: "Error"
        }
        time_format = "%x-%X"
        self.layout = {
            "padding": (3, 1),
            "columns": (("Name", max(map(lambda s: len(s.name), self.monitor.scanners))),
                        ("State", max(map(lambda s: len(s), state_names.values()))),
                        ("Last Scan", max(len("Last Scan"), len("99s ago"))),
                        ("Last Stock", len(datetime.now().strftime(time_format))),
                        ("Details", -1)),
            "state_names": state_names,
            "state_colors": {
                Scanner.InStock: curses.color_pair(2),
                Scanner.Unavailable: 0,
                Scanner.Error: curses.color_pair(1)
            },
            "time_format": time_format
        }

    def _play_loop(self, file):
        logging.debug("create notification process")
        self._notification_process = Process(target=loop,
                                             args=(file,))
        self._notification_process.daemon = True
        self._notification_process.start()

    def _stop_sound(self):
        if self._notification_process is not None:
            logging.debug("killing notification process")
            self._notification_process.terminate()
            while self._notification_process.is_alive():
                time.sleep(0.1)
            self._notification_process.close()
            self._notification_process = None
            logging.debug("notification process killed")

    @property
    def _is_playing_sound(self):
        return self._notification_process is not None

    def _play_sound_for_state(self):
        if self._is_playing_sound:
            self._stop_sound()
        if not self.silent:
            if self._notification_state == Scanner.InStock:
                self._play_loop("data/whohoo.mp3")
            elif not self.silent_error and self._notification_state == Scanner.Error:
                self._play_loop("data/nooo.mp3")

    def _notify_state(self, state: str):
        if self._notification_state is state:
            return
        self._notification_state = state
        logging.info(f"notification state going to: {state}")
        self._play_sound_for_state()

    def _notifications(self):
        if any(s.in_stock for s in self.monitor.scanners):
            self._notify_state(Scanner.InStock)
        elif any(s.consecutive_errors >= Main.MAX_FAIL for s in self.monitor.scanners):
            self._notify_state(Scanner.Error)
        else:
            self._notify_state(Scanner.Unavailable)

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

    def draw(self, stdscr):
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
        for i, scanner in enumerate(self.monitor.scanners):
            x = padding[0]

            state = scanner.last_sate
            color = int(self.layout["state_colors"][state])
            stdscr.addstr(y, x, scanner.name, color)
            x += columns[0][1] + padding[0]

            state_name = self.layout["state_names"][state]
            if scanner.has_error:
                state_name += f" #{'>' if scanner.consecutive_errors > 9 else ''}{min(9, scanner.consecutive_errors)}"
            state_attr = 0 if state is Scanner.Unavailable else curses.A_STANDOUT
            stdscr.addstr(y, x,
                          state_name,
                          color | state_attr)
            x += columns[1][1] + padding[0]

            if scanner.last_scan_time is not None:
                elapsed = datetime.now() - scanner.last_scan_time
                stdscr.addstr(y, x, f"{int(elapsed.total_seconds()):>2}s ago", color)
            x += columns[2][1] + padding[0]

            time_format = self.layout["time_format"]
            if scanner.last_stock_time is not None:
                stdscr.addstr(y, x, scanner.last_stock_time.strftime(time_format), color)
            x += columns[3][1] + padding[0]

            if scanner.last_error is not None:
                stdscr.addstr(y, x, f"{scanner.last_error}", color)
            elif scanner.watched_item_count is not None:
                if scanner.in_stock:
                    filter_pred = lambda it: it[2]
                    text = "in stock"
                else:
                    filter_pred = None
                    text = "watched"

                prices = sorted([price for _, price, _ in filter(filter_pred, scanner.items)])
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

        stdscr.addstr(y, padding[0], f"[ 'Q'uit | 'C'lear errors | 'U'pdate now | ")
        mute_cmd = "Un'm'ute" if self.silent else "'M'ute"
        stdscr.addstr(mute_cmd, curses.A_STANDOUT if self.silent else 0)
        stdscr.addstr(" ]")

        stdscr.refresh()
        # handle user inputs (quit)
        stdscr.nodelay(True)
        try:
            key = stdscr.getkey()
        except:
            pass
        else:
            if key == 'q' or key == 'Q':
                raise ExitException
            elif key == 'c' or key == 'C':
                self.monitor.clear_errors()
            elif key == 'm' or key == 'M':
                self.toggle_mute()
            elif key == 'u' or key == 'U':
                self.monitor.update_now()


def main(update_freq=20, silent=False, max_threads=8, foreign=True, nvidia=True,
         pattern="evga 3080", timeout=None, silent_error=True):
    """
    Monitor vendor sites.
    """
    try:
        Scanner.DefaultTimeout = timeout or update_freq
        scanners = []
        custom_ldlc_url = "https://www.ldlc.com/nouveautes/+fcat-4684+fdi-1+fv1026-5801+fv121-19183,19185.html"
        if nvidia:
            scanners.append(NvidiaScanner("3080"))
            scanners.append(NvidiaScanner("3090"))
            scanners.append(LDLCScanner("", custom_url=custom_ldlc_url))

        if pattern:
            for ScannerClass in [HardwareFrScanner, LDLCScanner, TopAchatScanner, RueDuCommerceScanner,
                                 MaterielNetScanner, AlternateScanner]:
                scanners.append(ScannerClass(pattern))

            if foreign:
                scanners.append(CaseKingScanner(pattern))
                scanners.append(AlternateScanner(pattern, locale="de"))

        dummy_scanners = [
            DummyScanner(delay=1, error=1, stocks=100),
            # DummyScanner(delay=1, error=10, stocks=2),
            # DummyScanner(delay=1, error=2, stocks=2),
        ]
        # scanners = dummy_scanners

        def main_loop(stdscr):
            monitor = StockMonitor(scanners, update_freq=update_freq, max_thread=max_threads)
            app = Main(monitor, silent=silent, silent_error=silent_error)
            try:
                monitor.start()
                while True:
                    app.draw(stdscr)
                    time.sleep(1.0 / 10)
            except ExitException:
                pass
            finally:
                monitor.terminate()

        curses.wrapper(main_loop)
        print("exiting...")

    except Exception as ex:
        print(f"Unexpected ! {ex}")
        traceback.print_exc()


if __name__ == '__main__':
    import fire

    fire.Fire(main)
