import { useState } from "react";
import { PersonFill } from "react-bootstrap-icons";
import COURSE_BASE from "./coursePath";
import type { ID } from "./models";

type Props = {
  studentID: ID;
  // Width and height in pixels.
  size: number;
};

// Input: studentID, whose Cal 1 Card photo to show, and its size in pixels.
// Output: the photo, or a gray placeholder if there isn't one.
// Description: Only for staff pages: the server refuses everyone else. The
// server answers 404 with no photo, so onError switches to the placeholder.
// alt is empty because the student's name is always shown right beside it.
export default function StudentPhoto({ studentID, size }: Props) {
  // Remember which student failed, so moving to another student tries again.
  const [missingPhotoID, setMissingPhotoID] = useState<ID | null>(null);

  if (missingPhotoID === studentID) {
    return (
      <div
        className="rounded bg-secondary-subtle text-secondary d-flex align-items-center justify-content-center flex-shrink-0"
        style={{ width: size, height: size }}
        aria-hidden="true"
      >
        <PersonFill size={size / 2} />
      </div>
    );
  }
  return (
    <img
      src={`${COURSE_BASE}/api/students/${studentID}/photo`}
      alt=""
      width={size}
      height={size}
      className="rounded flex-shrink-0"
      style={{ objectFit: "cover" }}
      onError={() => setMissingPhotoID(studentID)}
    />
  );
}
