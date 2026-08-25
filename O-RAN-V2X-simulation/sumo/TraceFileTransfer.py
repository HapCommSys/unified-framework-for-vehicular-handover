#!/usr/bin/env python3
"""Convert SUMO floating-car data (FCD) XML to the ns-3 waypoint format.

The generated file is consumed by ``scratch/MultiVehicleURLLC.cc``.  Each
vehicle is represented by a block of ``time x y`` records; blank lines separate
vehicles.  Comment lines beginning with ``#`` preserve the corresponding SUMO
vehicle identifier without changing the numeric input format.
"""

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def local_name(tag):
    return tag.rsplit('}', 1)[-1]


def natural_key(value):
    return [int(part) if part.isdigit() else part for part in re.split(r'(\d+)', value)]


def read_fcd(input_path):
    traces = {}

    for _, element in ET.iterparse(str(input_path), events=('end',)):
        if local_name(element.tag) != 'timestep':
            continue

        try:
            timestamp = float(element.attrib['time'])
        except (KeyError, ValueError) as exc:
            raise ValueError('A SUMO <timestep> is missing a valid time attribute') from exc

        for vehicle in element:
            if local_name(vehicle.tag) != 'vehicle':
                continue
            try:
                vehicle_id = vehicle.attrib['id']
                x = float(vehicle.attrib['x'])
                y = float(vehicle.attrib['y'])
            except (KeyError, ValueError) as exc:
                raise ValueError(
                    'A SUMO <vehicle> is missing valid id, x, or y attributes'
                ) from exc

            vehicle_trace = traces.setdefault(vehicle_id, [])
            if vehicle_trace and timestamp <= vehicle_trace[-1][0]:
                raise ValueError(
                    'Non-increasing timestamp for vehicle {!r}: {}'.format(vehicle_id, timestamp)
                )
            vehicle_trace.append((timestamp, x, y))

        element.clear()

    return traces


def write_trace(traces, output_path, precision, minimum_samples):
    selected_ids = [
        vehicle_id
        for vehicle_id in sorted(traces, key=natural_key)
        if len(traces[vehicle_id]) >= minimum_samples
    ]
    if not selected_ids:
        raise ValueError(
            'No vehicle has at least {} FCD samples'.format(minimum_samples)
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    number_format = '{{:.{}f}}'.format(precision)

    with output_path.open('w', encoding='utf-8', newline='\n') as output_file:
        for vehicle_id in selected_ids:
            output_file.write('# vehicle {}\n'.format(vehicle_id))
            for timestamp, x, y in traces[vehicle_id]:
                output_file.write(
                    '{} {} {}\n'.format(
                        number_format.format(timestamp),
                        number_format.format(x),
                        number_format.format(y),
                    )
                )
            output_file.write('\n')

    return len(selected_ids)


def parse_args():
    parser = argparse.ArgumentParser(
        description='Convert SUMO FCD XML to MultiVehicleURLLC waypoint traces.'
    )
    parser.add_argument('input', type=Path, help='SUMO FCD XML file')
    parser.add_argument('output', type=Path, help='output traceFile.txt path')
    parser.add_argument(
        '--precision', type=int, default=6, help='decimal places in the output (default: 6)'
    )
    parser.add_argument(
        '--minimum-samples',
        type=int,
        default=2,
        help='discard vehicles with fewer samples (default: 2)',
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.precision < 0:
        raise ValueError('--precision must be non-negative')
    if args.minimum_samples < 2:
        raise ValueError('--minimum-samples must be at least 2')
    if not args.input.is_file():
        raise FileNotFoundError('SUMO FCD file not found: {}'.format(args.input))

    traces = read_fcd(args.input)
    vehicle_count = write_trace(
        traces,
        args.output,
        precision=args.precision,
        minimum_samples=args.minimum_samples,
    )
    print('Wrote {} vehicle trace(s) to {}'.format(vehicle_count, args.output))


if __name__ == '__main__':
    try:
        main()
    except (ET.ParseError, OSError, ValueError) as exc:
        print('Trace conversion failed: {}'.format(exc), file=sys.stderr)
        sys.exit(1)
