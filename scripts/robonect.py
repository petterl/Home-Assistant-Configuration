#!/usr/bin/env python3
"""robonect.py — a small, dependency-free client & CLI for the Robonect Hx/Hx+ HTTP API.

Robonect is an aftermarket WiFi module for Husqvarna/Gardena robotic mowers. It exposes
a JSON API (read + simple control) and a set of HTML settings pages (installation,
timer, etc.). This tool wraps both:

  * READ      — GET /json?cmd=<X>            (status, battery, gps, error, timer, ...)
  * CONTROL   — GET /json?cmd=mode&mode=<X>  (auto/man/home/eod), start, stop, reboot
  * SETTINGS  — the HTML pages save via a plain GET that submits EVERY form field at
                once (sending a subset blanks the rest). This tool reads the page,
                parses all fields, applies your overrides, resubmits the whole form,
                and verifies the result by reading it back.

Why this exists: Robonect's settings pages have no JSON setter, and a hand-written curl
that sends only the field you want silently drops the others. Parsing and resubmitting
the complete form is the reliable way — that's the core of `form-set` below.

NOTE: installation settings (exit, remote, corridor, ...) only save reliably when the
mower is idle/docked. While it is actively mowing the save request hangs/times out and
the value is not applied. `form-set` verifies by reading back and reports failure.

------------------------------------------------------------------------------------
CONFIGURATION (in priority order)
  1. CLI flags:        --host --user --password
  2. Environment:      ROBONECT_HOST  ROBONECT_USER  ROBONECT_PASS
  3. secrets.yaml:     keys `robonect_username`, `robonect_password`, optional
                       `robonect_host` (path via ROBONECT_SECRETS, default
                       /config/secrets.yaml). Parsed without a YAML dependency.
Host defaults to 192.168.4.71 if nothing sets it.

USAGE EXAMPLES
  robonect.py status                       # friendly summary
  robonect.py get battery                  # raw JSON for any cmd
  robonect.py get gps
  robonect.py errors --limit 5             # recent fault log
  robonect.py mode man                     # auto | man | home | eod
  robonect.py start                        # start / stop / reboot
  robonect.py form-show exit               # dump all fields of a settings page
  robonect.py exit-set --dist 205          # reversing distance (cm) when leaving dock
  robonect.py form-set exit dist=205       # generic: set any field(s) on any page
  robonect.py remote-show                  # remote-start points

As a library:
  from robonect import RobonectClient
  c = RobonectClient("192.168.4.71", "user", "pass")
  print(c.json_cmd("status"))
  c.set_mode("man"); c.start()
  c.save_form("exit", {"dist": 205})

This module uses only the Python standard library and is intended to be shareable.
"""

import argparse
import base64
import json
import os
import re
import sys
import urllib.parse
import urllib.request

DEFAULT_HOST = "192.168.4.71"
DEFAULT_SECRETS = os.environ.get("ROBONECT_SECRETS", "/config/secrets.yaml")

# Robonect status / mode code maps (for friendly output)
MODE_NAMES = {0: "AUTO", 1: "MAN", 2: "HOME", 3: "EOD"}
STATUS_NAMES = {
    0: "Detecting", 1: "Parked", 2: "Mowing", 3: "Searching dock", 4: "Charging",
    5: "Searching", 7: "Error", 8: "Lost loop", 16: "Off", 17: "Sleeping",
}
PATH_NAMES = {0: "Boundary right", 1: "Boundary left", 2: "Guide"}


class RobonectError(Exception):
    """Raised when the Robonect unit returns an unsuccessful response."""


