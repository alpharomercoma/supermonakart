# Simulator capture script for the README pictures. make_media.py installs it
# as the __init__.py of a copy of the app and runs it with badgesim.py.
#
# It boots Super Mona Kart, unlocks the roster, drives the menus, lets the
# game's own AI race the player's kart (seeded, so every run is the same) and
# asks badgesim for a screenshot of chosen frames by adding the frame number to
# badgesim's SHOTS set. Each shot is logged as "<name> <frame>" in
# /state/shots.txt so the host can rename the PNGs.
import os
import sys

APP = "/system/apps/" + __file__.rsplit("/", 2)[-2]
os.chdir(APP)
sys.path.insert(0, APP)
badge.mode(HIRES | VSYNC)

import __main__
import game as G
from ai import Driver
from art import Art
from config import CHARACTERS
from progress import pick_rivals, unlocked
from rng import Rng

G.SAVE = "smk_capture"
game = G.Game(Art())
game.rng = Rng(2026)                  # the same races every run
game.save["unlocked"] = [c["key"] for c in CHARACTERS]

REAL = badge


class FakeBadge:
    def __init__(self):
        self.press = ()

    def pressed(self, b=None):
        if b is None:
            return REAL.pressed()
        return b in self.press or REAL.pressed(b)

    def __getattr__(self, name):
        return getattr(REAL, name)


fake = FakeBadge()
for name in ("game", "controls", "ui", "party", "race", "lights", "render", "art",
             "physics", "items", "net", "progress", "ai", "geom", "scenery"):
    m = sys.modules.get(name)
    if m is not None:
        setattr(m, "badge", fake)

PILOT = {"race": None, "drv": None, "skill": 0.95, "care": 0.5, "seed": 7}


def autopilot(dt, assist):
    r = game.race
    if PILOT["race"] is not r:
        PILOT["race"] = r
        PILOT["drv"] = Driver(r.karts[game.me], PILOT["skill"], 1.0, Rng(PILOT["seed"]),
                              drifts=True, care=PILOT["care"])
    steer, brake, drift, _throttle, use = PILOT["drv"].control(dt, r)
    return steer, brake, drift, use, False


game.controls.race = autopilot


try:
    os.mkdir("/state")
except OSError:
    pass
# Shot names go to a file, not a list: thousands of small strings kept alive
# would fragment the heap the game needs for its textures.
SHOT_LOG = open("/state/shots.txt", "w")


def shot(name):
    __main__.SHOTS.add(__main__.frame)
    SHOT_LOG.write("%s %d\n" % (name, __main__.frame))


def wait_ms(ms):
    end = badge.ticks + ms
    while badge.ticks < end:
        yield


def film(prefix, ms, every):
    """Shoot every `every`-th frame for `ms`; the frame just drawn is shot."""
    t0 = badge.ticks
    k = 0
    while badge.ticks - t0 < ms:
        if k % every == 0:
            shot("%s_%04d" % (prefix, k))
        k += 1
        yield


def script():
    # title and mode menu
    yield from wait_ms(2600)
    shot("title")
    fake.press = (BUTTON_SELECT,)
    yield
    yield from wait_ms(900)
    shot("menu")

    # every racer on the picker, the kart turning
    game.mode = G.GP
    game.go(G.CHARS, 0)
    yield
    for i in range(len(CHARACTERS)):
        game.cursor = i
        yield from film("chars%d" % i, 1400, 6)

    # the start of a quick race on each track
    for t, char in enumerate((0, 6, 4, 5)):          # Mona, Gopher, Tux, Ferris
        game.mode = G.QUICK
        game.char = char
        PILOT.update(skill=0.95, care=0.5, seed=7 + t)
        game.start_race(t)
        yield
        k = 0
        while game.state == G.INTRO:
            if k % 6 == 0:
                shot("t%d_intro_%04d" % (t, k))
            k += 1
            yield
        yield from film("t%d_race" % t, 14000, 3)

    # time trial: set a ghost, then chase it more slowly
    game.mode = G.TRIAL
    game.char = 4
    PILOT.update(skill=0.97, care=0.45, seed=3)
    game.start_race(2)
    yield
    while game.state != G.RESULTS:
        yield
    yield from wait_ms(1200)
    shot("tt_results")
    PILOT.update(skill=0.84, care=0.7, seed=11)
    game.start_race(2)
    yield
    yield from film("tt_ghost", 40000, 30)

    # a whole Grand Prix on Easy, to the podium
    game.mode = G.GP
    game.char = 0
    game.difficulty = 0
    game.cup_race = 0
    game.totals = {}
    game.last_order = []
    game.cup_rivals = pick_rivals(game.char, unlocked(game.save), game.rng)
    PILOT.update(skill=1.0, care=0.45, seed=5)
    game.start_race(0)
    yield
    done = set()
    while game.state != G.PODIUM:
        s = game.state
        if s == G.RESULTS and game.cup_race == 3 and game.since() > 900 and "gp_results" not in done:
            done.add("gp_results")
            shot("gp_results")
        if s == G.STANDINGS and game.cup_race == 3 and game.since() > 700 and "gp_standings" not in done:
            done.add("gp_standings")
            shot("gp_standings")
        if s in (G.RESULTS, G.STANDINGS) and game.since() > 1300:
            fake.press = (BUTTON_SELECT,)
        yield
    yield from film("podium", 3000, 6)
    print("@@PODIUM place=%d" % game.cup_place)


gen = script()


def update():
    game.update()
    fake.press = ()
    try:
        next(gen)
    except StopIteration:
        SHOT_LOG.close()
        return "done"
    except Exception as e:
        print("@@EXCEPTION state=%d" % game.state)
        sys.print_exception(e)
        return "exception"
    return None


def on_exit():
    game.exit()


run(update)
