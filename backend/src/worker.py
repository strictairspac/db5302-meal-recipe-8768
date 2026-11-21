import logging
import os
from pathlib import Path
from threading import Thread
from time import sleep

from src.config.settings import ARTIFACTS, cache, engine
from src.services.domain import solve
from src.services.workflow import claim, finish

HEARTBEAT = Path(ARTIFACTS) / 'worker-heartbeat'
# Concurrent runs are safe: claiming uses SKIP LOCKED and batches only
# contend on the ingredient rows they actually share while occupying.
THREADS = max(1, int(os.getenv('WORKER_THREADS', '4')))


def loop():
    while True:
        try:
            job = claim()
            HEARTBEAT.touch()
            if not job:
                cache.brpop('worker:wake', timeout=1)
                continue
            run_id, token, case_id, payload = job
            try:
                result = solve(payload, engine, case_id)
                finish(run_id, token, result=result)
            except (ValueError, KeyError, TypeError) as exc:
                finish(run_id, token, error=str(exc)[:500])
            except Exception:
                logging.exception('Domain run failed: %s', run_id)
                finish(run_id, token, error='后台执行失败，请检查输入或查看 worker 日志。')
        except Exception:
            logging.exception('Worker loop failure')
            sleep(2)


def work():
    HEARTBEAT.unlink(missing_ok=True)
    threads = [Thread(target=loop, daemon=True) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


if __name__ == '__main__':
    work()
