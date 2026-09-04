"""Terminal layovers derived from consecutive trips of one GTFS vehicle block.

The timetable establishes a layover, not the location of a real reversing siding.
Intervals exclude both the incoming and outgoing passenger-platform dwell.
"""
from collections import defaultdict


def turnback_snapshot(data, services, seconds):
    blocks = defaultdict(list)
    for trip in data['trips']:
        if trip['service'] in services and trip.get('block') and trip['times']:
            blocks[trip['block']].append(trip)

    def station(stop):
        return data['stops'][stop].get('parent') or stop

    active = []
    rejected = 0
    for block, trips in blocks.items():
        trips.sort(key=lambda trip: (trip['times'][0][1], trip['id']))
        for previous, following in zip(trips, trips[1:]):
            arrival, departure = previous['times'][-1], following['times'][0]
            start, end = arrival[2], departure[1]
            if end < start:
                rejected += 1
                continue
            if not start <= seconds < end:
                continue
            terminal = station(arrival[0])
            if (terminal != station(departure[0]) or previous['route'] != following['route']
                    or terminal == station(following['times'][-1][0])):
                continue
            # Do not show a train parked while another trip of that block is operating.
            if any(t is not previous and t is not following
                   and t['times'][0][1] < end and t['times'][-1][2] > start for t in trips):
                continue
            active.append(dict(
                id=f"turnback:{block}:{previous['id']}:{following['id']}", block=block,
                line_id=previous['route'], station_id=terminal,
                station=data['stops'][arrival[0]]['name'], status='TURNBACK',
                started_at_seconds=start, ends_at_seconds=end,
                duration_seconds=end-start, remaining_seconds=round(end-seconds, 1),
                next_departure_seconds=departure[2], next_trip_id=following['id'],
                next_destination=following['headsign'], provenance='DERIVED_GTFS_BLOCK_GAP',
            ))
    return dict(turnbacks=active, turnback_quality=dict(
        overlapping_trip_pairs=rejected,
        note='Terminal layover inferred from the same scheduled block. Bay locations and reversing movements are not surveyed. Conflicting or unlinked services have no invented countdown.'
    ))
