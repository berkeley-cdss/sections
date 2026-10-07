"""
This file is meant to be run locally on dev for testing. It is not for prod.
This was included because the import sheet function currently does not work locally.
The file should be exactly what is passed to the import_sheet function, but in a CSV format.
"""

from __future__ import annotations

import csv
import argparse

from course import load_course
from main import app
from import_sheet import import_enrollment, import_sections

def main(canvas_course_id: int, import_type, file_path: str):
    with app.app_context():
        load_course(canvas_course_id)
        with open(file_path, mode='r') as f:
            csvData = csv.reader(f)

            if import_type == "sections":
                import_sections(csvData)
            elif import_type == "enrollment":
                import_enrollment(csvData)

    print("Done importing!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", required=True, type=str, choices=["sections", "enrollment"])
    parser.add_argument("--file", required=True, type=str)
    parser.add_argument("--course", required=True, type=int, help="Canvas course id, set up first (e.g. via seed.py)")
    
    args = parser.parse_args()
    main(args.course, args.type, args.file)