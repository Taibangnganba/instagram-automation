"""Decide whether to make clips now and, if so, from which source video."""
from common import load_config, load_processed, load_sources, ready_clips, set_output


def pick():
    cfg = load_config()
    ready = len(ready_clips())
    if ready >= cfg["min_ready_clips"]:
        return None, f"{ready} clips already waiting (min_ready_clips={cfg['min_ready_clips']})"
    done = load_processed()
    for url, credit in load_sources():
        if url not in done:
            return (url, credit), f"{ready} clips waiting, making more"
    return None, "sources.txt has no unprocessed videos - add more links"


if __name__ == "__main__":
    cfg = load_config()
    source, reason = pick()
    print(reason)
    if source:
        set_output(run="true", url=source[0], credit=source[1],
                   max_source_minutes=cfg["max_source_minutes"],
                   auto_hook="1" if cfg["auto_hook"] else "0")
    else:
        set_output(run="false")
