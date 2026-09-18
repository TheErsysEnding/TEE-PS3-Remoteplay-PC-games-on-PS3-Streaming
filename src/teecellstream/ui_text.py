"""Die Worte beider Fenster - Beschriftungen, Erklaerungen, Uebersetzungen.

Das GTK-Fenster (ui.py) und das Qt-Fenster (ui_windows.py) zeigen dieselben Wahlmoeglichkeiten und
dieselben Saetze darunter. Zweimal aufgeschrieben waeren sie genau so lange gleich, bis jemand einen
davon anfasst - und dieses Projekt hat das schon zweimal bezahlt: einmal bei den Aufloesungsnamen, die
sich gegen STREAM_SIZES verschoben, einmal bei den Erklaerungen dazu, wo Full HD den Satz der
vorigen Zeile erbte. Deshalb steht hier alles, was beide brauchen, genau einmal - und nichts, was
GTK oder Qt kennt, damit dieses Modul auf jedem System importierbar bleibt.
"""

from . import protocol
from .i18n import _, add_translations

# The German half of this window. English is what stands in the code above and below; a string missing from
# here simply stays English, which is the point of keeping English as the source language.
LANGUAGE_LABELS = ("English", "Deutsch")
LANGUAGE_CODES = ("en", "de")

add_translations({
    # --- das Qt-Fenster (ui_windows.py) ------------------------------------------------------------
    # "Entropie-Codierung" und "Ratensteuerung" standen im GTK-Fenster als deutsche Literale im Code und
    # blieben deshalb auch in der englischen Oberflaeche deutsch. Hier steht Englisch als Quelltext und
    # das Deutsche in der Tabelle, wie ueberall sonst.
    "Entropy coding": "Entropie-Codierung",
    "Appearance": "Erscheinungsbild",
    "Dark, light, or whatever Windows is set to": "Dunkel, hell, oder so wie Windows eingestellt ist",
    "Follow Windows": "Wie Windows",
    "Light": "Hell",
    "Dark": "Dunkel",
    "Puts a shortcut in the Startup folder": "Legt eine Verknuepfung in den Autostart-Ordner",
    "Program": "Programm",
    "Help": "Hilfe",
    "About %s": "Ueber %s",
    "Version": "Fassung",
    "Streams the PC desktop to a PlayStation 3.": "Streamt den PC-Bildschirm an eine PlayStation 3.",
    "Based on cell-stream-server %s": "Aufbauend auf cell-stream-server %s",
    "Show": "Anzeigen",
    "Keep the server running": "Den Server am Laufen halten",
    "One euro pays for a whole month of the server this project lives on. PayPal, paysafecard, "
    "bank transfer or crypto.":
        "Ein Euro bezahlt einen ganzen Monat des Servers, auf dem dieses Projekt lebt. PayPal, "
        "paysafecard, Überweisung oder Krypto.",
    "Donate": "Spenden",
    "1 € pays for a month of the project's server":
        "1 € bezahlt einen Monat des Projekt-Servers",
    "All my projects": "Alle meine Projekte",
    "Source code": "Quelltext",
    "could not open the log: %s": "konnte das Log nicht öffnen: %s",
    "window: appearance %s, window colour %s": "Fenster: Erscheinungsbild %s, Fensterfarbe %s",
    "window: this Qt cannot switch the appearance (%s)":
        "Fenster: Dieses Qt kann das Erscheinungsbild nicht umschalten (%s)",
    "Yes, keep it": "Ja, so lassen",
    "The desktop was switched to the streaming resolution. Switching back in %d s unless you confirm.":
        "Der Desktop wurde auf die Stream-Aufloesung umgestellt. In %d s wird zurueckgeschaltet, wenn du "
        "nicht bestaetigst.",
    "started minimised - the icon in the notification area opens the window":
        "minimiert gestartet - das Symbol im Infobereich oeffnet das Fenster",
    "autostart: Windows does not say where the Startup folder is":
        "Autostart: Windows verraet nicht, wo der Autostart-Ordner liegt",
    " (recommended)": " (empfohlen)",
    "The PS3 decodes CAVLC about 43 % faster – measured 22 ms instead of 36–40 ms at 720p":
        "Die PS3 decodiert CAVLC rund 43 % schneller – gemessen 22 ms statt 36–40 ms bei 720p",
    "CABAC is slightly sharper per bit, but costs the PS3 considerably more decode time":
        "CABAC ist etwas schärfer pro Bit, kostet die PS3 aber deutlich mehr Decodezeit",
    "The lightest picture – the most decode time left over, at the cost of readable text":
        "Das leichteste Bild – es bleibt die meiste Decodezeit übrig, dafür wird Text unschärfer",
    " (a hair above – try it if the console runs fast)": " (einen Hauch darüber – testen, falls die Konsole schneller läuft)",
    "A good place to start – measured 22 ms decode on the PS3":
        "Empfohlen für den Einstieg – gemessen 22 ms Decode auf der PS3",
    "A little sharper, about 1.2× the decode load": "Etwas schärfer, rund 1,2× Decodelast",
    "Noticeably sharper, about 1.4× the decode load": "Deutlich schärfer, rund 1,4× Decodelast",
    "About 2× the decode load – a good middle ground": "Rund 2× Decodelast – ein guter Mittelweg",
    "Full HD, about 2.3× the decode load – measured 38–44 ms with x264":
        "Volles HD, rund 2,3× Decodelast – gemessen 38–44 ms mit x264",
    "the pointer and keyboard": "Zeiger und Tastatur",
    "pad: unknown key from the console's keyboard (HID 0x%02X)":
        "Pad: unbekannte Taste von der Tastatur an der Konsole (HID 0x%02X)",
    "Leave it alone": "Nicht umschalten",
    "Optimise for capture": "Für die Aufnahme optimieren",
    "Same size & refresh rate": "Gleiche Größe & Bildwiederholrate",
    "Same size only": "Nur gleiche Größe",
    "The desktop stays as it is – the stream is scaled down from its native mode":
        "Der Desktop bleibt, wie er ist – gestreamt wird vom nativen Modus herunterskaliert",
    "The highest refresh rate the capture can use – the most pictures, but the stream is resized":
        "Höchste Bildwiederholrate, die die Aufnahme nutzen kann – die meisten Bilder, aber der Stream wird umgerechnet",
    "Default: the stream's size at a whole multiple of its rate – nothing resampled, nothing beating":
        "Standard: Größe des Streams, Rate ein ganzes Vielfaches davon – nichts wird umgerechnet, nichts schwebt",
    "The stream's size at the fastest rate the screen has for it – sharp, but not locked in step":
        "Größe des Streams, dazu die schnellste Rate, die der Bildschirm dafür hat – scharf, aber nicht im Takt",
    "1 (default)": "1 (Standard)",
    "One picture in one piece – how everything so far was measured":
        "Ein Bild am Stück – so wurde alles bisher gemessen",
    "Experiment: two strips per picture. x264 only. Costs a little bitrate, as nothing is predicted across the edge":
        "Versuch: zwei Streifen je Bild. Nur x264. Kostet etwas Bitrate, weil über die Kante nicht vorhergesagt wird",
    "Experiment: four strips per picture – as many as the decoder has SPUs. x264 only":
        "Versuch: vier Streifen je Bild – so viele, wie der Decoder SPUs hat. Nur x264",
    "Variable": "Variabel",
    "Constant quality": "Konstante Qualität",
    "Constant bitrate": "Konstante Bitrate",
    "Bitrate only when something moves – the original setting":
        "Bitrate nur, wenn sich etwas bewegt – die ursprüngliche Einstellung",
    "Default: measured the lowest latency (29 ms), and text stays sharp on an idle desktop":
        "Standard: gemessen die niedrigste Latenz (29 ms), und Text bleibt auch im Leerlauf scharf",
    "Holds the rate exactly and pads with filler when it has to, which the server throws away again":
        "Hält die Rate genau und füllt notfalls mit Leerdaten auf, die der Server wieder wegwirft",
    "Default: repairs the picture continuously, with no bitrate spikes":
        "Standard: repariert das Bild laufend, ohne Bitratenspitzen",
    "Whole keyframes once a second – in case NVENC accumulates artefacts over time":
        "Ganze Schlüsselbilder im Sekundentakt – falls NVENC über die Zeit Artefakte zeigt",
    "None": "Keine",
    "Run a command or URI": "Befehl oder URI ausführen",
    " – above the cadence, pictures are being discarded": " – über dem Takt, Bilder werden verworfen",
    " – below the cadence, pictures are being held": " – unter dem Takt, Bilder werden gehalten",
    " – on the cadence": " – im Takt",
    " · source %d/s%s": " · Quelle %d/s%s",
    "Stopped": "Gestoppt",
    "Waiting for a PS3 …": "Warte auf eine PS3 …",
    "PS3 connected: ": "PS3 verbunden: ",
    "Closing the window leaves the server running in the background. Quit from the tray icon or the menu.":
        "Schließen des Fensters lässt den Server im Hintergrund weiterlaufen. "
        "Beenden über das Tray-Symbol oder das Menü.",
    "On the PS3, SELECT + Triangle / Circle / L1 / R1 fires commands 1 to 4. It only sends the "
    "number – what happens is set here: a URI such as steam://open/bigpicture (xdg-open) "
    "or a command line (sh -c). So a device on the network can never start anything you have not "
    "entered here.":
        "Die PS3 löst mit SELECT + Dreieck / Kreis / L1 / R1 die Befehle 1 bis 4 aus. Sie schickt nur die "
        "Nummer – was dann passiert, legst du hier fest: eine URI wie steam://open/bigpicture (xdg-open) "
        "oder eine Befehlszeile (sh -c). Ein Gerät im Netz kann also nie etwas starten, das du nicht "
        "hier eingetragen hast.",
    "Log opened": "Log geöffnet",
    "could not open the log: %s / %s": "konnte das Log nicht öffnen: %s / %s",
    "Main menu": "Hauptmenü",
    "Open the log": "Log öffnen",
    "Autostart": "Autostart",
    "Quit": "Beenden",
    "About ": "Über ",
    "Server": "Server",
    "Commands": "Befehle",
    "Video": "Video",
    "Input": "Eingabe",
    "System": "System",
    "Log": "Protokoll",
    "Encoder": "Encoder",
    "Error correction": "Fehlerkorrektur",
    "Resolution": "Auflösung",
    _("Bitrate"): _("Bitrate"),
    _("Entropy coder"): "Entropie-Codierung",
    _("Rate control"): "Ratensteuerung",
    "Slices per picture (experiment)": "Slices je Bild (Versuch)",
    "The desktop while streaming": "Desktop während des Streams",
    "Language": "Sprache",
    "The interface switches over at once – no restart": "Die Oberfläche schaltet sofort um – kein Neustart",
    "Stop": "Stopp",
    "Start": "Start",
    "Locked while a PS3 is streaming": "Gesperrt, solange eine PS3 streamt",
    "No H.264 encoder found": "Kein H.264-Encoder gefunden",
    "How the stream gets back to a clean picture after packet loss":
        "Wie der Stream nach Paketverlust wieder ein sauberes Bild bekommt",
    "Bigger means more readable text, but costs the PS3 roughly proportionally more decode time":
        "Größer heißt lesbarer Text, kostet die PS3 aber ungefähr proportional mehr Decodezeit",
    "Lower it when the picture judders on the PS3 – raise it only while it stays fluid":
        "Niedriger, wenn das Bild auf der PS3 ruckelt – höher nur, solange es flüssig bleibt",
    "The PS3 decodes CAVLC about 43 % faster – CABAC only while the picture stays fluid":
        "Die PS3 decodiert CAVLC rund 43 % schneller – CABAC nur, solange das Bild flüssig bleibt",
    "What the encoder spends its bitrate on – only the x264 encoder can do all three":
        "Wofür der Encoder seine Bitrate ausgibt – nur der x264-Encoder kann alle drei",
    "Swap the sticks in mouse mode": "Sticks im Maus-Modus tauschen",
    "The right stick moves the pointer": "Rechter Stick bewegt den Zeiger",
    "Start at login (minimised)": "Beim Anmelden starten (minimiert)",
    "Creates an autostart entry": "Legt einen Autostart-Eintrag an",
    "Ctrl+L": "Strg+L",
    "stopped by you": "von dir gestoppt",
    "encoders: end the stream first, then change the encoder":
        "encoders: erst den Stream beenden, dann den Encoder wechseln",
    "video: end the stream first, then change the error correction":
        "video: erst den Stream beenden, dann die Fehlerkorrektur wechseln",
    "video: end the stream first, then change the bitrate":
        "video: erst den Stream beenden, dann die Bitrate wechseln",
    "video: end the stream first, then change the resolution":
        "video: erst den Stream beenden, dann die Auflösung wechseln",
    "video: end the stream first, then change the entropy coder":
        "video: erst den Stream beenden, dann die Entropie-Codierung wechseln",
    "video: end the stream first, then change the rate control":
        "video: erst den Stream beenden, dann die Ratensteuerung wechseln",
    "video: end the stream first, then change the slice count":
        "video: erst den Stream beenden, dann die Slice-Zahl wechseln",
    "No, switch back": "Nein, zurückschalten",
    "display: picture confirmed, the new resolution stays":
        "display: Bild bestätigt, die neue Auflösung bleibt",
    "The desktop was switched for the stream.\n\nIf you can read this, everything is fine. "
    "With no answer it switches back to the previous resolution automatically in %d seconds.":
        "Der Desktop wurde für den Stream umgeschaltet.\n\nWenn du das hier lesen kannst, ist alles in "
        "Ordnung. Ohne Antwort wird in %d Sekunden automatisch auf die vorherige Auflösung zurückgeschaltet.",
    "window: could not go to the background: %s": "Fenster: konnte nicht in den Hintergrund gehen: %s",
    "command %d could not be saved: %s": "Befehl %d konnte nicht gespeichert werden: %s",
    "Still running in the background": "Läuft im Hintergrund weiter",
    "The server is still waiting for the PS3. Quit from the tray icon or the menu.":
        "Der Server wartet weiter auf die PS3. Beenden über das Tray-Symbol oder das Menü.",
})

