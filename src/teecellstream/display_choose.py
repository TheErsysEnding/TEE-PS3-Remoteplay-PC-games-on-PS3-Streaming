"""Picking the desktop mode to stream from - the part that is pure arithmetic.

Split out of display_mode.py so Windows can use the same choosers. Everything here is measurement, not
platform: which mode keeps the picture sharp, which keeps it even, and why. Duplicating it for a second
platform would be the "two lists that must agree" mistake this project has already paid for twice - once
when the resolution names drifted out of step with the sizes, and once when the explanations did.

A `mode` here is anything with .width, .height, .refresh and .is_variable_rate; both backends build their
own, and neither has to know about the other.
"""

CAPTURE_REFRESH_FACTOR = 1.5   # 60 fps wants a 90 Hz desktop before the compositor keeps up

# Sizes every monitor is expected to know. An exotic mode - 1408x800, 1536x864, 1792x1008 - may not exist
# on someone else's screen, or may exist and show nothing, and a black desktop is a bad thing to hand a
# user who is looking at their TV. So the desktop is put into an ordinary size and the stream is scaled
# from it. Only sizes that also clear CAPTURE_REFRESH_FACTOR qualify: on a screen whose 1280x720 tops out
# at 60 Hz, switching to it would cost a third of the frames, which is worse than any scaling.
PREFERRED_DESKTOP_SIZES = ((1280, 720), (1920, 1080), (2560, 1440))

# The three strategies the user can pick between. "capture" is the measured default above; "sixty" exists
# because the default's premise - more refresh is always better - has a cost the frame COUNT never showed:
# a 320 Hz desktop hands the screen cast ~69 pictures a second at uneven intervals, our 60 Hz grid takes the
# newest of them, and 15 % are superseded before their slot. Measured on the real console: content spacing
# 75 % within a quarter-interval of ideal, 756 visibly held pictures in a 7-minute session. At 60 Hz there
# is no beat left at all - the compositor and the grid share one clock - but the same measurement that gave
# us CAPTURE_REFRESH_FACTOR says the cast then hands out only two thirds of them. Evenly spaced 40 against
# unevenly spaced 58: which of those an eye prefers is not something to reason about, so it is a switch.
DISPLAY_STRATEGIES = ("off", "capture", "sixty", "size")

# Monitors report 59.9506 for what everyone calls 60, and 320.00146 for 320. A rate is "the same" within
# this much - wide enough for that, narrow enough to tell 60 from 120. Used when a rate is matched against
# a NAME ("the 60 Hz mode"), where a tenth of a Hz never mattered.
# (This used to be declared twice, 0.2 near the top and 1.0 here; the second one shadowed the first for
# every call, so 0.2 never applied to anything. Only this one is left.)
REFRESH_TOLERANCE_HZ = 1.0

# ...but "is the desktop ALREADY at the exact mode we picked out of its own list" is a different question,
# and it needs a much tighter answer. This screen has 1920x1080 at 119.8788 Hz AND at 119.9302 Hz, 0.05 Hz
# apart, and only one of them is exactly 2 x 59.94 - telling those two apart is the whole point of
# choose_sixty_hz_mode. At 1.0 Hz a desktop sitting on the wrong one reported "already there" and was never
# switched, which quietly cancelled that choice.
# This is only used when the rate came from the monitor's own mode list, so it need only absorb the
# rounding in what mutter reports (four decimals). A merely NOMINAL 60 keeps the wide tolerance: a screen
# whose "60" is 59.9506 must not be restarted for nothing.
SAME_RATE_TOLERANCE_HZ = 0.02

CONFIRM_SECONDS = 15


