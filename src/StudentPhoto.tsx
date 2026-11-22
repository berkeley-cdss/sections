import { useState } from "react";
import COURSE_BASE from "./coursePath";
import type { ID } from "./models";

type Props = {
  studentID: ID;
  // Width and height in pixels.
  size: number;
};

// Input: studentID, whose Cal 1 Card photo to show, and its size in pixels.
// Output: the photo, or seating's gray placeholder if there isn't one.
// Description: Only for staff pages: the server refuses everyone else. The
// server answers 404 with no photo, so onError switches to the placeholder.
// alt is empty because the student's name is always shown right beside it.
export default function StudentPhoto({ studentID, size }: Props) {
  // Remember which student failed, so moving to another student tries again.
  const [missingPhotoID, setMissingPhotoID] = useState<ID | null>(null);

  // public/photo-placeholder.png is seating's server/static/img/photo-placeholder.png.
  const photoURL =
    missingPhotoID === studentID
      ? "/photo-placeholder.png"
      : `${COURSE_BASE}/api/students/${studentID}/photo`;
  return (
    <img
      src={photoURL}
      alt=""
      // As on seating's seat maps: photos far below the screen load as you scroll near them.
      loading="lazy"
      width={size}
      height={size}
      className="rounded flex-shrink-0"
      style={{ objectFit: "cover" }}
      onError={() => setMissingPhotoID(studentID)}
    />
  );
}
