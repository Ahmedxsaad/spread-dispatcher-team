"""Draws the three diagrams of the README as Excalidraw scenes.

    python3 docs/diagrams/draw.py      # writes the .excalidraw files beside this script

Each diagram has its boxes on the left and, beside each numbered step, a note: what happens there, and what
it was measured to be worth. The PNG and SVG files are rendered from the scenes; drop a .excalidraw file on
excalidraw.com to edit one by hand.
"""
from __future__ import annotations

import json
import zlib
from pathlib import Path

HERE = Path(__file__).parent
INK, GRAY, GOOD = "#1e1e1e", "#626a71", "#227231"
# What a colour means, in all three diagrams: (border, fill, text, tint of its zone).
COLOURS = {
    "comes in": ("#1971c2", "#a5d8ff", "#145a9b", "#e7f5ff"),
    "measured": ("#0c8599", "#99e9f2", "#096877", "#e3fafc"),
    "decides": ("#6741d9", "#d0bfff", "#5938bb", "#f3f0ff"),
    "risk": ("#e03131", "#ffc9c9", "#af2626", "#fff5f5"),
    "result": ("#2f9e44", "#b2f2bb", "#227231", "#ebfbee"),
    "outside": ("#495057", "#e9ecef", "#343a40", "#f8f9fa"),
}
MIDDLE, LEFT, RIGHT, WIDE = 330, 165, 495, 660   # the boxes' columns, and the width of a zone
NOTES = 760                                       # where the notes' column starts
GAP = 4                                           # between an arrow's end and the box it touches


