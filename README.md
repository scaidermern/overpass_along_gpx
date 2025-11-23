# overpass_along_gpx

Query Overpass API along GPX files and write the result to a GPX file.

## Description

Query OpenStreetMap tags via Overpass API along a GPX track.
Reads a GPX track and stores each track point as location.
Then Overpass API is queried for all locations and the given tags to retrieve elements (nodes and ways) from OpenStreetMap.
The result is saved as a GPX file (waypoints and tracks).
Currently only nodes and ways are supported but not relations.

## Options

- `files`: GPX files to read
- `-h, --help`: show this help message and exit
- `-o, --outfile OUTFILE`: output file
- `-q, --query QUERY`: Overpass API tag query, e.g. `'node["amenity"~"bench|waste_basket"]'`
- `-f, --queryfile QUERYFILE`: file that contains Overpass API tag queries, one query per line
- `-n, --name NAME`: title of the resulting GPX file
- `-t, --timeout TIMEOUT`: timeout of the Overpass API query in seconds
- `-d, --distance DISTANCE`: maximum distance around track in meters to query Overpass API for
- `-l, --limit LIMIT`: limit number of locations per Overpass API query to perform multiple smaller queries instead of a large one (use 0 for unlimited, try 500 if requests fail)
- `-r, --retries RETRIES`: number of retries if call to Overpass API fails
- `-u, --url URL`: Overpass API instance
- `--dry-run`: don't execute Overpass API query, only print it
- `-v, --verbose`: print debugging information (use twice to be more verbose)

## Example

Example: Obtain locations from `in.gpx`, search for highways without a surface tag around each location, write the result to `out.gpx`.
```
./overpass_along_gpx.py -o out.gpx -q 'way["highway"][!"surface"]' in.gpx
```

Tag queries can either be specified on the command line via `-q` or read from a file specified via `-f`.
When using option `-f`, tag queries have to be specified one per line.
See file `example_query.txt` as an example. 

# License
[GPL v3](https://www.gnu.org/licenses/gpl-3.0.html)
(c) Alexander Heinlein
