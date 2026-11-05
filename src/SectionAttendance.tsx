import { useContext, useState } from "react";
import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";
import AddSessionModal from "./AddSessionModal";

import { canEditSection } from "./models";
import type { SectionDetails } from "./models";
import SessionAttendance from "./SessionAttendance";
import StateContext from "./StateContext";

type Props = {
  section: SectionDetails;
};

export default function SectionAttendance({ section }: Props) {
  const { currentUser } = useContext(StateContext);
  const [adding, setAdding] = useState(false);

  if (!canEditSection(currentUser, section)) {
    // Past sessions, read-only; there's nothing to start or add.
    return (
      <>
        <br />
        <Alert variant="info" className="mb-0">
          You are not the TA assigned to this section, so you cannot log attendance.
        </Alert>
        {section.sessions
          .slice()
          .reverse()
          .map((session) => (
            <SessionAttendance key={session.startTime} session={session} section={section} />
          ))}
      </>
    );
  }

  return (
    <>
      <SessionAttendance section={section} />
      {section.sessions
        .slice()
        .reverse()
        .map((session) => (
          <SessionAttendance
            key={session.startTime}
            session={session}
            section={section}
          />
        ))}
      <p>
        <br />
        <Button variant="secondary" size="sm" onClick={() => setAdding(true)}>
          Add Missing Session
        </Button>
      </p>
      <AddSessionModal
        show={adding}
        section={section}
        onClose={() => setAdding(false)}
      />
    </>
  );
}
