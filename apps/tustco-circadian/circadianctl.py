#!/usr/bin/env python3
"""Control helper for Tustco Circadian alpha3."""

import argparse
import json
import os
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "config.json")
STATE_PATH = os.path.join(BASE, "state.json")


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default


def save_json(path, data):
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temp, path)


def current_target(config):
    sys.path.insert(0, BASE)
    from circadian import moon_window, schedule_at, sky_for, sun_events

    now = datetime.now()
    events = sun_events(now, config)
    moon = moon_window(now, config, events)
    sky_now = sky_for(now, config, events)
    scheduled = schedule_at(now, config, events)
    if sky_now.get("event"):
        target = {
            "color": str(sky_now["color"]).upper(),
            "dimmer": int(sky_now["dimmer"]),
            "source": "sky:{}".format(sky_now["event"]),
        }
    elif moon["active"]:
        target = {
            "color": str(config.get("moon", {}).get("color", "6E8CFF")).upper(),
            "dimmer": int(config.get("moon", {}).get("dimmer", 25)),
            "source": "full-moon",
        }
    else:
        target = {"color": scheduled[0], "dimmer": scheduled[1], "source": "schedule"}

    sun = None
    if events:
        sun = {
            "sunrise": events["sunrise_text"],
            "sunset": events["sunset_text"],
        }
    return sun, moon, sky_now, {"color": scheduled[0], "dimmer": scheduled[1]}, target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("status", help="show daemon state, sun, moon, sky events and target")
    sub.add_parser("pause", help="stop automatic changes until resumed")
    sub.add_parser("resume", help="return to the time schedule")
    sub.add_parser("clear", help="remove any manual preset override")

    preset = sub.add_parser("preset", help="hold a named preset until cleared")
    preset.add_argument("name", help="preset name from config.json")

    args = parser.parse_args()
    config = load_json(CONFIG_PATH, {})
    state = load_json(STATE_PATH, {"paused": False, "override": None})

    if args.action == "status":
        sun, moon, sky_now, schedule_now, target = current_target(config)
        if state.get("override"):
            target = dict(state["override"], source="override")
        print(json.dumps({
            "paused": state.get("paused", False),
            "override": state.get("override"),
            "sun": sun,
            "moon": moon,
            "sky": sky_now,
            "schedule_now": schedule_now,
            "target_now": target,
            "devices": config.get("devices", []),
        }, indent=2))
        return 0

    if args.action == "pause":
        state["paused"] = True
    elif args.action == "resume":
        state["paused"] = False
    elif args.action == "clear":
        state["override"] = None
    elif args.action == "preset":
        presets = config.get("presets", {})
        if args.name not in presets:
            print("Unknown preset. Available: {}".format(", ".join(sorted(presets))),
                  file=sys.stderr)
            return 2
        state["override"] = dict(presets[args.name])
        state["paused"] = False

    save_json(STATE_PATH, state)
    print(json.dumps(state, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