class RobonectClient:
    """Minimal HTTP client for a Robonect module (HTTP Basic auth)."""

    def __init__(self, host, user, password, timeout=10):
        self.host = host
        self.user = user
        self.password = password
        self.timeout = timeout

    # ---- low level -----------------------------------------------------------
    def _get(self, path):
        """GET an absolute path on the unit; returns the response as a str (latin-1)."""
        url = "http://%s/%s" % (self.host, path.lstrip("/"))
        req = urllib.request.Request(url)
        token = base64.b64encode(("%s:%s" % (self.user, self.password)).encode()).decode()
        req.add_header("Authorization", "Basic " + token)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            # Robonect serves latin-1 (e.g. ° in GPS NMEA strings). Decode tolerantly.
            return resp.read().decode("latin-1")

    # ---- JSON API ------------------------------------------------------------
    def json_cmd(self, cmd, **params):
        """Call GET /json?cmd=<cmd>[&k=v...] and return the parsed dict.

        Does not raise on {"successful": false} — callers inspect the dict, since
        some "errors" are informational (e.g. cmd=gps when no module is fitted)."""
        query = {"cmd": cmd}
        query.update({k: v for k, v in params.items() if v is not None})
        return json.loads(self._get("json?" + urllib.parse.urlencode(query)))

    def require(self, cmd, **params):
        """Like json_cmd but raise RobonectError if successful is not True."""
        data = self.json_cmd(cmd, **params)
        if not data.get("successful", False):
            raise RobonectError("cmd=%s failed: %s" % (cmd, data))
        return data

    # ---- control -------------------------------------------------------------
    def set_mode(self, mode):
        """mode = auto | man | home | eod"""
        return self.require("mode", mode=mode)

    def start(self):
        return self.require("start")

    def stop(self):
        return self.require("stop")

    def reboot(self):
        # The reboot action is a bare flag, not service=reboot.
        return json.loads(self._get("json?cmd=service&reboot"))

    # ---- HTML settings forms -------------------------------------------------
    def page(self, path):
        """Fetch a settings page and return its HTML (str)."""
        return self._get(path)

    @staticmethod
    def _attr(tag, name):
        m = re.search(r'\b%s="([^"]*)"' % re.escape(name), tag, re.I)
        return m.group(1) if m else None

    def parse_fields(self, html):
        """Parse every submittable form field on a settings page, in document order.

        Returns a list of (name, value) tuples mimicking what a browser would submit:
        text/number/range/hidden -> value; checkbox/radio -> included only if checked;
        select -> the selected option's value (or first option). submit/button skipped."""
        fields = []
        token_re = re.compile(r"<input\b[^>]*>|<select\b[^>]*>.*?</select>", re.S | re.I)
        for m in token_re.finditer(html):
            tag = m.group(0)
            name = self._attr(tag, "name")
            if not name:
                continue
            if tag[:6].lower() == "<input":
                typ = (self._attr(tag, "type") or "text").lower()
                if typ in ("submit", "button", "image", "file", "reset"):
                    continue
                if typ in ("checkbox", "radio"):
                    if re.search(r"\bchecked\b", tag, re.I):
                        fields.append((name, self._attr(tag, "value") or "on"))
                else:
                    fields.append((name, self._attr(tag, "value") or ""))
            else:  # <select>
                sel = re.search(r'<option\s+value="([^"]*)"[^>]*\bselected', tag, re.I)
                if not sel:
                    sel = re.search(r'<option\s+value="([^"]*)"', tag, re.I)
                fields.append((name, sel.group(1) if sel else ""))
        return fields

    def save_form(self, page, overrides, verify=True):
        """Read a settings page, resubmit ALL fields with `overrides` applied, verify.

        page      -- page name without slash, e.g. "exit", "remote", "timer".
        overrides -- {field_name: value} to change.
        Returns {"sent": [...], "verify": {field: {"requested","actual","ok"}}}.

        Resubmitting the complete form is required: Robonect blanks any field not
        present in the save request."""
        overrides = {k: str(v) for k, v in overrides.items()}
        current = self.parse_fields(self.page(page))
        sent, applied = [], set()
        for name, value in current:
            if name in overrides:
                sent.append((name, overrides[name]))
                applied.add(name)
            else:
                sent.append((name, value))
        # overrides that were not already present (e.g. a checkbox currently off)
        for name, value in overrides.items():
            if name not in applied:
                sent.append((name, value))
        sent.append(("save", ""))
        self._get(page + "?" + urllib.parse.urlencode(sent))

        result = {"sent": sent, "verify": {}}
        if verify:
            after = dict(self.parse_fields(self.page(page)))
            for name in overrides:
                actual = after.get(name)
                result["verify"][name] = {
                    "requested": overrides[name],
                    "actual": actual,
                    "ok": actual == overrides[name],
                }
        return result


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------
def _read_secrets(path):
    """Tiny, dependency-free reader for robonect_* keys in a secrets.yaml."""
    out = {}
    try:
        with open(path) as fh:
            for line in fh:
                m = re.match(r'\s*(robonect_(?:host|username|password))\s*:\s*"?([^"\n]+?)"?\s*$', line)
                if m:
                    out[m.group(1)] = m.group(2)
    except OSError:
        pass
    return out


