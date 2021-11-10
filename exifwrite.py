#!/usr/bin/env python

import glob
import os
import csv
import piexif
from fractions import Fraction
from gooey import Gooey
from gooey import GooeyParser
from pyproj import Transformer
from datetime import datetime
from gps_time.core import GPSTime

@Gooey(progress_regex=r"^progress: (?P<current>\d+)/(?P<total>\d+)$",
       progress_expr="current / total * 100")

def main():
    # Initialize parser
    parser = GooeyParser(description="Rock Robotic Exif Writer. Use either the CSV file created by PCPainter \nor your Trajectory file -- NOT BOTH. \nFor the most accuracy, use the PCPainter generated csv file.")
    parser.add_argument(
        '--image_list_csv',
        metavar='Image List CSV',
        help='Generated by PCMaster',
        widget='FileChooser'
    )
    parser.add_argument(
        '--trajectory',
        metavar='Trajectory File',
        help='Trajectory File (Not recommended)',
        widget='FileChooser'
    )

    parser.add_argument(
        'base_camera_dir',
        metavar='Photo Directory (required)',
        help="Photo Directory",
        widget='DirChooser')

    # Read arguments from command line
    args = parser.parse_args()
    photos = glob.glob(args.base_camera_dir + os.sep + '*jpg')
    total_photos = len(photos)
    print("Camera directory " + args.base_camera_dir)
    print("Total Photos " + str(total_photos))

    if total_photos == 0:
        print('No photos found!')
        return

    if args.trajectory:
        print("Trajectory File: " + args.trajectory)
        traj = open(args.trajectory, newline='')
        trajectory_csv = csv.reader(traj, delimiter='\t')
        photo_num = 0
        for photo in photos:
            head, tail = os.path.split(photo)
            name = tail.split('_')
            startTime = name[1]
            name2 = name[2].split('.')

            imageStart = (int(startTime) % 604800000000) / 1000000
            i = 0
            before = ''
            after = ''
            previous = ''
            traj.seek(0)
            for line in trajectory_csv:
                if i > 0:
                    if imageStart < float(line[1]):
                        if after == '':
                            before = previous
                            after = line
                            break

                    previous = line

                i = i + 1

            if before != '' and after != '':
                # Find which one is closest.
                beforeDiff = float(before[1]) - imageStart
                afterDiff = imageStart - float(after[1])
                if beforeDiff < afterDiff:
                    photo_date = get_photo_date(before[0], before[1])
                    set_gps_location(photo, float(before[4]), float(before[3]), float(before[5]), photo_date)
                else:
                    photo_date = get_photo_date(after[0], after[1])
                    set_gps_location(photo, float(after[4]), float(after[3]), float(after[5]), photo_date)
            photo_num = photo_num + 1
            print('progress: ' + str(photo_num) + '/' + str(total_photos))

    if args.image_list_csv:
        print("CSV File: " + args.image_list_csv)
        traj = open(args.image_list_csv, newline='')
        trajectory_csv = csv.reader(traj, delimiter=',')
        total_lines = len(list(trajectory_csv))
        i = 0
        traj.seek(0)
        headers = []
        week = 0
        second = 1
        epsg = 2
        easting = 3
        northing = 4
        height = 5
        photo_item = 9

        for line in trajectory_csv:
            if i > 0:
                photoname = line[photo_item]
                photoname = photoname.replace('camera/', '')
                if os.path.exists(args.base_camera_dir + os.sep + photoname):
                    photo = args.base_camera_dir + os.sep + photoname
                    reproject = reproject_point(line[easting], line[northing], 'epsg:' + line[epsg])
                    photo_date = get_photo_date(line[week], line[second])
                    set_gps_location(photo, float(reproject[1]), float(reproject[0]), float(line[height]), photo_date)
            else:
                headers = line
                if headers[0] == 'Easting':
                    week = 9
                    second = 10
                    epsg = 11
                    easting = 0
                    northing = 1
                    height = 2
                    photo_item = 8

            i = i + 1
            print('progress: ' + str(i) + '/' + str(total_lines))

def get_photo_date(gpsweek, seconds):
    float_val = float(seconds)
    int_val = int(float_val)
    gps_time = GPSTime(gpsweek, int_val)
    return gps_time.to_datetime().strftime("%Y:%m:%d %H:%M:%S")

def reproject_point(x, y, in_crs, out_crs = 'epsg:4326'):
    try:
        transformer = Transformer.from_crs(in_crs, out_crs, always_xy=True)
        x2, y2 = transformer.transform(x, y)
        return [x2, y2]
    except:
        return [0, 0]

def to_deg(value, loc):
    """convert decimal coordinates into degrees, minutes and seconds tuple
    Keyword arguments: value is float gps-value, loc is direction list ["S", "N"] or ["W", "E"]
    return: tuple like (25, 13, 48.343 ,'N')
    """
    if value < 0:
        loc_value = loc[0]
    elif value > 0:
        loc_value = loc[1]
    else:
        loc_value = ""
    abs_value = abs(value)
    deg =  int(abs_value)
    t1 = (abs_value-deg)*60
    min = int(t1)
    sec = round((t1 - min)* 60, 5)
    return (deg, min, sec, loc_value)


def change_to_rational(number):
    """convert a number to rantional
    Keyword arguments: number
    return: tuple like (1, 2), (numerator, denominator)
    """
    f = Fraction(str(number))
    return (f.numerator, f.denominator)


def set_gps_location(file_name, lat, lng, altitude, photo_date):
    """Adds GPS position as EXIF metadata
    Keyword arguments:
    file_name -- image file
    lat -- latitude (as float)
    lng -- longitude (as float)
    altitude -- altitude (as float)
    """
    lat_deg = to_deg(lat, ["S", "N"])
    lng_deg = to_deg(lng, ["W", "E"])

    exiv_lat = (change_to_rational(lat_deg[0]), change_to_rational(lat_deg[1]), change_to_rational(lat_deg[2]))
    exiv_lng = (change_to_rational(lng_deg[0]), change_to_rational(lng_deg[1]), change_to_rational(lng_deg[2]))

    if altitude <= 0:
        altitude = 1

    gps_ifd = {
        piexif.GPSIFD.GPSVersionID: (2, 0, 0, 0),
        piexif.GPSIFD.GPSAltitudeRef: 0,
        piexif.GPSIFD.GPSAltitude: change_to_rational(round(altitude, 2)),
        piexif.GPSIFD.GPSLatitudeRef: lat_deg[3],
        piexif.GPSIFD.GPSLatitude: exiv_lat,
        piexif.GPSIFD.GPSLongitudeRef: lng_deg[3],
        piexif.GPSIFD.GPSLongitude: exiv_lng,
    }

    gps_exif = {
        "GPS": gps_ifd
    }

    # get original exif data first!
    try:
        exif_data = piexif.load(file_name)

        # update original exif data to include GPS tag
        exif_data.update(gps_exif)
        exif_data["0th"][piexif.ImageIFD.DateTime] = photo_date
        exif_data["Exif"][piexif.ExifIFD.DateTimeOriginal] = photo_date
        exif_data["Exif"][piexif.ExifIFD.DateTimeDigitized] = photo_date
        exif_bytes = piexif.dump(exif_data)

        piexif.insert(exif_bytes, file_name)
    except:
        print("Could not open " + str(file_name))

if __name__ == '__main__':
    main()