def choose_sixty_hz_mode(modes: list, stream_width: int, stream_height: int, fps: float) -> tuple:
    """(width, height, refresh) for the "no beat" strategy: an ordinary size at the stream's own frame rate.

    Everything shares one clock this way - the game, the compositor, our grid and the console - so no picture
    can be superseded before its slot and none can be held past it. What it costs is what
    CAPTURE_REFRESH_FACTOR was written for; whether that trade is worth it is what the switch is for."""
    # An integer MULTIPLE of the frame rate is just as beat-free as the rate itself - at 2x every
    # second repaint is a slot - and it is what makes this strategy usable at all. Measured on a
    # 320 Hz monitor: the desktop at 1x (59.939 Hz) had the source delivering only 33 pictures a
    # second, because GNOME's ScreenCast hands out roughly every other repaint. At 2x (119.879 Hz)
    # the same shortfall still leaves a full 60. So multiples from 2 up are preferred, and 1x is the
    # fallback for a monitor that has nothing faster.
    #
    # The 0.5 Hz tolerance is absolute on purpose, because the leftover IS the beat frequency: a mode
    # 0.5 Hz off its multiple walks the phase through one whole repaint every two seconds, and one
    # 0.24 Hz off (240.000 Hz against 4 x 59.94 = 239.76) every four. Both are far better than the
    # 60 Hz beat of an unmatched desktop, and a tighter bound would reject useful modes.
    def multiple_of(refresh: float) -> int:
        for n in (2, 3, 4, 1):
            if abs(refresh - fps * n) <= 0.5:
                return n
        return 0

    # Two modes of the same size can BOTH pass that tolerance: this monitor offers 1920x1080 at 119.8788 Hz
    # and at 119.9302 Hz, and only the first is exactly 2 x 59.94. Whatever is left over is the beat, so among
    # equals the smallest leftover has to win - 0.0012 Hz off walks the phase through one repaint every 14
    # minutes, 0.05 Hz off every 20 seconds, and the 20 seconds are what is still felt as the odd hitch.
    def phase_error(mode) -> float:
        return abs(mode.refresh - fps * multiple_of(mode.refresh))

    usable = [mode for mode in modes
              if mode.width >= stream_width and mode.height >= stream_height
              and multiple_of(mode.refresh) and not mode.is_variable_rate]
    if not usable:
        return stream_width, stream_height, float(fps)
    # smallest multiple at or above 2 wins; 1x only when the screen offers nothing else
    best_multiple = min((multiple_of(mode.refresh) for mode in usable),
                        key=lambda n: (n < 2, n))
    exact = [mode for mode in usable if multiple_of(mode.refresh) == best_multiple]
    for width, height in PREFERRED_DESKTOP_SIZES:
        if width * height < stream_width * stream_height:
            continue
        fits = [mode for mode in exact if (mode.width, mode.height) == (width, height)]
        if fits:
            closest = min(fits, key=phase_error)
            return closest.width, closest.height, closest.refresh
    # size still comes first - a desktop bigger than the stream costs a resampling, which costs sharpness
    best = min(exact, key=lambda mode: (mode.width * mode.height, phase_error(mode)))
    return best.width, best.height, best.refresh


def choose_size_only_mode(modes: list, stream_width: int, stream_height: int, fps: float) -> tuple:
    """(width, height, refresh) for "the stream's own size, whatever rate the screen does best".

    This takes half of what "sixty" does and leaves the other half alone. The half it keeps is the one
    that was measured to matter most: with the desktop at exactly the stream's size nothing is resampled
    on the way to the console, and that is what turned a soft picture sharp. The half it drops is the
    rate - so the screen may run as fast as it likes, and the compositor has all the repaints it wants
    instead of the bare two per picture that a locked multiple leaves it.

    What it gives up is the phase lock: the desktop's rate is then whatever the monitor's fastest mode at
    that size happens to be, and it need not be a whole multiple of the frame rate. Whether the sharpness
    without the lock beats the lock is exactly what this setting is for finding out."""
    same = [mode for mode in modes
            if mode.width == stream_width and mode.height == stream_height and not mode.is_variable_rate]
    if not same:
        # the screen has no mode at this size at all: ask for it anyway, as the other strategies do -
        # the backend either finds something or reports back and the stream is scaled as before
        return stream_width, stream_height, float(fps)
    best = max(same, key=lambda mode: mode.refresh)
    return best.width, best.height, best.refresh


def choose_capture_mode(modes: list, stream_width: int, stream_height: int, fps: int) -> tuple:
    """(width, height, refresh) the desktop should run at while streaming `stream_width`x`stream_height`@fps."""
    roomy = [mode for mode in modes
             if mode.width >= stream_width and mode.height >= stream_height
             and mode.refresh >= fps * CAPTURE_REFRESH_FACTOR and not mode.is_variable_rate]
    if not roomy:
        # no mode is fast enough (a plain 60 Hz monitor): the third is lost whatever we do, so fall back to
        # the original's pixel-for-pixel switch, which at least keeps the capture small and the picture sharp
        return stream_width, stream_height, float(fps)
    # an ordinary size first, smallest that still covers the stream; failing that, the largest ordinary
    # size this screen can do quickly - a 1920x1088 stream has no ordinary size big enough, and 1920x1080
    # is both the closest and very nearly 1:1
    covering = [size for size in PREFERRED_DESKTOP_SIZES if size[0] * size[1] >= stream_width * stream_height]
    for candidates in (covering, list(reversed(PREFERRED_DESKTOP_SIZES))):
        for width, height in candidates:
            fits = [mode for mode in roomy if (mode.width, mode.height) == (width, height)]
            if fits:
                best = max(fits, key=lambda mode: mode.refresh)
                return best.width, best.height, best.refresh

    best = min(roomy, key=lambda mode: (mode.width * mode.height, -mode.refresh))
    return best.width, best.height, best.refresh



