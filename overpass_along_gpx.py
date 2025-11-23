#!/usr/bin/env python3
"""Query Overpass API along GPX files and write the result to a GPX file"""

import argparse
import http.client
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

@dataclass
class Location:
    """Location consisting of latitude and longitude"""

    lat: float
    lon: float

    def str(self):
        """Return a string represenation of this location"""

        return f'{self.lat},{self.lon}'

@dataclass
class OverpassAlongGPX:
    """Query Overpass API along GPX files and write the result to a GPX file

    Attributes:
        url (str): Overpass API instance
        limit (int): Maximum number of locations per Overpass API query
        retries (int): Number of retries if call to Overpass API fails
        verbose (int): Verbosity level
        locations_in (list): List of locations obtained from GPX input file
        nodes_out (list): Nodes obtained from Overpass API result
        ways_out (list): Ways obtained from Overpass API result
        node_ids (set): Unique OSM IDs of all ways obtained from Overpass API result
        way_ids (set): Unique OSM IDs of all ways obtained from Overpass API result
        failure (bool): Whether call to Overpass API failed even after retry
    """

    url: str
    limit: int = 0
    retries: int = 0
    verbose: int = 0
    locations_in: list = field(default_factory=list)
    nodes_out: list = field(default_factory=list)
    ways_out: list = field(default_factory=list)
    node_ids: set = field(default_factory=set)
    way_ids: set = field(default_factory=set)
    failure: bool = False

    @dataclass
    class Node:
        """Node consisting of a single location

        Attributes:
            id (int): Unique OSM ID of this way
            loc (Location): Coordinates
        """

        id: int
        loc: Location

    @dataclass
    class Way:
        """Way consisting of multiple locations (nodes)
        
        Attributes:
            id (int): Unique OSM ID of this way
            nodes (list): A list of locations 
        """

        id: int
        nodes: list = field(default_factory=list)

        def add_node(self, location):
            """Add a node to this way"""
            self.nodes.append(location)

    def write_header(self, out, title):
        """Add GPX header"""

        out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        out.write('<gpx\n')
        out.write(' xmlns="http://www.topografix.com/GPX/1/1"\n')
        out.write(' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n')
        out.write(' xsi:schemaLocation="http://www.topografix.com/GPX/1/1 '
            'http://www.topografix.com/GPX/1/1/gpx.xsd"\n')
        out.write(' version="1.1"\n')
        out.write(' creator="overpass_along_gpx">\n')

        if title:
            out.write(f' <title>{title}</title>\n')

    def write_footer(self, out):
        """Add GPX trailer"""

        out.write('</gpx>\n')

    def write_node(self, out, node):
        """Write node to GPX"""

        out.write((
            f' <wpt lat="{node.loc.lat}" lon="{node.loc.lon}">\n'
            '  <extensions>\n'
            f'   <osmid>{node.id}</osmid>\n'
            '  </extensions>\n'
            ' </wpt>\n'))

    def write_way(self, out, way):
        """Write way to GPX"""

        out.write((
            ' <trk>\n'
            '  <trkseg>\n'))
        for node in way.nodes:
            out.write(f'   <trkpt lat="{node.lat}" lon="{node.lon}"></trkpt>\n')
        out.write((
            '  </trkseg>\n'
            '  <extensions>\n'
            f'   <osmid>{way.id}</osmid>\n'
            '  </extensions>\n'
            ' </trk>\n'))

    def parse_gpx_file(self, file):
        """Obtain locations from given GPX file"""

        print(f'Parsing {file}')
        with open(file, encoding='utf-8') as infile:
            for line in infile:
                if not any(word in line for word in('<trkpt', '<wpt', '<rtept')):
                    continue
                if not 'lat="' in line and 'lon="' in line:
                    continue

                lat = re.search('lat="\\d+\\.\\d+"', line)
                if not lat:
                    continue
                lat = lat.group(0) # lat='lat="51.12345"'
                lat = float(lat.split('"')[1])

                lon = re.search('lon="\\d+\\.\\d+"', line)
                if not lon:
                    continue
                lon = lon.group(0) # lon='lon="13.67890"'
                lon = float(lon.split('"')[1])

                location = Location(lat, lon)
                self.locations_in.append(location)
        if self.verbose:
            print(f'Read {len(self.locations_in)} locations')

    def write_result(self, file, title):
        """Write Overpass API result to GPX file"""

        if self.verbose:
            print(f'Writing result to {file}')

        with open(file, 'w', encoding='utf-8') as outfile:
            self.write_header(outfile, title)
            for node in self.nodes_out:
                self.write_node(outfile, node)
            for way in self.ways_out:
                self.write_way(outfile, way)
            self.write_footer(outfile)
        print('Wrote result')

    def read_overpass_queries_from_file(self, file):
        """Read Overpass API queries from file"""

        queries = []
        with open(file, encoding='utf-8') as infile:
            for line in infile:
                queries.append(line.strip())
        return queries

    def build_overpass_query(self, locations, queries, timeout, distance):
        """Build and return full Overpass API query"""

        latlon = ','.join([loc.str() for loc in locations])
        query = (
            f'[out:json][timeout:{timeout}];\n'
            '(\n')
        for q in queries:
            query += f'    {q}(around:{distance},{latlon});\n'
        query += (
            ');\n'
            'out geom;')

        return query

    def process_overpass_response(self, jresponse):
        """Process JSON response from Overpass API request"""

        node_count = way_count = 0
        for element in jresponse['elements']:
            element_type = element['type']
            if element_type not in ('node', 'way'):
                continue

            element_id = element['id']

            if 'node' == element_type:
                # check if element already exists, can happen if we perform multiple Overpass API
                # queries to limit the number of locations per query and the same elements are
                # returned by subsequent queries
                if element_id in self.node_ids:
                    if self.verbose:
                        print(f'Skipping previously obtained node {element_id}')
                    continue

                if self.verbose:
                    print(f'Adding new node {element_id}')
                self.node_ids.add(element_id)

                loc = Location(element['lat'], element['lon'])
                node = self.Node(element_id, loc)
                self.nodes_out.append(node)
                node_count += 1
            elif 'way' == element_type:
                if element_id in self.way_ids:
                    if self.verbose:
                        print(f'Skipping previously obtained way {element_id}')
                    continue

                if self.verbose:
                    print(f'Adding new way {element_id}')
                self.way_ids.add(element_id)

                way = self.Way(element_id)
                for geometry in element['geometry']:
                    location = Location(geometry['lat'], geometry['lon'])
                    way.add_node(location)
                self.ways_out.append(way)
                way_count += 1
        print(f'Obtained {way_count} ways and {node_count} nodes from Overpass API')

    def perform_overpass_query(self, locations, query, timeout, distance, dry_run):
        """Query Overpass API for given locations"""

        print(f'Performing Overpass API query for {len(locations)} locations')

        full_query = self.build_overpass_query(locations, query, timeout, distance)
        if dry_run or self.verbose > 1:
            print(f'Query:\n{full_query}')
        if dry_run:
            return

        post_data = urllib.parse.urlencode({'data': full_query}).encode()

        request = urllib.request.Request(f'{self.url}/interpreter', data=post_data)
        jresponse = None
        success = False
        for i in range(0, self.retries + 1):
            delay = 0.1
            try:
                if self.verbose and i > 0:
                    print(f'Retry {i} of {self.retries}')

                t_start = time.perf_counter()
                response = urllib.request.urlopen(request)
                t_end = time.perf_counter()

                try:
                    jresponse = json.load(response)
                    print(f'Overpass API query took {(t_end - t_start):.1f} seconds')
                    if 'remark' in jresponse:
                        print(f'Remark from Overpass API: {jresponse["remark"]}')
                    else:
                        # request was successful, response was valid
                        success = True
                        break
                except Exception as e:
                    print(f'Failed to parse Overpass API JSON response: {ex}')
            except urllib.error.URLError as ex:
                t_end = time.perf_counter()
                print(ex)
                if self.verbose > 1:
                    print('Error response body:')
                    print(ex.fp.read().decode("utf-8"))
                if 429 == ex.code:
                    print('Too many requests, delaying next request...')
                    delay = 20
            except http.client.ConnectionError as ex:
                t_end = time.perf_counter()
                print(ex)
            print(f'Querying Overpass API failed in try {i + 1}/{self.retries + 1} after '
                f'{(t_end - t_start):.1f} seconds')
            time.sleep(delay)

        if not success:
            print(f'Querying Overpass API failed after {self.retries + 1} tries')
            self.failure = True
            return

        self.process_overpass_response(jresponse)

    def perform_overpass_queries(self, queries, timeout, distance, dry_run):
        """Perform multiple Overpass API queries for given locations via multiple chunks"""

        if self.limit <= 0:
            num_queries = 1
            chunk_size = len(self.locations_in)
        else:
            num_queries = math.ceil(len(self.locations_in) / self.limit)
            chunk_size = self.limit

        print(f'Queries: {queries}')
        if self.verbose:
            print(f'Performing {num_queries} queries with {chunk_size} locations each '
                  f'for {len(self.locations_in)} locations in total')

        for i in range(0, num_queries):
            start = i * chunk_size
            end = min(start + chunk_size, len(self.locations_in))
            if self.verbose and num_queries > 1:
                print(f'Chunk {i} of {num_queries} for {end-start} locations from '
                      f'{start + 1} to {end}')
            self.perform_overpass_query(
                self.locations_in[start:end], queries, timeout, distance, dry_run)

    def run(self, infiles, outfile, query, queryfile, title, timeout, distance, dry_run):
        """Perform all the magic"""

        for infile in infiles:
            self.parse_gpx_file(infile)
        if not self.locations_in:
            print('No locations found')
            return

        if queryfile:
            queries = self.read_overpass_queries_from_file(queryfile)
        else:
            queries = [query]

        self.perform_overpass_queries(queries, timeout, distance, dry_run)

        if dry_run:
            return

        if self.nodes_out or self.ways_out:
            self.write_result(outfile, title)

        if self.failure:
            print('Warning: result may be incomplete due to failed Overpass API calls')

