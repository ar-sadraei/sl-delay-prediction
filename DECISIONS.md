# Decisions Log

This file documents the non-obvious judgment calls made during this project, and why. The goal is that anyone (including future me) can understand *why* the pipeline works the way it does, not just *what* it does.

## Project setup

**Branch per phase, PR + merge even solo.** Every phase of work happens on its own branch, gets pushed, opened as a Pull Request, reviewed, then merged into `main`. `main` stays in a working state at all times. Done even working alone, because the commit/PR history itself is part of what a project demonstrates.

**API keys are named by purpose, not by creation order.** Started with one generic `TRAFIKLAB_KEY`, but split into `TRAFIKLAB_STATIC_KEY` / `TRAFIKLAB_REALTIME_KEY` / `TRAFIKLAB_KODA_KEY` once it became clear Trafiklab treats GTFS Regional Static, GTFS Regional Realtime, and KoDa as separately-authorized APIs, each needing its own key added to the project. A generic name stops being descriptive the moment there's more than one of something.

## Data access

**KoDa dates must be based on the real current date, not an assumed one.** Hit a `400 Bad Request` ("data does not exist") when requesting a KoDa archive for a date that turned out to be in the future relative to the actual server clock. KoDa only has archives for dates that have already happened — pick historical dates deliberately, checked against `date` in the terminal, not assumed.

**`py7zr` cannot open KoDa's 7z archives; extraction uses the system `7zz` binary instead.** Confirmed the archives themselves are valid (via the `file` command and via successfully extracting other dates) but `py7zr` throws `Bad7zFile: invalid header data` even after upgrading. The actively-maintained `sevenzip` Homebrew package (binary name `7zz`, distinct from the older/unmaintained `p7zip`) handles them without issue. The pipeline shells out via `subprocess` rather than depending on `py7zr`.

**Some KoDa archives are themselves corrupted on the server side, independent of any local issue.** The archive for `2025-08-01` was only 891KB and failed to open in three independent, well-established tools (`py7zr`, `p7zip`, and current `sevenzip`) despite a fully verified, complete download (`Content-Length` matched bytes received exactly). A neighboring date (`2024-08-01`, ~59.8MB) downloaded and extracted cleanly. Lesson: if multiple independent tools agree something's broken, the input itself — not the tooling — is usually the problem. Pipeline code that processes many dates should expect occasional bad archives and handle/log failures per-date rather than assuming every date will succeed.

**SL's realtime `TripUpdates` snapshots repeat every ~15-30 seconds throughout the day; "the observed delay" for a (trip, stop) is defined as the last snapshot recorded before that stop was reached.** This is a deliberate choice, not the only valid one — an average across snapshots, or the delay at scheduled arrival time specifically, are both defensible alternatives. "Last known value" was chosen as the simplest reasonable proxy for "what actually happened."

**Historical joins must use KoDa's historical *static* GTFS snapshot for the matching date, not the live static feed.** Trafiklab's static GTFS is regenerated daily, so today's trip IDs and schedules aren't guaranteed to match what was in effect weeks or months ago. Joining old realtime data against today's schedule would silently mis-join or drop rows, more so the further back the date. KoDa serves historical static snapshots specifically to avoid this.

**GTFS scheduled times can exceed `24:00:00`** for trips that run past midnight (e.g. `25:14:00`). A plain `pd.to_datetime` call fails on this; parsing splits the time into hours/minutes/seconds and adds it as a `Timedelta` to the service date instead, which correctly rolls over into the next calendar day.

## Weather data

**SMHI parameter 1 ("Lufttemperatur — momentanvärde, 1 gång/tim") was chosen over several other same-titled temperature parameters** after checking each one's `summary` field directly against the live API rather than assuming. Parameter 1 gives one instantaneous reading per hour, which matches the trip data's hourly granularity — daily min/max/mean variants (parameters 2, 19, 20, 26, 27) would lose the hour-level detail needed for the join, and the per-minute variant (45) is finer-grained than needed.

**Station 98230 (Stockholm-Observatoriekullen A) was chosen over station 98210 (same physical location, same coordinates)** because 98230 has both current data (`latest-hour`/`latest-day`/`latest-months`) and the full quality-controlled `corrected-archive`, while 98210 only exposes the archived history — suggesting 98210 is a retired/legacy station code. Airport stations (Arlanda, Bromma) were considered and rejected in favor of a central-Stockholm station, since airports sit well outside the city center where most SL delays are actually occurring.

**SMHI's CSV export mixes real data rows with stray footnote/legend text in extra trailing columns**, and the number of metadata header rows before the real table isn't guaranteed stable. Parsing finds the real header row programmatically (by scanning for the line starting with `"Datum;"`) rather than hardcoding a `skiprows` count, and explicitly restricts to the first 4 columns (`date`, `time`, `temperature_c`, `quality`) rather than reading everything.

**The `quality` column (SMHI's G/Y flags — green = checked & approved, yellow = suspect/roughly-checked) is kept, not dropped.** No filtering decision has been made yet on whether to exclude yellow-flagged readings — deferred until Phase 3, where its effect on results (if any) can be checked directly rather than assumed upfront.

**The weather station has real gaps in its hourly record** (e.g. a missing `02:00:00` reading observed directly in the data). The join in Phase 2 needs to tolerate missing weather for a given hour (produce a null) rather than crash or silently drop the corresponding trip.

---
*This log will be updated as Phase 2 onward introduces new judgment calls (delay threshold, train/test split strategy, precision/recall trade-offs, etc.).*
