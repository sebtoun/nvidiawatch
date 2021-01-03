from datetime import datetime
import time
from playsound import playsound
from typing import List, Union, Iterable
from concurrent.futures import ThreadPoolExecutor, Future
import curses
from stockscan import Scanner, HardwareFrScanner, LDLCScanner, NvidiaScanner, TopAchatScanner, RueDuCommerceScanner, \
    MaterielNetScanner, CaseKingScanner, AlternateScanner, DummyScanner
import traceback
import threading


def loop(file):
    while True:
        playsound(file)


class ExitException(Exception):
    pass


class StockMonitor:
    def __init__(self, scanners: List[Scanner], update_freq=10, max_thread=8):
        self._update_freq = update_freq
        self._scanners = scanners
        self._update_results: Union[Iterable[Future], None] = None
        self._last_update_time = None

        # update thread
        self.pool = ThreadPoolExecutor(min(max_thread, len(scanners)))
        self._update_thread = None
        self.stop_update = False

    def _update_scanners(self):
        def update_scanner(scanner: Scanner):
            scanner.update()

        self._last_update_time = datetime.now()
        self._update_results = [self.pool.submit(update_scanner, scanner) for scanner in self._scanners]

    def _update_loop(self):
        self._update_scanners()
        while not self.stop_update:
            update_pending = any(map(lambda f: not f.done(), self._update_results))
            delay_elapsed = (datetime.now() - self._last_update_time).total_seconds() >= self._update_freq
            if update_pending or not delay_elapsed:
                time.sleep(0.5)
            else:
                self._update_scanners()

    def clear_errors(self):
        for scanner in self._scanners:
            scanner.clear_last_error()

    def start(self):
        assert self._update_thread is None
        self.stop_update = False
        self._update_thread = threading.Thread(target=self._update_loop)
        self._update_thread.start()

    def terminate(self):
        if self._update_thread is not None:
            self.stop_update = True
            self._update_thread.join()
        self.pool.shutdown(wait=False)
        if self._update_results is not None:
            for f in self._update_results:
                if not f.done():
                    f.cancel()

    @property
    def scanners(self):
        return self._scanners


class Main:
    MAX_FAIL = 5

    def __init__(self, monitor: StockMonitor, silent=False):
        self.monitor = monitor
        self.silent = silent

        # notifications
        self._notification_thread = None

        # init layout
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_RED, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)

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
            "state_attributes": {
                Scanner.InStock: curses.A_STANDOUT | curses.color_pair(2),
                Scanner.Unavailable: 0,
                Scanner.Error: curses.A_STANDOUT | curses.color_pair(1)
            },
            "time_format": time_format
        }

    def _play_loop(self, file):
        if not self.silent and self._notification_thread is None:
            self._notification_thread = threading.Thread(target=loop,
                                                         args=(file,))
            self._notification_thread.start()

    def _play_ok_sound(self):
        self._play_loop("data/whohoo.mp3")

    def _play_error_sound(self):
        self._play_loop("data/nooo.mp3")

    def _notifications(self):
        def has_stock(s: Scanner):
            return s.in_stock

        def has_errors(s: Scanner):
            return s.consecutive_errors >= Main.MAX_FAIL

        if any(map(has_stock, self.monitor.scanners)):
            self._play_ok_sound()
        elif any(map(has_errors, self.monitor.scanners)):
            self._play_error_sound()

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

        y += padding[1] + 1
        for i, scanner in enumerate(self.monitor.scanners):
            x = padding[0]

            stdscr.addstr(y, x, scanner.name)
            x += columns[0][1] + padding[0]

            state = self.layout["state_names"][scanner.last_sate]
            if scanner.has_error:
                state += f" #{'>' if scanner.consecutive_errors > 9 else ''}{min(9, scanner.consecutive_errors)}"
            stdscr.addstr(y, x,
                          state,
                          self.layout["state_attributes"][scanner.last_sate])
            x += columns[1][1] + padding[0]

            if scanner.last_scan_time is not None:
                elapsed = datetime.now() - scanner.last_scan_time
                stdscr.addstr(y, x, f"{int(elapsed.total_seconds()):>2}s ago")
            x += columns[2][1] + padding[0]

            time_format = self.layout["time_format"]
            if scanner.last_stock_time is not None:
                stdscr.addstr(y, x, scanner.last_stock_time.strftime(time_format))
            x += columns[3][1] + padding[0]

            try:
                detail = f"{scanner.watched_item_count} items watched"
            except:
                detail = None
            if scanner.last_error is not None:
                stdscr.addstr(y, x, f"{scanner.last_error}")
            elif detail is not None:
                stdscr.addstr(y, x, detail)

            stdscr.addstr(y + 1, padding[0],
                          f"\tCheck {scanner.user_url}")

            y += 3

        stdscr.addstr(y, padding[0],
                      f"[press 'q' to quit, 'c' to clear errors]")

        stdscr.refresh()
        # handle user inputs (quit)
        stdscr.nodelay(True)
        try:
            key = stdscr.getkey()
        except:
            key = None
        if key == "q":
            raise ExitException
        elif key == 'c':
            self.monitor.clear_errors()


if __name__ == '__main__':
    try:
        UPDATE_FREQ = 10
        Scanner.DefaultTimeout = UPDATE_FREQ
        scanners = [
            HardwareFrScanner("evga 3080"),
            LDLCScanner("evga 3080"),
            # LDLCScanner("amd ryzen 5900x -kit"),
            NvidiaScanner("3080"),
            NvidiaScanner("3090"),
            TopAchatScanner("evga 3080"),
            # TopAchatScanner("amd ryzen 5900x -kit"),
            RueDuCommerceScanner(),
            MaterielNetScanner(),
            CaseKingScanner("evga 3080"),
            AlternateScanner("evga 3080"),
            # DummyScanner(delay=1, error=2, stocks=2),
            # DummyScanner(delay=1, error=2, stocks=2),
            # DummyScanner(delay=1, error=100, stocks=2),
        ]

        def main(stdscr):
            monitor = StockMonitor(scanners, update_freq=UPDATE_FREQ, max_thread=8)
            app = Main(monitor, silent=True)
            try:
                monitor.start()
                while True:
                    app.draw(stdscr)
                    time.sleep(1.0 / 10)
            except ExitException:
                pass
            finally:
                monitor.terminate()

        curses.wrapper(main)
        print("exiting...")

    except Exception as ex:
        print(f"Unexpected ! {ex}")
        traceback.print_exc()
