"""
locations_data.py - the 8 pre-monitored NER stations shown on the dashboard.

elevation_m and slope_deg were REMOVED from here - they used to be hand-written
placeholder numbers. Real values are now fetched from an actual DEM (ASTER GDEM
via OpenTopoData) by services/terrain.py and attached in routes/gis.py. This
file only holds what is genuinely static reference data: id, name, coordinates,
state/district, and geology (geology is still a placeholder - not yet backed by
a real geological survey dataset; that is a separate, not-yet-done integration).

In a later phase this could move into the database - for now it's static
seed data shared by multiple routes.
"""

NER_LOCATIONS = [
    {
        "id": "MEG-SOHRA-01", "name": "Sohra (Cherrapunji), Meghalaya",
        "place": "Sohra (Cherrapunji) Cliff Escarpment",
        "lat": 25.28, "lon": 91.72, "state": "Meghalaya", "district": "East Khasi Hills",
        "geology": "Upper Cretaceous Limestone & Sandstone Overburden",
    },
    {
        "id": "MIZ-AIZ-01", "name": "Aizawl, Mizoram",
        "place": "Hunthar Veng Sinking Area",
        "lat": 23.73, "lon": 92.72, "state": "Mizoram", "district": "Aizawl North",
        "geology": "Tertiary Surma Group Sandstone-Shale",
    },
    {
        "id": "MAN-TUP-04", "name": "Tupul, Manipur",
        "place": "Tupul-Ijei River Basin Hill Ridge",
        "lat": 24.68, "lon": 93.83, "state": "Manipur", "district": "Noney",
        "geology": "Disturbed Belt Sedimentary Sequence",
    },
    {
        "id": "TRI-KHD-01", "name": "Khowai-Dhalai, Tripura",
        "place": "Atharamura Hill Pass",
        "lat": 24.06, "lon": 91.63, "state": "Tripura", "district": "Khowai-Dhalai",
        "geology": "Tipam Sandstone Formation",
    },
    {
        "id": "NAG-KOH-01", "name": "Kohima, Nagaland",
        "place": "Kohima Ridge Slope",
        "lat": 25.67, "lon": 94.11, "state": "Nagaland", "district": "Kohima",
        "geology": "Naga Metamorphic Belt",
    },
    {
        "id": "ARU-ITA-01", "name": "Itanagar, Arunachal Pradesh",
        "place": "Itanagar Capital Complex Slope",
        "lat": 27.10, "lon": 93.62, "state": "Arunachal Pradesh", "district": "Papum Pare",
        "geology": "Siwalik Group Sediments",
    },
    {
        "id": "SIK-GAN-01", "name": "Gangtok, Sikkim",
        "place": "Gangtok Ridge Escarpment",
        "lat": 27.33, "lon": 88.61, "state": "Sikkim", "district": "East Sikkim",
        "geology": "Darjeeling Gneiss Complex",
    },
    {
        "id": "ASM-GUW-01", "name": "Guwahati, Assam",
        "place": "Nilachal Hill Slope",
        "lat": 26.14, "lon": 91.74, "state": "Assam", "district": "Guwahati",
        "geology": "Precambrian Gneissic Basement",
    },
]