class Scene:
    def __init__(self, title: str, subtitle: str):
        self.zones, self.lines, self.boxes, self.marks = [], [], [], []
        self.text(self.marks, "title", 0, 0, title, 36)
        self.text(self.marks, "subtitle", 0, 56, subtitle, 20, GRAY)

    def item(self, layer: list, name: str, kind: str, x: float, y: float, w: float, h: float, **more) -> dict:
        item = {"id": name, "type": kind, "x": x, "y": y, "width": w, "height": h, "angle": 0, "strokeColor": INK,
                "backgroundColor": "transparent", "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
                "roughness": 1, "opacity": 100, "groupIds": [], "frameId": None, "roundness": None,
                "seed": zlib.crc32(name.encode()), "version": 1, "versionNonce": zlib.crc32(name[::-1].encode()),
                "isDeleted": False, "boundElements": None, "updated": 1, "link": None, "locked": False, **more}
        layer.append(item)
        return item

    def text(self, layer: list, name: str, x: float, y: float, words: str, size: int = 18, colour: str = INK,
             inside: dict | None = None) -> dict:
        rows = words.split("\n")
        w, h = max(len(row) for row in rows) * size * 0.6, len(rows) * size * 1.25
        if inside:
            x, y = inside["x"] + (inside["width"] - w) / 2, inside["y"] + (inside["height"] - h) / 2
            inside["boundElements"] = (inside["boundElements"] or []) + [{"type": "text", "id": name}]
        return self.item(layer, name, "text", x, y, w, h, strokeColor=colour, strokeWidth=1, text=words,
                         originalText=words, fontSize=size, fontFamily=5, textAlign="center" if inside else "left",
                         verticalAlign="middle" if inside else "top", containerId=inside["id"] if inside else None,
                         autoResize=True, lineHeight=1.25)

    def zone(self, name: str, y: float, h: float, colour: str) -> None:
        border, _, ink, tint = COLOURS[colour]
        self.item(self.zones, name, "rectangle", 0, y, WIDE, h, strokeColor=border, backgroundColor=tint,
                  strokeWidth=1, strokeStyle="dashed", roundness={"type": 3})
        self.text(self.zones, name + "-title", 20, y + 16, name.upper(), 20, ink)

    def box(self, name: str, centre: float, y: float, w: float, words: str, colour: str, kind: str = "rectangle",
            bold: bool = False, h: float = 84) -> dict:
        border, fill, ink, _ = COLOURS[colour]
        box = self.item(self.boxes, name, kind, centre - w / 2, y, w, h, strokeColor=border, backgroundColor=fill,
                        strokeWidth=4 if bold else 2, roundness={"type": 3} if kind == "rectangle" else None)
        self.text(self.boxes, name + "-label", 0, 0, words, 18, ink, inside=box)
        return box

    def arrow(self, points: list, start: dict | None = None, end: dict | None = None, style: str = "solid",
              head: str | None = "arrow", colour: str = INK, name: str = "") -> None:
        name = name or f"arrow-{len(self.lines)}"
        (x, y), ends = points[0], {"startBinding": start, "endBinding": end}
        steps = [[px - x, py - y] for px, py in points]
        for key, box in ends.items():
            if box:
                box["boundElements"] = (box["boundElements"] or []) + [{"type": "arrow", "id": name}]
                ends[key] = {"elementId": box["id"], "focus": 0, "gap": GAP, "fixedPoint": None}
        self.item(self.lines, name, "arrow", x, y, max(px for px, _ in steps) - min(px for px, _ in steps),
                  max(py for _, py in steps) - min(py for _, py in steps), strokeColor=colour, strokeStyle=style,
                  points=steps, lastCommittedPoint=None, startArrowhead=None, endArrowhead=head, elbowed=False, **ends)

    def down(self, above: dict, below: dict, x: float = MIDDLE, **more) -> float:
        """An arrow straight down from one box to the next. Returns the height of its middle, for the badge."""
        top, bottom = above["y"] + above["height"] + GAP, below["y"] - GAP
        self.arrow([(x, top), (x, bottom)], above, below, **more)
        return (top + bottom) / 2

    def badge(self, number: int | str, x: float, y: float, size: int = 44, name: str = "step") -> dict:
        badge = self.item(self.marks, f"{name}-{number}", "ellipse", x - size / 2, y - size / 2, size, size,
                          backgroundColor="#fff3bf", roughness=0)
        self.text(self.marks, f"{name}-{number}-label", 0, 0, str(number), 16, inside=badge)
        return badge

    def note(self, number: int | str, y: float, head: str, rows: list[str], effect: str = "") -> None:
        """A numbered note in the right column, centred on the height y: what happens, and its measured effect."""
        y -= (27.5 + 22.5 * (len(rows) + bool(effect))) / 2
        self.badge(number, NOTES + 20, y + 14, 40, "note")
        self.text(self.marks, f"note-{number}-head", NOTES + 56, y, head, 22)
        for i, row in enumerate(rows):
            self.text(self.marks, f"note-{number}-row-{i}", NOTES + 56, y + 30 + 22.5 * i, row, 18, GRAY)
        if effect:
            self.text(self.marks, f"note-{number}-effect", NOTES + 56, y + 30 + 22.5 * len(rows), effect, 18, GOOD)

    def legend(self, y: float, entries: list[tuple[str, str]]) -> None:
        x = 0
        for i, (sign, words) in enumerate(entries):
            if sign == "dashed":
                self.arrow([(x, y + 14), (x + 60, y + 14)], style="dashed", name=f"legend-{i}")
            elif sign == "bold":
                self.item(self.marks, f"legend-{i}", "rectangle", x, y, 60, 28, strokeWidth=4, roundness={"type": 3})
            else:
                border, fill, _, _ = COLOURS[sign]
                self.item(self.marks, f"legend-{i}", "rectangle", x, y, 60, 28, strokeColor=border,
                          backgroundColor=fill, roundness={"type": 3})
            words = self.text(self.marks, f"legend-{i}-words", x + 76, y + 3, words, 18, GRAY)
            x += 76 + words["width"] + 48

    def save(self, name: str) -> None:
        scene = {"type": "excalidraw", "version": 2, "source": "docs/diagrams/draw.py",
                 "elements": self.zones + self.lines + self.boxes + self.marks,
                 "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20}, "files": {}}
        (HERE / f"{name}.excalidraw").write_text(json.dumps(scene, indent=1) + "\n")


def how_the_desk_decides() -> None:
    s = Scene("How the desk decides", "one request, one price, one gig: two estimates, one rule, one guard")

    s.zone("read", 120, 348, "comes in")
    request = s.box("request", MIDDLE, 176, 360, "A dealer's request\nlane · options · note", "comes in", "ellipse")
    reader = s.box("reader", MIDDLE, 356, 320, "Notes reader\nFinnish · Swedish · English", "comes in")
    s.badge(1, MIDDLE, s.down(request, reader))
    s.note(1, 308, "A dealer asks for a price",
           ["a lane, its options, a note in three languages.", "The answer is due in 15 world minutes: 4.5 s in the final"])

    s.zone("estimate", 568, 168, "measured")
    drivers = s.box("drivers", LEFT, 624, 270, "Driver curve\na driver in time?", "measured")
    dealers = s.box("dealers", RIGHT, 624, 270, "Dealer curve\ntakes this price?", "measured")
    fork = s.badge(2, MIDDLE, 530)
    s.arrow([(MIDDLE, 440 + GAP), (MIDDLE, 508 - GAP)], reader, fork, head=None)
    for curve, x, side in ((drivers, LEFT, -1), (dealers, RIGHT, 1)):
        s.arrow([(MIDDLE + side * (22 + GAP), 530), (x, 530), (x, 624 - GAP)], fork, curve)
    s.note(2, 530, "The note is read first",
           ["it can move the ready time, the opening hours,", "the deadline, or ask for plates or a manual licence"],
           "+€1,850 a week · 99.97% of 3,963 unseen notes right")

    s.zone("decide", 812, 348, "decides")
    rule = s.box("rule", MIDDLE, 868, 500, "Price rule\nthe price with the highest expected profit", "decides", bold=True)
    guard = s.box("guard", MIDDLE, 1048, 320, "Guard\nroom left in the week?", "risk", bold=True)
    for number, curve, x in ((3, drivers, LEFT), (4, dealers, RIGHT)):
        s.down(curve, rule, x)
        s.badge(number, x, 774)
    s.note(3, 716, "Will a driver take the car in time?",
           ["a logistic curve fitted on 29,597 orders gives the", "opening fee with the lowest expected cost"])
    s.note(4, 826, "Will the dealer take the price?",
           ["a curve for each lane; the day's level is learned", "from every quote that wins or loses"],
           "+€314 a week for following the competitor's moves")
    s.badge(5, MIDDLE, s.down(rule, guard))
    s.note(5, 1000, "One rule: the highest expected profit",
           ["the chance that the dealer takes the price, times", "what the price leaves after the driver's cost"],
           "the kit starter loses €66,760 a week; this rule makes €9,039")

    s.zone("act", 1236, 348, "result")
    quote = s.box("quote", MIDDLE, 1292, 300, "Quote\na price for each option", "result")
    gig = s.box("gig", MIDDLE, 1472, 300, "Gig for the drivers\nalone or in a pair", "result")
    s.down(guard, quote)
    s.badge(6, MIDDLE, 1198)
    s.note(6, 1198, "One guard: the week stays ranked",
           ["never more cars due on one day than the week", "can afford to lose a quarter of"],
           "lowest of 40 weeks: 91.3% on time before, 94.1% after")
    s.badge(7, MIDDLE, s.down(quote, gig))
    s.note(7, 1424, "Won: the car becomes a gig",
           ["two cars in one gig when the second starts where", "the first ends; the fee rises in two steps"],
           "return-trip pairs: +€1,224 a week, then +€1,064")

    # Each answer teaches the dealer curve: a dashed line back, outside the zones.
    s.arrow([(480 + GAP, 1334), (700, 1334), (700, 666), (630 + GAP, 666)], quote, dealers, style="dashed")
    s.legend(1624, [("dashed", "each win or loss moves the day's price level"), ("bold", "where the margin is decided"),
                    ("risk", "keeps 90% of the orders on time")])
    s.save("how-the-desk-decides")


def how_an_idea_becomes_a_default() -> None:
    s = Scene("How an idea becomes a default",
              "11,651 practice weeks under 272 labels: each idea with its number, kept or not")
    centre, bin_x = 220, 560

    s.zone("try", 120, 348, "comes in")
    idea = s.box("idea", centre, 176, 360, "An idea\na setting that is off", "comes in", "ellipse")
    weeks = s.box("weeks", centre, 356, 320, "80 practice weeks\nwith it and without it", "measured")
    s.badge(1, centre, s.down(idea, weeks, centre))
    s.note(1, 308, "One idea at a time, on the same weeks",
           ["the same seed gives the same week to the cent,", "so each week is compared with itself"])

    s.zone("judge", 544, 460, "decides")
    gain = s.box("gain", centre, 600, 400, "Gain over twice\nits standard error?", "decides", "diamond", h=140)
    lowest = s.box("lowest", centre, 836, 400, "Lowest week\nstill as high?", "decides", "diamond", h=140)
    dropped = s.box("dropped", bin_x, 630, 160, "Not taken\nlisted with\nits number", "risk", h=316)
    s.down(weeks, gain, centre)
    s.badge(2, centre, 506)
    s.note(2, 506, "A gain counts from twice its standard error",
           ["one cent less on every fee step moved one week by", "€1,354: under that bar a difference is noise"])
    s.badge(3, centre, s.down(gain, lowest, centre))
    for gate in (gain, lowest):
        y = gate["y"] + 70
        s.arrow([(centre + 200 + GAP, y), (bin_x - 80 - GAP, y)], gate, dropped, colour=COLOURS["risk"][0])
        s.text(s.marks, f"no-{gate['id']}", centre + 216, y - 28, "no", 16, COLOURS["risk"][2])
    s.note("no", 670, "Most ideas end here, and stay in the log",
           ["over sixty are in the README, each with its label", "and what it made or lost"])
    s.note(3, 800, "The lowest week must not fall",
           ["the final is one week, and under 90% on time", "a team is not ranked"],
           "+€197 a week refused: the hardest week fell to 90.9%")

    s.zone("keep", 1080, 348, "result")
    unseen = s.box("unseen", centre, 1136, 320, "80 unseen weeks\njudged once, never tuned on", "measured")
    default = s.box("default", centre, 1316, 320, "The new default\nv19 · v20 · v21", "result", bold=True)
    s.down(lowest, unseen, centre)
    s.badge(4, centre, 1042)
    s.note(4, 1042, "Then 80 weeks that no setting has seen",
           ["the weeks that judged dozens of settings flatter", "the survivors, so fresh weeks judge the change once"])
    s.badge(5, centre, s.down(unseen, default, centre))
    s.note(5, 1268, "Only then it becomes the default",
           ["and plays the next ranking round, and the final"],
           "v20: +€169 a week on 200 weeks (standard error €37)")
    s.legend(1468, [("bold", "what the final plays"), ("risk", "measured, and not taken"), ("measured", "weeks played")])
    s.save("how-an-idea-becomes-a-default")


def the_live_final() -> None:
    s = Scene("The live final", "34 minutes that nobody touches: the service waits, plays and starts again by itself")

    s.zone("server", 120, 168, "outside")
    world = s.box("world", MIDDLE, 176, 400, "The final's world\nits clock runs by itself", "outside", "ellipse")

    s.zone("our machine", 364, 168, "decides")
    books = s.box("books", 150, 420, 240, "Books\nkept from the events", "measured")
    desk = s.box("desk", 515, 420, 230, "Desk\nprices and gigs", "decides", bold=True)
    edge = 218 + 42 * (1 - (100 / 200) ** 2) ** 0.5       # the ellipse's lower edge, 100 to each side of its middle
    s.arrow([(230, edge + GAP), (230, 420 - GAP)], world, books)
    s.arrow([(430, 420 - GAP), (430, edge + GAP)], desk, world)
    s.arrow([(270 + GAP, 462), (400 - GAP, 462)], books, desk)
    s.badge(1, 230, 326)
    s.badge(2, 335, 462)
    s.badge(3, 430, 326)
    s.note(1, 240, "Events arrive on a stream",
           ["requests, bookings, drivers who give a gig back:", "the books are kept from the events alone"])
    s.note(2, 346, "One look at the books takes 40 ms",
           ["at once after an event that cannot wait,", "and else every 12 minutes of the world"])
    s.note(3, 452, "Quotes and gigs go back in time", ["a request waits 4.5 s for its price"],
           "Sunday 01:00 test final: no late quote, 2nd of 236 teams")

    s.zone("four nets", 608, 504, "risk")
    nets = [
        ("No answer in 4 s", "Recover in place", "The desk keeps its books and reads what it missed",
         ["the kit waits 20 s, a world hour; the desk waits 4,", "then reads the missed events and goes on"],
         "two lost requests recovered in a test final, no rejoin"),
        ("A silent stream", "Open it again", "A dead stream says nothing, so silence is the sign",
         ["in the hours of the requests a live world is never", "silent for 3 s; the new stream starts at the last event"],
         "four silent streams opened again, nothing missed"),
        ("The process stops", "Start by itself", "A restart costs nothing that a week can show",
         ["the books are rebuilt from the event history", "and the desk's own journal"],
         "€19,444 a week with a restart, €19,208 without"),
        ("The hall's Wi-Fi", "Play from a VM", "The final is played 15 ms from the server",
         ["the Wi-Fi dropped for seconds at a time; the laptop", "is the standby, and plays only if the VM is gone"],
         "29th of 75 from the Wi-Fi, 2nd of 236 from the VM"),
    ]
    for i, (failure, answer, head, rows, effect) in enumerate(nets):
        y = 664 + 116 * i
        fails = s.box(f"fails-{i}", 150, y, 240, failure, "risk", h=72)
        answers = s.box(f"answers-{i}", 515, y, 230, answer, "result", h=72)
        s.arrow([(270 + GAP, y + 36), (400 - GAP, y + 36)], fails, answers)
        s.badge(4 + i, 335, y + 36)
        s.note(4 + i, y + 36, head, rows, effect)
    s.legend(1152, [("risk", "what can go wrong"), ("result", "what the service does"),
                    ("bold", "the decisions: the first diagram")])
    s.save("the-live-final")


if __name__ == "__main__":
    how_the_desk_decides()
    how_an_idea_becomes_a_default()
    the_live_final()