def make_client(args):
    secrets = _read_secrets(DEFAULT_SECRETS)
    host = args.host or os.environ.get("ROBONECT_HOST") or secrets.get("robonect_host") or DEFAULT_HOST
    user = args.user or os.environ.get("ROBONECT_USER") or secrets.get("robonect_username")
    pw = args.password or os.environ.get("ROBONECT_PASS") or secrets.get("robonect_password")
    if not (user and pw):
        sys.exit("Saknar inloggning. Sätt ROBONECT_USER/ROBONECT_PASS (+ev ROBONECT_HOST) "
                 "eller --user/--password/--host, eller robonect_username/password i %s." % DEFAULT_SECRETS)
    return RobonectClient(host, user, pw)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _print_json(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def cmd_status(c, args):
    s = c.require("status")["status"]
    print("Mode:    %s (%s)" % (s["mode"], MODE_NAMES.get(s["mode"], "?")))
    print("Status:  %s (%s)" % (s["status"], STATUS_NAMES.get(s["status"], "?")))
    print("Battery: %s%%" % s["battery"])
    print("Stopped: %s   Home: %s   Distance: %s m" % (s["stopped"], s["home"], s["distance"]))


def cmd_get(c, args):
    params = {}
    for kv in args.param or []:
        k, _, v = kv.partition("=")
        params[k] = v
    _print_json(c.json_cmd(args.cmd, **params))


def cmd_errors(c, args):
    errs = c.json_cmd("error").get("errors", [])
    for e in errs[: args.limit]:
        print("%s %s  kod %3s  %s" % (e["date"], e["time"], e["error_code"], e["error_message"]))


def cmd_mode(c, args):
    _print_json(c.set_mode(args.mode))


def cmd_simple(c, args):
    _print_json(getattr(c, args._action)())


def cmd_form_show(c, args):
    for name, value in c.parse_fields(c.page(args.page)):
        print("%-14s = %s" % (name, value))


def cmd_form_set(c, args):
    overrides = {}
    for kv in args.assignments:
        k, _, v = kv.partition("=")
        overrides[k] = v
    res = c.save_form(args.page, overrides)
    for name, info in res["verify"].items():
        mark = "OK" if info["ok"] else "MISSLYCKADES"
        print("%s: begärt %s -> faktiskt %s  [%s]" % (name, info["requested"], info["actual"], mark))
    if not all(v["ok"] for v in res["verify"].values()):
        print("\nOBS: vissa fält ändrades inte. Vanlig orsak: mowern måste vara dockad/"
              "stillastående för att spara installationsinställningar.", file=sys.stderr)
        sys.exit(1)


def cmd_exit_show(c, args):
    cmd_form_show(c, argparse.Namespace(page="exit"))


def cmd_exit_set(c, args):
    cmd_form_set(c, argparse.Namespace(page="exit", assignments=["dist=%d" % args.dist]))


def cmd_remote_show(c, args):
    d = c.json_cmd("remote")
    total = 0
    for i in range(1, 6):
        p = d.get("remotestart_%d" % i)
        if p:
            total += p["proportion"]
            print("Fernstart %d: %-14s %3d%%  %3dm  visible=%s"
                  % (i, PATH_NAMES.get(p["path"], "?"), p["proportion"], p["distance"], p["visible"]))
    print("Sum: %d%%  (from dock: %d%%)" % (total, 100 - total))


def build_parser():
    p = argparse.ArgumentParser(description="Robonect Hx/Hx+ client & CLI.")
    p.add_argument("--host")
    p.add_argument("--user")
    p.add_argument("--password")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("status", help="friendly status summary")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("get", help="raw JSON for any cmd (status, battery, gps, timer, ...)")
    sp.add_argument("cmd")
    sp.add_argument("--param", action="append", help="extra query param k=v (repeatable)")
    sp.set_defaults(func=cmd_get)

    # named read shortcuts -> get
    for name in ("version", "battery", "gps", "timer", "motor", "health", "ext",
                 "push", "wlan", "weather", "portal", "name", "clock", "hour"):
        s = sub.add_parser(name, help="GET /json?cmd=%s" % name)
        s.set_defaults(func=cmd_get, cmd=name, param=None)

    sp = sub.add_parser("errors", help="recent fault log")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(func=cmd_errors)

    sp = sub.add_parser("mode", help="set operation mode")
    sp.add_argument("mode", choices=["auto", "man", "home", "eod"])
    sp.set_defaults(func=cmd_mode)

    for action in ("start", "stop", "reboot"):
        s = sub.add_parser(action, help="%s the mower" % action)
        s.set_defaults(func=cmd_simple, _action=action)

    sp = sub.add_parser("form-show", help="dump all fields of a settings page")
    sp.add_argument("page", help="page name, e.g. exit, remote, timer, corridor, equipment")
    sp.set_defaults(func=cmd_form_show)

    sp = sub.add_parser("form-set", help="set field(s) on any settings page (resubmits whole form)")
    sp.add_argument("page")
    sp.add_argument("assignments", nargs="+", help="NAME=VALUE ...")
    sp.set_defaults(func=cmd_form_set)

    sp = sub.add_parser("exit-show", help="show charging-station exit / reversing settings")
    sp.set_defaults(func=cmd_exit_show)

    sp = sub.add_parser("exit-set", help="set reversing distance (cm) when leaving the dock")
    sp.add_argument("--dist", type=int, required=True, help="reversing distance in cm (15-600, step 5)")
    sp.set_defaults(func=cmd_exit_set)

    sp = sub.add_parser("remote-show", help="show remote-start points")
    sp.set_defaults(func=cmd_remote_show)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    client = make_client(args)
    try:
        args.func(client, args)
    except RobonectError as e:
        sys.exit("Robonect-fel: %s" % e)
    except (TimeoutError, urllib.error.URLError, OSError) as e:
        sys.exit("Kommunikationsfel mot %s: %s\n(Tips: installationsinställningar "
                 "som exit/remote/corridor verkar bara gå att spara när mowern står "
                 "stilla/dockad — under klippning hänger sparningen och tar inte.)"
                 % (client.host, e))


if __name__ == "__main__":
    main()