def fps_labels() -> tuple[str, ...]:
    """Built on demand like bitrate_labels: the bracketed words are translated."""
    smooth = _(" (even)")
    hitch = _(" (slight hitch)")
    exact = _(" (matches the TV exactly)")
    probe = _(" (needs a smaller picture – measures the decoder)")
    trial = _(" (a hair above – try it if the console runs fast)")

    def note(f: float) -> str:
        # 59.94 is the television's own rate, so every picture lands on exactly one refresh: no
        # duplicate, no dropped one. Above 60 nothing more can be SHOWN at all - the extra pictures
        # are decoded and then overwritten before the beam reaches them - so those are a measurement.
        if abs(f - 59.94) < 0.005:
            return exact
        if abs(f - 59.95) < 0.005:
            # the two are 0.01 apart, so this test has to be tighter than the gap - see fps_fraction,
            # where the same band was wide enough to swallow 59.95 whole
            return trial
        if f > 60:
            return probe
        return smooth if f in (30, 60) else hitch

    return tuple("%g fps%s" % (f, note(f)) for f in protocol.FPS_CHOICES)


def bitrate_labels() -> tuple[str, ...]:
    """Built on demand rather than at import: the word in brackets is translated, so the list has to be
    rebuilt whenever the language changes."""
    return tuple("%d Mbit/s%s" % (k // 1000, _(" (recommended)") if k == protocol.KBPS else "")
                 for k in protocol.BITRATE_CHOICES_KBPS)
# Short names for the dropdown, full explanations underneath it. GTK truncates a long selected value with
# an ellipsis at any window size, so the sentence that explains a choice can never live inside the choice:
# it goes into the row's subtitle, which the row rewrites whenever the selection changes.
FPS_HINT = ("The PS3 shows 59.94 pictures a second. 30 and 60 land evenly on that, "
            "50 and 55 do not – they buy the console time per picture instead")
BITRATE_HINT = "Lower it when the picture judders on the PS3 – raise it only while it stays fluid"

ENTROPY_LABELS = ("CAVLC", "CABAC")
ENTROPY_HINTS = ("The PS3 decodes CAVLC about 43 % faster – measured 22 ms instead of 36–40 ms at 720p",
                 "CABAC is slightly sharper per bit, but costs the PS3 considerably more decode time")

def size_labels() -> tuple[str, ...]:
    """Built from protocol.STREAM_SIZES rather than written out beside it.

    It used to be a hardcoded tuple, and the moment a size was added to STREAM_SIZES without it the
    dropdown kept its old entries while every index shifted by one - picking "1280 × 720" set
    960 × 544. Two lists that must agree is one list too many."""
    return tuple("%d × %d" % size for size in protocol.STREAM_SIZES)
# Keyed by the size itself, not by position. As a flat tuple this had gone wrong exactly the way the
# labels above had: 960 × 544 was added to STREAM_SIZES and the tuple stayed five long, so every
# explanation slid up by one place and Full HD - the last entry - got none at all and simply kept
# whichever sentence had been standing there before. A size with no entry here is now visible as a
# short, honest line instead of somebody else's sentence.
SIZE_HINT_BY_SIZE = {
    (960, 544):   "The lightest picture – the most decode time left over, at the cost of readable text",
    (1280, 720):  "A good place to start – measured 22 ms decode on the PS3",
    (1408, 800):  "A little sharper, about 1.2× the decode load",
    (1536, 864):  "Noticeably sharper, about 1.4× the decode load",
    (1792, 1008): "About 2× the decode load – a good middle ground",
    (1920, 1080): "Full HD, about 2.3× the decode load – measured 38–44 ms with x264",
}


def size_hints() -> tuple[str, ...]:
    """One explanation per entry of STREAM_SIZES, in that order - see SIZE_HINT_BY_SIZE."""
    return tuple(SIZE_HINT_BY_SIZE.get(size, "%d × %d" % size) for size in protocol.STREAM_SIZES)

# The names say what each one DOES to the desktop, in the order DISPLAY_STRATEGIES lists them.
# "Throttle to 60 Hz" was the old name of the third one and described only half of it: it also puts the
# desktop at the stream's own size, and that half turned out to be the one that made the picture sharp.
DISPLAY_LABELS = ("Leave it alone", "Optimise for capture", "Same size & refresh rate", "Same size only")
DISPLAY_HINTS = ("The desktop stays as it is – the stream is scaled down from its native mode",
                 "The highest refresh rate the capture can use – the most pictures, but the stream is resized",
                 "Default: the stream's size at a whole multiple of its rate – nothing resampled, nothing beating",
                 "The stream's size at the fastest rate the screen has for it – sharp, but not locked in step")

SLICE_LABELS = ("1 (default)", "2", "4")
SLICE_HINTS = ("One picture in one piece – how everything so far was measured",
               "Experiment: two strips per picture. x264 only. Costs a little bitrate, as nothing is predicted across the edge",
               "Experiment: four strips per picture – as many as the decoder has SPUs. x264 only")
RATE_LABELS = ("Variable", "Constant quality", "Constant bitrate")
RATE_HINTS = ("Bitrate only when something moves – the original setting",
              "Default: measured the lowest latency (29 ms), and text stays sharp on an idle desktop",
              "Holds the rate exactly and pads with filler when it has to, which the server throws away again")

LOSS_RECOVERY_KINDS = ("intra", "keyframe")
LOSS_RECOVERY_LABELS = ("Intra-Refresh", "Keyframes")
LOSS_RECOVERY_HINTS = ("Default: repairs the picture continuously, with no bitrate spikes",
                       "Whole keyframes once a second – in case NVENC accumulates artefacts over time")
COMMAND_KINDS = ("none", "run")
COMMAND_KIND_LABELS = ("None", "Run a command or URI")

# The grid hands the console `fps` pictures a second whatever the desktop does. A source ABOVE that has
# some of its pictures replaced before their slot, and unevenly - which is exactly what judder is, even
# while every counter still reads 60. Measured across sessions: a source at ~60/s put 94-97 % of pictures
# on the grid, one at 67-83/s only 68-76 %. Below the band the source itself is simply slow and pictures
# are held; that is visible for a different reason and is not the capture's doing.
# The band is the servo's, see capture.SERVO_SLEW_FRACTION: inside it the grid follows the source exactly.
SOURCE_BAND = 0.0333


def source_rate_text(captured_fps: int, fps: int) -> str:
    """The live source rate for the status line, with a word on it when it is outside the servo band."""
    if captured_fps <= 0:
        return ""
    # captured_fps is a whole number, so the band has to be rounded outwards or the two rates at its very
    # edge read as outside it. The servo was measured locking at 62/s and letting go at 63.
    low, high = int(fps * (1 - SOURCE_BAND)), -int(-fps * (1 + SOURCE_BAND) // 1)
    if captured_fps > high:
        note = " – above the cadence, pictures are being discarded"
    elif captured_fps < low:
        note = " – below the cadence, pictures are being held"
    else:
        note = " – on the cadence"
    return " · source %d/s%s" % (captured_fps, note)


STATUS_STOPPED = "Stopped"
STATUS_WAITING = "Waiting for a PS3 …"
STATUS_CONNECTED = "PS3 connected: "
HIDE_HINT = ("Closing the window leaves the server running in the background. "
             "Quit from the tray icon or the menu.")
COMMANDS_INTRO = ("On the PS3, SELECT + Triangle / Circle / L1 / R1 fires commands 1 to 4. It only sends the "
                  "number – what happens is set here: a URI such as steam://open/bigpicture (xdg-open) "
                  "or a command line (sh -c). So a device on the network can never start anything you have not "
                  "entered here.")



def status_text(armed: bool, connected: bool, who: str) -> str:
    """The one line the window's status card and the tray's tooltip both show - defined once so they cannot drift."""
    if not armed:
        return _(STATUS_STOPPED)
    return _(STATUS_CONNECTED) + who if connected else _(STATUS_WAITING)