def main() -> int:
    """main"""

    parser = argparse.ArgumentParser(
        prog='Overpass API along GPX',
        description='Query Overpass API along GPX files',
        epilog=f'example: {sys.argv[0]} -o out.gpx -q \'way["highway"][!"surface"]\' in.gpx',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('files', nargs='*', help='GPX files to read')
    parser.add_argument('-o', '--outfile', required=True, help='output file')
    parser.add_argument('-q', '--query',
        help='Overpass API tag query, e.g. \'node["amenity"~"bench|waste_basket"]\'')
    parser.add_argument('-f', '--queryfile',
        help='file that contains Overpass API tag queries, one query per line')
    parser.add_argument('-n', '--name', help='title of the resulting GPX file')
    parser.add_argument('-t', '--timeout', type=int, default=120,
        help='timeout of the Overpass API query in seconds')
    parser.add_argument('-d', '--distance', type=int, default=20,
        help='maximum distance around track in meters to query Overpass API for')
    parser.add_argument('-l', '--limit', type=int, default=0,
        help='limit number of locations per Overpass API query to perform multiple smaller '
             'queries instead of a large one (use 0 for unlimited, try 500 if requests fail)')
    parser.add_argument('-r', '--retries', type=int, default=3,
        help='number of retries if call to Overpass API fails')
    parser.add_argument('-u', '--url', default='https://overpass-api.de/api/',
        help='Overpass API instance')
    parser.add_argument('--dry-run', action='store_true', default=False,
        help='don\'t execute Overpass API query, only print it')
    parser.add_argument('-v', '--verbose', action='count', default=0,
        help='print debugging information (use twice to be more verbose)')

    args = parser.parse_args()

    if (
        (args.query and args.queryfile) or
        (not args.query and not args.queryfile)
       ):
        print('error: need either query or queryfile as argument')
        parser.print_help()
        sys.exit(1)

    ov_gpx = OverpassAlongGPX(args.url, args.limit, args.retries, args.verbose)
    ov_gpx.run(args.files, args.outfile, args.query, args.queryfile, args.name,
        args.timeout, args.distance, args.dry_run)

    return 0

if __name__ == '__main__':
    sys.exit(main())
