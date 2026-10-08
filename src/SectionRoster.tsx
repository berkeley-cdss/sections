import { useContext, useState } from "react";
import Button from "react-bootstrap/Button";
import Card from "react-bootstrap/Card";
import { Link, Navigate } from "react-router-dom";
import styled from "styled-components";
import AddStudentModal from "./AddStudentModal";
import type { SectionDetails } from "./models";
import StateContext from "./StateContext";
import useAPI from "./useStateAPI";
import useSectionAPI from "./useSectionAPI";

const FlexLayout = styled.div`
  display: flex;
  flex-wrap: wrap;
`;

const CardHolder = styled.div`
  width: 300px;
  margin: 8px;
`;

type Props = {
  section: SectionDetails;
};

export default function SectionRoster({ section }: Props) {
  const { currentUser } = useContext(StateContext);

  const deleteSection = useAPI("delete_section");
  const addStudents = useSectionAPI("add_students");
  const removeStudent = useSectionAPI("remove_student");
  const refreshState = useAPI("refresh_state");

  const [adding, setAdding] = useState(false);
  const [deleted, setDeleted] = useState(false);

  if (deleted) {
    return <Navigate to="/" replace />;
  }

  const copyEmailsToClipboard = () => {
    const studentEmails = section.students.map((student) => student.email).join(", ");
    navigator.clipboard.writeText(studentEmails);
  };

  return (
    <>
      <FlexLayout>
        {section.students.length === 0 && currentUser?.isAdmin && (
          <CardHolder>
            <Card>
              <Card.Body>
                <Card.Title>No students are enrolled.</Card.Title>
                <Card.Text>It&apos;s lonely here...</Card.Text>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() =>
                    deleteSection({ section_id: section.id }).then(() => setDeleted(true))
                  }
                >
                  Delete Section
                </Button>
              </Card.Body>
            </Card>
          </CardHolder>
        )}
        <CardHolder>
          <Card>
            <Card.Body>
              <Card.Title>Copy Roster</Card.Title>
              <Card.Text>Gets student emails.</Card.Text>
              <Button variant="primary" size="sm" onClick={copyEmailsToClipboard}>
                Copy Roster
              </Button>
            </Card.Body>
          </Card>
        </CardHolder>
        {section.students.map((student) => (
          <CardHolder key={student.email}>
            <Card>
              <Card.Body>
                <Card.Title>
                  <Link to={`/user/${student.id}`}>{student.name}</Link>
                </Card.Title>
                <Card.Text>
                  <a href={`mailto:${student.email}`}>{student.email}</a>
                </Card.Text>{" "}
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() =>
                    removeStudent({
                      student: student.email,
                      section_id: section.id,
                    }).then(() => refreshState())
                  }
                >
                  Remove
                </Button>
              </Card.Body>
            </Card>
          </CardHolder>
        ))}
        <CardHolder>
          <Card>
            <Card.Body>
              <Card.Title>Add Students</Card.Title>
              <Card.Text>They will be moved here.</Card.Text>
              <Button variant="primary" size="sm" onClick={() => setAdding(true)}>
                Add Students
              </Button>
            </Card.Body>
          </Card>
        </CardHolder>
      </FlexLayout>
      <AddStudentModal
        show={adding}
        onAdd={(emails) =>
          addStudents({ section_id: section.id, emails }).then(() => refreshState())
        }
        onClose={() => setAdding(false)}
      />
    </>
  );
}
