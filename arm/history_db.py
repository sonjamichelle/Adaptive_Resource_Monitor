# Adaptive Resource Monitor
# Original developer: Sonja M Thomas
# Copyright 2010-2026 SLT Design Creations, LLC
# Licensed under the Design Creations Attribution-NonCommercial-ShareAlike License v1.0.
# See LICENSE.md for complete license terms.
# https://www.designcreations.us/

"""SQLite activity is confined to one background thread."""
from contextlib import closing
from pathlib import Path
from queue import Empty, Full, Queue
import logging
import sqlite3
import threading
from time import monotonic, time

from .model import Availability, Reading

LOG = logging.getLogger(__name__)
BATCH_SECONDS = 4
SQL_INSERT = "INSERT OR IGNORE INTO readings VALUES (?,?,?,?,?,?,?,?)"
SQL_SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
  machine TEXT, device TEXT, metric TEXT, stamp REAL, value REAL, unit TEXT,
  status TEXT, detail TEXT, PRIMARY KEY (machine,device,metric,stamp)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS retention ON readings(stamp);
"""


class HistoryDb:
    def __init__(self, path, retention, maximum, deliver, failure, previous=None):
        self.path = Path(path)
        self.retention = retention
        self.maximum = maximum * 1024 * 1024
        self.deliver, self.failure = deliver, failure
        self.previous = previous
        self.tasks = Queue(maxsize=128)
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.run, name="ARM history")
        self.thread.start()

    def send(self, operation, args=None):
        if not self.stopping.is_set():
            try:
                self.tasks.put_nowait((operation, args))
                return True
            except Full:
                self.failure("History queue is full")
        return False

    def record(self, readings):
        if readings:
            self.send("record", readings)

    def request(self, token, keys, cutoff):
        self.send("request", (token, tuple(keys), cutoff))

    def stop(self):
        self.stopping.set()

    def close(self):
        self.stop()
        self.thread.join()

    def run(self):
        previous, self.previous = self.previous, None
        if previous:
            previous.thread.join()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.path, timeout=2)) as connection:
                self.operate(connection)
        except (OSError, sqlite3.Error) as exc:
            message = f"History database failed ({type(exc).__name__}: {exc})"
            LOG.error("%s", message)
            self.failure(message)

    def operate(self, conn):
        conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA journal_size_limit=4194304")
        conn.executescript(SQL_SCHEMA)
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        pending = []
        last_flush = monotonic()
        self.trim(conn, page_size)
        last_trim = monotonic()
        while not self.stopping.is_set() or not self.tasks.empty():
            try:
                operation, args = self.tasks.get(timeout=.25)
            except Empty:
                operation, args = "", None
            if operation == "record":
                pending.extend(
                    (r.machine, r.device, r.metric, r.timestamp, r.value, r.unit, r.availability.value, r.diagnostic)
                    for r in args
                )
            elif operation == "clear":
                pending.clear()
                with conn:
                    conn.execute("DELETE FROM readings")
                conn.execute("VACUUM")
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self.deliver(args, {})
            elif operation == "request":
                token, keys, cutoff = args
                result = {}
                with conn:
                    for key in keys:
                        # Bound how much history is loaded for each requested plot.
                        # Group older sequences by time, preserving real peak observations.
                        step = max(1, (time() - cutoff) / 2000)
                        sql = (
                            "SELECT stamp,value,unit,status,detail,max(coalesce(value,-1)) "
                            "FROM readings WHERE machine=? AND device=? AND metric=? AND stamp>=? "
                            "GROUP BY cast((stamp-?)/? as integer) ORDER BY stamp"
                        )
                        rows = conn.execute(sql, (*key, cutoff, cutoff, step))
                        result[key] = [Reading(*key, value, unit, stamp, Availability(status), detail)
                                       for stamp, value, unit, status, detail, _ in rows]
                self.deliver(token, result)
            tick = monotonic()
            if pending and (tick - last_flush >= BATCH_SECONDS or len(pending) >= 12000):
                self.flush(conn, pending)
                last_flush = tick
            if tick - last_trim >= 60:
                self.trim(conn, page_size)
                last_trim = tick
        self.flush(conn, pending)
        self.trim(conn, page_size)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    @staticmethod
    def flush(conn, pending):
        if pending:
            with conn:
                conn.executemany(SQL_INSERT, pending)
            pending.clear()

    def trim(self, conn, page_size):
        cutoff = time() - self.retention * 86400
        with conn:
            conn.execute("DELETE FROM readings WHERE stamp<?", (cutoff,))
            pages = conn.execute("PRAGMA page_count").fetchone()[0]
            if pages * page_size > self.maximum:
                free = conn.execute("PRAGMA freelist_count").fetchone()[0]
                count = conn.execute("SELECT count(*) FROM readings").fetchone()[0]
                fraction = max(0, 1 - (self.maximum * .90 / (max(1, pages - free) * page_size)))
                if fraction and count:
                    position = min(count - 1, int(fraction * count))
                    oldest = conn.execute("SELECT stamp FROM readings ORDER BY stamp LIMIT 1 OFFSET ?",
                                          (position,)).fetchone()
                    if oldest:
                        conn.execute("DELETE FROM readings WHERE stamp<=?", oldest)
        if pages * page_size > self.maximum:
            conn.execute("VACUUM")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
