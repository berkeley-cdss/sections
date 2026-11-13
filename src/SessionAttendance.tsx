import moment from "moment";
import { useContext, useState } from "react";
import Button from "react-bootstrap/Button";
import Card from "react-bootstrap/Card";
import Table from "react-bootstrap/Table";
import { Link } from "react-router-dom";
import styled from "styled-components";
import AddStudentModal from "./AddStudentModal";
import AttendanceRow from "./AttendanceRow";
import Pronouns from "./Pronouns";
import { canEditSection, nextSessionStartTime } from "./models";
import type { AttendanceStatusType, Person, SectionDetails, Session } from "./models";
import StateContext from "./StateContext";
import useSectionAPI from "./useSectionAPI";

const TableHolder = styled.div`
  margin-bottom: -1em;
`;

const CardHeader = styled.div`
  display: flex;
  width: 100%;
  justify-content: space-between;
  align-items: center;
`;

const ButtonGroup = styled.div`
  display: flex;
  gap: 0.5em;
`;

function deleteQuestion(session: Session): string {
  const date = moment.unix(session.startTime).format("MMMM D");
  const count = session.attendances.length;
  const attendance =
    count === 0
      ? "No attendance has been taken in it."
      : `Its attendance for ${count} ${count === 1 ? "student" : "students"} will be deleted too.`;
  return `Delete the ${date} session? ${attendance} This can't be undone.`;
}

type Props = {
  section: SectionDetails;
  session?: Session | null;
};

export default function SessionAttendance({ section, session }: Props) {
  const startSession = useSectionAPI("start_session");
  const setAttendance = useSectionAPI("set_attendance");
  const deleteSession = useSectionAPI("delete_session");

  const { currentUser } = useContext(StateContext);
  const canEdit = canEditSection(currentUser, section);
  const [adding, setAdding] = useState(false);

  const mostRecentSession =
    section.sessions.length > 0 ? section.sessions[section.sessions.length - 1] : null;

  const notStartedSectionExists =
    mostRecentSession == null ||
    moment().isAfter(moment.unix(mostRecentSession.startTime).add(1.5, "days"));

  // if the latest section recently occurred, it is still "latest", not the one in the future
  const latestSectionStartTime = nextSessionStartTime(section, -1.5);

  if (session == null && !notStartedSectionExists) {
    return null;
  }

  const sessionStudents: Array<Person> =
    session?.attendances.map((attendance) => attendance.student) ?? [];

  const students = Array.from(
    new Map(
      (session == null || (session?.id === mostRecentSession?.id && !notStartedSectionExists)
        ? section.students.concat(sessionStudents)
        : sessionStudents
      ).map((student) => [student.email, student])
    ).values()
  ).sort((a, b) => a.name.localeCompare(b.name));

  const getStudentAttendanceStatus = (email: string): AttendanceStatusType | null => {
    if (session == null) {
      return null;
    }
    for (const attendance of session.attendances) {
      if (attendance.student.email === email) {
        return attendance.status;
      }
    }
    return null;
  };

  return (
    <>
      <br />
      <Card>
        <Card.Header>
          <CardHeader>
            <b>
              {(session == null ? latestSectionStartTime : moment.unix(session.startTime)).format(
                "MMMM D"
              )}
              {session == null && " (not started)"}
            </b>
            {!canEdit ? null : session == null ? (
              <Button
                variant="primary"
                size="sm"
                onClick={() =>
                  startSession({
                    section_id: section.id,
                    start_time: latestSectionStartTime.unix(),
                  })
                }
              >
                Start Session
              </Button>
            ) : (
              <ButtonGroup>
                <Button variant="secondary" size="sm" onClick={() => setAdding(true)}>
                  Add Students
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  aria-label={`Delete the ${moment.unix(session.startTime).format("MMMM D")} session`}
                  onClick={() => {
                    if (window.confirm(deleteQuestion(session))) {
                      deleteSession({ session_id: session.id });
                    }
                  }}
                >
                  Delete
                </Button>
              </ButtonGroup>
            )}
          </CardHeader>
        </Card.Header>
        <TableHolder>
          <Table>
            <tbody>
              {students.map((student) => (
                <tr key={student.email} className="text-center">
                  <td className="align-middle">
                    <Link to={`/user/${student.id}`}>{student.name}</Link>
                    <Pronouns of={student} />
                  </td>
                  <td>
                    <AttendanceRow
                      editable={canEdit && session != null}
                      status={getStudentAttendanceStatus(student.email)}
                      onClick={(status) => {
                        if (canEdit && session != null)
                          setAttendance({
                            session_id: session.id,
                            students: student.email,
                            status,
                          });
                      }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableHolder>
      </Card>
      {canEdit && session != null && (
        <AddStudentModal
          show={adding}
          onAdd={(addedStudents) =>
            setAttendance({
              session_id: session.id,
              students: addedStudents,
              status: "present" satisfies AttendanceStatusType,
            })
          }
          onClose={() => setAdding(false)}
        />
      )}
    </>
  );
}
