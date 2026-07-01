"""
Thread-safe print() wrapper shared by pipeline.py.

Console output was cut down to one line per criterion — "<variant> | <criterion>
| applies=<bool>" — printed from process_criterion() in pipeline.py, plus a
handful of batch-level progress lines in run_pipeline_batch(). Every one of
those lines already embeds the variant string itself, so there's no need for
the automatic per-thread "[variant]" prefixing this module used to do; log()
now just holds a lock around print() so concurrent variants (via the
ThreadPoolExecutor in run_pipeline_batch) can't interleave two lines into a
garbled one on stdout.

All the verbose per-tool-call logging that used to live in agents/*.py and
tools/*.py has been removed — full reasoning/evidence for every criterion is
still written out in full to the batch JSON output (see save_results() in
pipeline.py), just not printed to the console anymore.
"""
import threading

_print_lock = threading.Lock()


def log(*args, sep: str = " ", **kwargs) -> None:
    """Drop-in replacement for print() that's safe to call from multiple
    concurrently-running variant threads without interleaving output."""
    message = sep.join(str(a) for a in args)
    with _print_lock:
        print(message, **kwargs)
